"""
Request Logger - Structured JSONL request logging like enowxai's request_logs.jsonl.
Logs every request with timing, model, provider, token counts, and errors.
"""
import json
import logging
import os
import time
from typing import Any, Dict, Optional
import asyncio

logger = logging.getLogger(__name__)

_LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
_LOG_PATH = os.path.join(_LOG_DIR, 'request_logs.jsonl')
_MAX_LOG_SIZE_MB = 50  # Rotate at 50 MB
_MAX_LOG_FILES = 5

_write_lock = asyncio.Lock()


def _ensure_log_dir():
    os.makedirs(_LOG_DIR, exist_ok=True)


def _rotate_if_needed():
    """Rotate log file if it exceeds MAX_LOG_SIZE_MB."""
    try:
        if not os.path.exists(_LOG_PATH):
            return
        size_mb = os.path.getsize(_LOG_PATH) / (1024 * 1024)
        if size_mb < _MAX_LOG_SIZE_MB:
            return
        # Rotate: shift existing backups
        for i in range(_MAX_LOG_FILES - 1, 0, -1):
            src = f"{_LOG_PATH}.{i}"
            dst = f"{_LOG_PATH}.{i + 1}"
            if os.path.exists(src):
                os.rename(src, dst)
        os.rename(_LOG_PATH, f"{_LOG_PATH}.1")
        logger.info("Request log rotated")
    except Exception as e:
        logger.warning(f"Log rotation failed: {e}")


class RequestLogger:
    """Writes structured JSONL log entries for every API request."""

    def __init__(self):
        _ensure_log_dir()

    def _write_entry(self, entry: Dict[str, Any]):
        """Synchronous write — called from async wrapper."""
        try:
            _rotate_if_needed()
            line = json.dumps(entry, ensure_ascii=False, default=str)
            with open(_LOG_PATH, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception as e:
            logger.warning(f"Failed to write request log: {e}")

    async def log_request(
        self,
        *,
        request_id: str,
        model: str,
        provider: str,
        credential_id: Optional[str],
        stream: bool,
        input_tokens: int,
        output_tokens: int,
        ttfb_ms: Optional[float],          # Time To First Byte
        total_ms: float,
        finish_reason: Optional[str],
        error: Optional[str] = None,
        thinking_blocks_stripped: int = 0,
        status: str = "ok",
    ):
        entry = {
            "ts": round(time.time(), 3),
            "id": request_id,
            "model": model,
            "provider": provider,
            "cred": credential_id,
            "stream": stream,
            "tokens_in": input_tokens,
            "tokens_out": output_tokens,
            "ttfb_ms": round(ttfb_ms, 1) if ttfb_ms is not None else None,
            "total_ms": round(total_ms, 1),
            "finish": finish_reason,
            "thinking_stripped": thinking_blocks_stripped if thinking_blocks_stripped else None,
            "status": status,
            "error": error,
        }
        # Remove None values to keep logs compact
        entry = {k: v for k, v in entry.items() if v is not None}

        async with _write_lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._write_entry, entry)

    def get_recent(self, n: int = 100) -> list:
        """Read last N log entries (for dashboard display)."""
        entries = []
        try:
            if not os.path.exists(_LOG_PATH):
                return []
            with open(_LOG_PATH, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            for line in lines[-n:]:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Failed to read request logs: {e}")
        return entries

    def get_stats_summary(self) -> Dict[str, Any]:
        """Aggregate stats from recent log entries."""
        try:
            entries = self.get_recent(1000)
            if not entries:
                return {}

            total = len(entries)
            errors = sum(1 for e in entries if e.get('status') != 'ok')
            tokens_out = sum(e.get('tokens_out', 0) for e in entries)
            tokens_in = sum(e.get('tokens_in', 0) for e in entries)
            latencies = [e['total_ms'] for e in entries if 'total_ms' in e]
            avg_latency = sum(latencies) / len(latencies) if latencies else 0
            thinking_stripped = sum(e.get('thinking_stripped', 0) for e in entries)

            models = {}
            for e in entries:
                m = e.get('model', 'unknown')
                models[m] = models.get(m, 0) + 1

            return {
                "total_requests": total,
                "error_count": errors,
                "success_rate": round((total - errors) / total * 100, 1) if total else 0,
                "total_tokens_in": tokens_in,
                "total_tokens_out": tokens_out,
                "avg_latency_ms": round(avg_latency, 1),
                "thinking_blocks_stripped": thinking_stripped,
                "models": models,
            }
        except Exception as e:
            logger.warning(f"Failed to compute log stats: {e}")
            return {}


request_logger = RequestLogger()
