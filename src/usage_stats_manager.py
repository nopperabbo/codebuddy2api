"""
Usage Statistics Manager - Tracks per-key stats, latency, and persists to disk.
"""
import json
import os
import tempfile
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone

_STATS_FILE = os.path.join(os.path.dirname(__file__), '..', 'stats.json')
_PERSIST_INTERVAL = 100  # persist every N requests
_HOURLY_RETENTION_HOURS = 72


def atomic_write_json(filepath: str, data: dict):
    dir_path = os.path.dirname(filepath) or '.'
    fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, filepath)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class UsageStatsManager:
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super(UsageStatsManager, cls).__new__(cls)
                    inst.model_usage = defaultdict(int)
                    inst.credential_usage = defaultdict(int)
                    # Per-key detailed tracking
                    inst.key_stats = defaultdict(lambda: {
                        "total_requests": 0,
                        "failed_requests": 0,
                        "last_used_at": None,
                    })
                    # Latency tracking per model
                    inst.model_latency = defaultdict(lambda: {
                        "ttfb_sum": 0.0,
                        "ttfb_count": 0,
                        "total_sum": 0.0,
                        "total_count": 0,
                    })
                    # Hourly stats: {"2026-05-04T19": {"requests": N, "failures": N, "per_key_failures": {"cred_id": N}}}
                    inst.hourly_stats = {}
                    inst._total_requests = 0
                    inst._load_from_disk()
                    cls._instance = inst
        return cls._instance

    def _load_from_disk(self):
        try:
            if os.path.exists(_STATS_FILE):
                with open(_STATS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.model_usage = defaultdict(int, data.get("model_usage", {}))
                self.credential_usage = defaultdict(int, data.get("credential_usage", {}))
                for k, v in data.get("key_stats", {}).items():
                    self.key_stats[k] = v
                for k, v in data.get("model_latency", {}).items():
                    self.model_latency[k] = v
                self.hourly_stats = data.get("hourly_stats", {})
                self._total_requests = data.get("total_requests", 0)
                self._prune_hourly_stats()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to load stats from disk: {e}")

    def _maybe_persist(self):
        self._total_requests += 1
        if self._total_requests % _PERSIST_INTERVAL == 0:
            self._persist_to_disk()

    def _persist_to_disk(self):
        try:
            data = {
                "model_usage": dict(self.model_usage),
                "credential_usage": dict(self.credential_usage),
                "key_stats": dict(self.key_stats),
                "model_latency": dict(self.model_latency),
                "hourly_stats": self.hourly_stats,
                "total_requests": self._total_requests,
                "persisted_at": int(time.time()),
            }
            atomic_write_json(_STATS_FILE, data)
        except Exception:
            pass

    def record_model_usage(self, model_name: str):
        with self._lock:
            self.model_usage[model_name] += 1

    def record_credential_usage(self, credential_id: str):
        with self._lock:
            self.credential_usage[credential_id] += 1
            ks = self.key_stats[credential_id]
            ks["total_requests"] = ks.get("total_requests", 0) + 1
            ks["last_used_at"] = int(time.time())
            self._record_hourly_request()
            self._maybe_persist()

    def record_credential_failure(self, credential_id: str):
        with self._lock:
            ks = self.key_stats[credential_id]
            ks["failed_requests"] = ks.get("failed_requests", 0) + 1
            self._record_hourly_failure(credential_id)

    def record_latency(self, model: str, ttfb: float, total: float):
        with self._lock:
            ml = self.model_latency[model]
            ml["ttfb_sum"] = ml.get("ttfb_sum", 0.0) + ttfb
            ml["ttfb_count"] = ml.get("ttfb_count", 0) + 1
            ml["total_sum"] = ml.get("total_sum", 0.0) + total
            ml["total_count"] = ml.get("total_count", 0) + 1

    def get_stats(self):
        with self._lock:
            latency_summary = {}
            for model, ml in self.model_latency.items():
                ttfb_count = ml.get("ttfb_count", 0)
                total_count = ml.get("total_count", 0)
                latency_summary[model] = {
                    "avg_ttfb_ms": round(ml.get("ttfb_sum", 0) / ttfb_count * 1000, 1) if ttfb_count else 0,
                    "avg_total_ms": round(ml.get("total_sum", 0) / total_count * 1000, 1) if total_count else 0,
                    "request_count": total_count,
                }
            return {
                "model_usage": dict(self.model_usage),
                "credential_usage": dict(self.credential_usage),
                "key_stats": dict(self.key_stats),
                "model_latency": latency_summary,
                "total_requests": self._total_requests,
            }

    def get_key_stats(self, credential_id: str) -> dict:
        with self._lock:
            return dict(self.key_stats.get(credential_id, {
                "total_requests": 0,
                "failed_requests": 0,
                "last_used_at": 0,
            }))

    @staticmethod
    def _current_hour_key() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")

    def _ensure_hourly_bucket(self, hour_key: str) -> dict:
        if hour_key not in self.hourly_stats:
            self.hourly_stats[hour_key] = {"requests": 0, "failures": 0, "per_key_failures": {}}
        return self.hourly_stats[hour_key]

    def _record_hourly_request(self):
        bucket = self._ensure_hourly_bucket(self._current_hour_key())
        bucket["requests"] += 1

    def _record_hourly_failure(self, credential_id: str):
        bucket = self._ensure_hourly_bucket(self._current_hour_key())
        bucket["failures"] += 1
        pkf = bucket.setdefault("per_key_failures", {})
        pkf[credential_id] = pkf.get(credential_id, 0) + 1

    def _prune_hourly_stats(self):
        cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
        from datetime import timedelta
        cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=_HOURLY_RETENTION_HOURS)
        cutoff_key = cutoff_dt.strftime("%Y-%m-%dT%H")
        stale = [k for k in self.hourly_stats if k < cutoff_key]
        for k in stale:
            del self.hourly_stats[k]

    def get_hourly_history(self, hours: int = 24) -> dict:
        with self._lock:
            self._prune_hourly_stats()
            from datetime import timedelta
            cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
            cutoff_key = cutoff_dt.strftime("%Y-%m-%dT%H")
            result = {}
            for k in sorted(self.hourly_stats.keys()):
                if k >= cutoff_key:
                    result[k] = self.hourly_stats[k]

            all_key_failures = defaultdict(int)
            for bucket in result.values():
                for cid, cnt in bucket.get("per_key_failures", {}).items():
                    all_key_failures[cid] += cnt
            failure_ranking = sorted(all_key_failures.items(), key=lambda x: x[1], reverse=True)[:20]

            return {
                "hours_requested": hours,
                "buckets": result,
                "failure_ranking": [{"credential_id": cid, "failures": cnt} for cid, cnt in failure_ranking],
            }

    def force_persist(self):
        with self._lock:
            self._persist_to_disk()


usage_stats_manager = UsageStatsManager()
