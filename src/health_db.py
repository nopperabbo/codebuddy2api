import time
import sqlite3
import asyncio
import logging
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DB_PATH = Path("data/health.db")


@dataclass
class CredentialEvent:
    timestamp: float
    credential_id: str
    event_type: str
    status_code: int = 0
    latency_ms: float = 0.0
    error: str = ""


@dataclass
class AlertRecord:
    timestamp: float
    alert_type: str
    severity: str
    message: str
    resolved_at: Optional[float] = None


class HealthDatabase:
    _instance: Optional["HealthDatabase"] = None

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._init_db()

    @classmethod
    def get_instance(cls, db_path: Optional[Path] = None) -> "HealthDatabase":
        if cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        cls._instance = None

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS credential_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    credential_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    status_code INTEGER DEFAULT 0,
                    latency_ms REAL DEFAULT 0.0,
                    error TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    resolved_at REAL
                );

                CREATE INDEX IF NOT EXISTS idx_events_cred_time
                    ON credential_events(credential_id, timestamp DESC);

                CREATE INDEX IF NOT EXISTS idx_events_time
                    ON credential_events(timestamp DESC);

                CREATE INDEX IF NOT EXISTS idx_alerts_resolved
                    ON alerts(resolved_at, timestamp DESC);
            """)
            conn.commit()
        finally:
            conn.close()

    async def record_event(self, event: CredentialEvent):
        async with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT INTO credential_events
                       (timestamp, credential_id, event_type, status_code, latency_ms, error)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (event.timestamp, event.credential_id, event.event_type,
                     event.status_code, event.latency_ms, event.error)
                )
                conn.commit()
            finally:
                conn.close()

    async def record_alert(self, alert: AlertRecord) -> int:
        async with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    """INSERT INTO alerts (timestamp, alert_type, severity, message, resolved_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (alert.timestamp, alert.alert_type, alert.severity,
                     alert.message, alert.resolved_at)
                )
                conn.commit()
                return cursor.lastrowid
            finally:
                conn.close()

    async def resolve_alert(self, alert_id: int):
        async with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE alerts SET resolved_at = ? WHERE id = ? AND resolved_at IS NULL",
                    (time.time(), alert_id)
                )
                conn.commit()
            finally:
                conn.close()

    async def get_credential_history(
        self, credential_id: str, limit: int = 100, since: Optional[float] = None
    ) -> List[dict]:
        conn = self._get_conn()
        try:
            if since:
                rows = conn.execute(
                    """SELECT * FROM credential_events
                       WHERE credential_id = ? AND timestamp >= ?
                       ORDER BY timestamp DESC LIMIT ?""",
                    (credential_id, since, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM credential_events
                       WHERE credential_id = ?
                       ORDER BY timestamp DESC LIMIT ?""",
                    (credential_id, limit)
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    async def get_credential_stats(self, credential_id: str, window_seconds: float = 3600.0) -> dict:
        conn = self._get_conn()
        since = time.time() - window_seconds
        try:
            row = conn.execute(
                """SELECT
                     COUNT(*) as total,
                     SUM(CASE WHEN event_type = 'success' THEN 1 ELSE 0 END) as successes,
                     SUM(CASE WHEN event_type = 'failure' THEN 1 ELSE 0 END) as failures,
                     AVG(CASE WHEN event_type = 'success' THEN latency_ms END) as avg_latency,
                     MAX(timestamp) as last_event
                   FROM credential_events
                   WHERE credential_id = ? AND timestamp >= ?""",
                (credential_id, since)
            ).fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    async def get_active_alerts(self) -> List[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM alerts WHERE resolved_at IS NULL
                   ORDER BY timestamp DESC"""
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    async def get_recent_alerts(self, limit: int = 50) -> List[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    async def cleanup_old_events(self, retention_hours: int = 72):
        cutoff = time.time() - (retention_hours * 3600)
        async with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "DELETE FROM credential_events WHERE timestamp < ?", (cutoff,)
                )
                conn.execute(
                    "DELETE FROM alerts WHERE resolved_at IS NOT NULL AND resolved_at < ?",
                    (cutoff,)
                )
                conn.commit()
            finally:
                conn.close()

    async def get_failure_rate_history(
        self, credential_id: str, bucket_minutes: int = 5, buckets: int = 24
    ) -> List[dict]:
        conn = self._get_conn()
        now = time.time()
        since = now - (bucket_minutes * 60 * buckets)
        try:
            rows = conn.execute(
                """SELECT
                     CAST((timestamp - ?) / ? AS INTEGER) as bucket,
                     COUNT(*) as total,
                     SUM(CASE WHEN event_type = 'failure' THEN 1 ELSE 0 END) as failures
                   FROM credential_events
                   WHERE credential_id = ? AND timestamp >= ?
                   GROUP BY bucket ORDER BY bucket""",
                (since, bucket_minutes * 60, credential_id, since)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
