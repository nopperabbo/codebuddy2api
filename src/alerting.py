import time
import asyncio
import logging
from typing import Optional, Dict, Set

from src.circuit_breaker import CircuitBreakerManager, CircuitState
from src.health_db import HealthDatabase, AlertRecord

logger = logging.getLogger(__name__)


class AlertSeverity:
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertType:
    ALL_CREDENTIALS_DOWN = "all_credentials_down"
    MAJORITY_CREDENTIALS_DOWN = "majority_credentials_down"
    CREDENTIAL_OPEN = "credential_open"
    CREDENTIAL_RECOVERED = "credential_recovered"


class AlertManager:
    _instance: Optional["AlertManager"] = None

    def __init__(self):
        self._active_alerts: Dict[str, int] = {}
        self._suppressed_until: Dict[str, float] = {}
        self._suppression_window = 300.0
        self._check_interval = 10.0
        self._running = False
        self._task: Optional[asyncio.Task] = None

    @classmethod
    def get_instance(cls) -> "AlertManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        cls._instance = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("AlertManager started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("AlertManager stopped")

    async def on_state_change(self, credential_id: str, old_state: CircuitState, new_state: CircuitState):
        db = HealthDatabase.get_instance()

        if new_state == CircuitState.OPEN:
            alert_key = f"{AlertType.CREDENTIAL_OPEN}:{credential_id}"
            if not self._is_suppressed(alert_key):
                alert = AlertRecord(
                    timestamp=time.time(),
                    alert_type=AlertType.CREDENTIAL_OPEN,
                    severity=AlertSeverity.INFO,
                    message=f"Credential {credential_id[:8]}... circuit opened (was {old_state.value})"
                )
                alert_id = await db.record_alert(alert)
                self._active_alerts[alert_key] = alert_id
                self._suppress(alert_key)
                logger.warning(f"ALERT [{AlertSeverity.INFO}]: {alert.message}")

        elif new_state == CircuitState.CLOSED and old_state in (CircuitState.OPEN, CircuitState.HALF_OPEN):
            alert_key = f"{AlertType.CREDENTIAL_OPEN}:{credential_id}"
            if alert_key in self._active_alerts:
                await db.resolve_alert(self._active_alerts[alert_key])
                del self._active_alerts[alert_key]

            recovery_alert = AlertRecord(
                timestamp=time.time(),
                alert_type=AlertType.CREDENTIAL_RECOVERED,
                severity=AlertSeverity.INFO,
                message=f"Credential {credential_id[:8]}... recovered (circuit closed)"
            )
            await db.record_alert(recovery_alert)
            logger.info(f"RESOLVED: Credential {credential_id[:8]}... recovered")

        await self._check_aggregate_health()

    async def _check_aggregate_health(self):
        cb = CircuitBreakerManager.get_instance()
        summary = cb.get_summary()
        db = HealthDatabase.get_instance()

        total = summary["total_credentials"]
        if total == 0:
            return

        open_count = summary["states"]["open"]
        open_ratio = open_count / total

        if summary["critical"]:
            alert_key = AlertType.ALL_CREDENTIALS_DOWN
            if alert_key not in self._active_alerts and not self._is_suppressed(alert_key):
                alert = AlertRecord(
                    timestamp=time.time(),
                    alert_type=AlertType.ALL_CREDENTIALS_DOWN,
                    severity=AlertSeverity.CRITICAL,
                    message=f"ALL {total} credentials are DOWN. Service unavailable."
                )
                alert_id = await db.record_alert(alert)
                self._active_alerts[alert_key] = alert_id
                self._suppress(alert_key)
                logger.critical(f"ALERT [{AlertSeverity.CRITICAL}]: {alert.message}")

        elif open_ratio >= 0.5:
            alert_key = AlertType.MAJORITY_CREDENTIALS_DOWN
            if alert_key not in self._active_alerts and not self._is_suppressed(alert_key):
                alert = AlertRecord(
                    timestamp=time.time(),
                    alert_type=AlertType.MAJORITY_CREDENTIALS_DOWN,
                    severity=AlertSeverity.WARNING,
                    message=f"{open_count}/{total} credentials are DOWN (>50%)."
                )
                alert_id = await db.record_alert(alert)
                self._active_alerts[alert_key] = alert_id
                self._suppress(alert_key)
                logger.warning(f"ALERT [{AlertSeverity.WARNING}]: {alert.message}")

        else:
            for key in [AlertType.ALL_CREDENTIALS_DOWN, AlertType.MAJORITY_CREDENTIALS_DOWN]:
                if key in self._active_alerts:
                    await db.resolve_alert(self._active_alerts[key])
                    del self._active_alerts[key]

    async def _monitor_loop(self):
        while self._running:
            try:
                await asyncio.sleep(self._check_interval)
                await self._check_aggregate_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Alert monitor error: {e}")

    def _is_suppressed(self, alert_key: str) -> bool:
        if alert_key in self._suppressed_until:
            if time.time() < self._suppressed_until[alert_key]:
                return True
            del self._suppressed_until[alert_key]
        return False

    def _suppress(self, alert_key: str):
        self._suppressed_until[alert_key] = time.time() + self._suppression_window

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "active_alerts": len(self._active_alerts),
            "suppressed_keys": len(self._suppressed_until),
        }
