"""
Credit Balance Checker — polls CodeBuddy /billing/ide/usage per credential
to track real remaining credits and deprioritize near-exhausted accounts.
"""
import asyncio
import logging
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

CODEBUDDY_BASE = "https://www.codebuddy.ai"
BILLING_ENDPOINT = f"{CODEBUDDY_BASE}/billing/ide/usage"

CHECK_INTERVAL_SECONDS = 300      # Poll every 5 minutes
STAGGER_DELAY_SECONDS = 2         # Delay between credential checks to avoid burst
LOW_CREDIT_THRESHOLD = 0.10       # 10% remaining → warning
CRITICAL_CREDIT_THRESHOLD = 0.05  # 5% remaining → critical


class CredentialCredit:
    __slots__ = ("credential_id", "used", "total", "checked_at", "error", "status")

    def __init__(self, credential_id: str):
        self.credential_id = credential_id
        self.used: int = 0
        self.total: int = 0
        self.checked_at: float = 0
        self.error: Optional[str] = None
        self.status: str = "unknown"  # ok, warning, critical, error, unknown

    @property
    def remaining(self) -> int:
        return max(self.total - self.used, 0)

    @property
    def usage_fraction(self) -> float:
        if self.total <= 0:
            return 0.0
        return self.used / self.total

    @property
    def remaining_fraction(self) -> float:
        return 1.0 - self.usage_fraction

    def to_dict(self) -> Dict[str, Any]:
        return {
            "credential_id": self.credential_id,
            "used": self.used,
            "total": self.total,
            "remaining": self.remaining,
            "usage_pct": round(self.usage_fraction * 100, 1),
            "remaining_pct": round(self.remaining_fraction * 100, 1),
            "status": self.status,
            "checked_at": self.checked_at,
            "error": self.error,
        }


