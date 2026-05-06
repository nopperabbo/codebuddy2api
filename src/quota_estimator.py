"""
Credential Quota Estimator
Tracks estimated daily token usage per credential to proactively
de-prioritize credentials approaching their daily limit — before
they hit quota errors from CodeBuddy.
"""
import json
import logging
import os
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)

_STATE_FILE = os.path.join(os.path.dirname(__file__), '..', 'logs', 'quota_state.json')

# Tune these based on your actual CodeBuddy tier
DEFAULT_DAILY_TOKEN_BUDGET = 500_000  # Conservative: 500K tokens/day per account

WARNING_THRESHOLD  = 0.80   # 80%  → start deprioritizing
CRITICAL_THRESHOLD = 0.95   # 95%  → almost never pick this credential
_SAVE_EVERY_N      = 10     # Persist state every N token records to limit I/O


class QuotaEstimator:
    def __init__(self):
        # credential_id → {tokens_today, date, requests}
        self._usage: Dict[str, Dict[str, Any]] = {}
        self._pending_saves = 0
        self._load()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _today() -> str:
        import datetime
        return datetime.date.today().isoformat()

    def _load(self):
        try:
            if os.path.exists(_STATE_FILE):
                with open(_STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                today = self._today()
                # Discard yesterday's data automatically
                self._usage = {k: v for k, v in data.items()
                               if v.get("date") == today}
                logger.info(f"Quota state loaded: {len(self._usage)} creds tracked today")
        except Exception as e:
            logger.warning(f"Could not load quota state: {e}")
            self._usage = {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
            tmp = _STATE_FILE + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self._usage, f, ensure_ascii=False)
            os.replace(tmp, _STATE_FILE)
        except Exception as e:
            logger.warning(f"Could not save quota state: {e}")

    def _get_entry(self, credential_id: str) -> Dict[str, Any]:
        today = self._today()
        entry = self._usage.setdefault(credential_id, {
            "tokens_today": 0, "date": today, "requests": 0
        })
        if entry.get("date") != today:
            # New day → reset
            entry["tokens_today"] = 0
            entry["date"]         = today
            entry["requests"]     = 0
        return entry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_usage(self, credential_id: str, tokens_in: int, tokens_out: int):
        """Record token consumption for a credential."""
        if not credential_id:
            return
        entry = self._get_entry(credential_id)
        entry["tokens_today"] += tokens_in + tokens_out
        entry["requests"]      = entry.get("requests", 0) + 1
        self._pending_saves   += 1
        if self._pending_saves >= _SAVE_EVERY_N:
            self._save()
            self._pending_saves = 0

    def get_usage_fraction(self, credential_id: str,
                           daily_budget: int = DEFAULT_DAILY_TOKEN_BUDGET) -> float:
        """Returns 0.0–1.0 of estimated daily budget consumed."""
        entry = self._usage.get(credential_id)
        if not entry or entry.get("date") != self._today():
            return 0.0
        return min(entry["tokens_today"] / max(daily_budget, 1), 1.0)

    def get_quota_score(self, credential_id: str,
                        daily_budget: int = DEFAULT_DAILY_TOKEN_BUDGET) -> float:
        """
        Multiplier 0.0–1.0 for credential selection weight.
        1.0 = full quota, 0.05 = nearly exhausted → almost never selected.
        """
        fraction = self.get_usage_fraction(credential_id, daily_budget)
        if fraction >= CRITICAL_THRESHOLD:
            return 0.05
        if fraction >= WARNING_THRESHOLD:
            # Linear decay from 1.0 → 0.1 between WARNING and CRITICAL
            ratio = (fraction - WARNING_THRESHOLD) / (CRITICAL_THRESHOLD - WARNING_THRESHOLD)
            return max(0.1, 1.0 - ratio * 0.9)
        return 1.0

    def get_all_usage(self, daily_budget: int = DEFAULT_DAILY_TOKEN_BUDGET) -> Dict[str, Any]:
        today = self._today()
        result = {}
        for cid, entry in self._usage.items():
            if entry.get("date") != today:
                continue
            fraction = self.get_usage_fraction(cid, daily_budget)
            result[cid] = {
                "tokens_today" : entry["tokens_today"],
                "requests"     : entry.get("requests", 0),
                "usage_pct"    : round(fraction * 100, 1),
                "quota_score"  : round(self.get_quota_score(cid, daily_budget), 2),
                "status"       : ("critical" if fraction >= CRITICAL_THRESHOLD
                                  else "warning" if fraction >= WARNING_THRESHOLD
                                  else "ok"),
            }
        return result

    def flush(self):
        """Force persist state to disk."""
        self._save()
        self._pending_saves = 0


quota_estimator = QuotaEstimator()
