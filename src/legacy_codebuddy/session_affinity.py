"""
Session Affinity Manager
Pins a specific credential to a client session (identified by IP) for
the lifetime of that OpenCode conversation. Prevents mid-session
credential switching which can disrupt long coding sessions.
"""
import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_SESSION_TTL_SECONDS = 2 * 3600   # 2-hour idle timeout
_MAX_SESSIONS        = 100         # Max simultaneous pinned sessions


class SessionAffinityManager:
    def __init__(self):
        # session_key → {credential_id, created_at, last_used, request_count}
        self._sessions: Dict[str, Dict] = {}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _evict_expired(self):
        now = time.monotonic()
        stale = [k for k, v in self._sessions.items()
                 if now - v["last_used"] > _SESSION_TTL_SECONDS]
        for k in stale:
            cred = self._sessions[k]["credential_id"]
            logger.info(f"Session affinity expired: key={k[:8]} cred={cred}")
            del self._sessions[k]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_pinned_credential(self, session_key: str) -> Optional[str]:
        """Return the pinned credential_id for this session, or None."""
        if not session_key:
            return None
        self._evict_expired()
        entry = self._sessions.get(session_key)
        if entry:
            entry["last_used"]    = time.monotonic()
            entry["request_count"] = entry.get("request_count", 0) + 1
            return entry["credential_id"]
        return None

    def pin_credential(self, session_key: str, credential_id: str):
        """Pin credential_id to this session."""
        if not session_key or not credential_id:
            return
        self._evict_expired()
        # Evict oldest if at capacity
        if len(self._sessions) >= _MAX_SESSIONS:
            oldest_key = min(self._sessions, key=lambda k: self._sessions[k]["last_used"])
            del self._sessions[oldest_key]
        is_new = session_key not in self._sessions
        self._sessions[session_key] = {
            "credential_id" : credential_id,
            "created_at"    : time.monotonic(),
            "last_used"     : time.monotonic(),
            "request_count" : 1,
        }
        if is_new:
            logger.info(f"Session pinned: key={session_key[:8]} → cred={credential_id}")

    def release_session(self, session_key: str):
        """Release a pinned session (e.g., credential became exhausted)."""
        if session_key in self._sessions:
            cred = self._sessions.pop(session_key)["credential_id"]
            logger.info(f"Session affinity released: key={session_key[:8]} was={cred}")

    def release_credential(self, credential_id: str):
        """Release ALL sessions pinned to a specific credential (on exhaustion)."""
        keys = [k for k, v in self._sessions.items()
                if v["credential_id"] == credential_id]
        for k in keys:
            del self._sessions[k]
        if keys:
            logger.info(f"Released {len(keys)} session(s) pinned to {credential_id}")

    def stats(self) -> dict:
        self._evict_expired()
        return {
            "active_sessions": len(self._sessions),
            "sessions": [
                {
                    "key"           : k[:8] + "...",
                    "credential_id" : v["credential_id"],
                    "request_count" : v.get("request_count", 0),
                    "age_minutes"   : round((time.monotonic() - v["created_at"]) / 60, 1),
                    "idle_minutes"  : round((time.monotonic() - v["last_used"]) / 60, 1),
                }
                for k, v in self._sessions.items()
            ],
        }


session_affinity = SessionAffinityManager()