class CreditChecker:
    """Background service that periodically checks credit balance for all credentials."""

    def __init__(self):
        self._credits: Dict[str, CredentialCredit] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._on_critical_callback = None

    def set_on_critical(self, callback):
        """Set callback(credential_id, credit_info) when a credential hits critical."""
        self._on_critical_callback = callback

    async def start(self, token_manager):
        """Start the background polling loop."""
        self._token_manager = token_manager
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("CreditChecker started (interval=%ds)", CHECK_INTERVAL_SECONDS)

    async def stop(self):
        """Stop the background polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("CreditChecker stopped")

    async def _poll_loop(self):
        """Main loop: check all credentials periodically."""
        await asyncio.sleep(5)  # Initial delay to let app start
        while self._running:
            try:
                await self._check_all_credentials()
            except Exception as e:
                logger.error(f"CreditChecker poll error: {e}")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    async def _check_all_credentials(self):
        """Check credit for every loaded credential."""
        credentials = self._token_manager.credentials
        if not credentials:
            return

        import os
        for cred in credentials:
            if not self._running:
                break
            filename = os.path.basename(cred["file_path"])
            bearer_token = cred["data"].get("bearer_token", "")
            if not bearer_token:
                continue

            await self._check_single(filename, bearer_token)
            await asyncio.sleep(STAGGER_DELAY_SECONDS)

    async def _check_single(self, credential_id: str, bearer_token: str):
        """Check credit for a single credential via /billing/ide/usage."""
        credit = self._credits.setdefault(credential_id, CredentialCredit(credential_id))

        headers = {
            "Accept": "application/json",
            "X-Api-Key": bearer_token,
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "CLI/1.0.7 CodeBuddy/1.0.7",
        }

        try:
            async with httpx.AsyncClient(verify=False, timeout=15) as client:
                resp = await client.get(BILLING_ENDPOINT, headers=headers)

            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0:
                    usage_data = data.get("data", {})
                    credit.used = usage_data.get("used", 0)
                    credit.total = usage_data.get("total", 0)
                    credit.checked_at = time.time()
                    credit.error = None

                    remaining_frac = credit.remaining_fraction
                    if remaining_frac <= CRITICAL_CREDIT_THRESHOLD:
                        credit.status = "critical"
                        if self._on_critical_callback:
                            try:
                                self._on_critical_callback(credential_id, credit.to_dict())
                            except Exception:
                                pass
                    elif remaining_frac <= LOW_CREDIT_THRESHOLD:
                        credit.status = "warning"
                    else:
                        credit.status = "ok"

                    logger.debug(
                        f"Credit check [{credential_id}]: {credit.used}/{credit.total} "
                        f"({credit.status})"
                    )
                else:
                    credit.error = f"API code={data.get('code')}: {data.get('msg', '')}"
                    credit.status = "error"
                    credit.checked_at = time.time()
            elif resp.status_code == 401:
                credit.error = "Unauthorized (token expired?)"
                credit.status = "error"
                credit.checked_at = time.time()
            else:
                credit.error = f"HTTP {resp.status_code}"
                credit.status = "error"
                credit.checked_at = time.time()

        except httpx.TimeoutException:
            credit.error = "Timeout"
            credit.status = "error"
            credit.checked_at = time.time()
        except Exception as e:
            credit.error = str(e)
            credit.status = "error"
            credit.checked_at = time.time()
            logger.warning(f"Credit check failed [{credential_id}]: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_credit(self, credential_id: str) -> Optional[Dict[str, Any]]:
        """Get credit info for a single credential."""
        credit = self._credits.get(credential_id)
        if credit and credit.checked_at > 0:
            return credit.to_dict()
        return None

    def get_all_credits(self) -> Dict[str, Any]:
        """Get credit info for all credentials."""
        result = {}
        for cid, credit in self._credits.items():
            if credit.checked_at > 0:
                result[cid] = credit.to_dict()
        return result

    def get_credit_score(self, credential_id: str) -> float:
        """
        Returns 0.0-1.0 multiplier for credential selection.
        1.0 = plenty of credit, 0.05 = nearly exhausted.
        Used by token_manager to deprioritize low-credit credentials.
        """
        credit = self._credits.get(credential_id)
        if not credit or credit.checked_at == 0:
            return 1.0  # Unknown = assume full

        if credit.status == "error":
            return 0.8  # Can't verify, slight penalty

        remaining = credit.remaining_fraction
        if remaining <= CRITICAL_CREDIT_THRESHOLD:
            return 0.05
        if remaining <= LOW_CREDIT_THRESHOLD:
            ratio = (LOW_CREDIT_THRESHOLD - remaining) / (LOW_CREDIT_THRESHOLD - CRITICAL_CREDIT_THRESHOLD)
            return max(0.1, 1.0 - ratio * 0.9)
        return 1.0

    def get_summary(self) -> Dict[str, Any]:
        """Summary stats across all credentials."""
        all_credits = [c for c in self._credits.values() if c.checked_at > 0]
        if not all_credits:
            return {"total_credentials": 0, "checked": 0}

        total_used = sum(c.used for c in all_credits)
        total_capacity = sum(c.total for c in all_credits)
        ok_count = sum(1 for c in all_credits if c.status == "ok")
        warning_count = sum(1 for c in all_credits if c.status == "warning")
        critical_count = sum(1 for c in all_credits if c.status == "critical")
        error_count = sum(1 for c in all_credits if c.status == "error")

        return {
            "total_credentials": len(self._credits),
            "checked": len(all_credits),
            "total_used": total_used,
            "total_capacity": total_capacity,
            "total_remaining": total_capacity - total_used,
            "overall_usage_pct": round(total_used / max(total_capacity, 1) * 100, 1),
            "ok": ok_count,
            "warning": warning_count,
            "critical": critical_count,
            "error": error_count,
        }

    async def force_check(self, credential_id: str) -> Optional[Dict[str, Any]]:
        """Force an immediate credit check for a specific credential."""
        import os
        for cred in self._token_manager.credentials:
            filename = os.path.basename(cred["file_path"])
            if filename == credential_id:
                bearer_token = cred["data"].get("bearer_token", "")
                if bearer_token:
                    await self._check_single(credential_id, bearer_token)
                    return self.get_credit(credential_id)
        return None


credit_checker = CreditChecker()
