"""
Response Deduplication Cache
Caches recent responses to avoid wasting quota on OpenCode retries.
Uses SHA256 hash of (model + messages) as cache key with LRU eviction.
"""
import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 15    # Response valid for 15s (covers OpenCode retry window)
_MAX_CACHE_SIZE    = 200   # LRU limit


class ResponseCache:
    def __init__(self):
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._hits   = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _make_key(self, model: str, messages: List[Dict]) -> str:
        try:
            raw = json.dumps({"model": model, "messages": messages},
                             sort_keys=True, ensure_ascii=False)
            return hashlib.sha256(raw.encode()).hexdigest()
        except Exception:
            return ""

    def _evict_expired(self):
        now = time.monotonic()
        stale = [k for k, v in self._cache.items()
                 if now - v["ts"] > _CACHE_TTL_SECONDS]
        for k in stale:
            del self._cache[k]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_cache(self, messages: List[Dict]) -> bool:
        """Skip caching when tool results are present — they have side-effects."""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "tool":
                return False
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        return False
        return True

    def get(self, model: str, messages: List[Dict]) -> Optional[str]:
        """Return cached full SSE text, or None on miss."""
        key = self._make_key(model, messages)
        if not key:
            return None
        self._evict_expired()
        entry = self._cache.get(key)
        if entry and (time.monotonic() - entry["ts"]) < _CACHE_TTL_SECONDS:
            self._cache.move_to_end(key)
            self._hits += 1
            logger.info(f"Cache HIT (dedup save) model={model} key={key[:8]} hits={self._hits}")
            return entry["response"]
        self._misses += 1
        return None

    def put(self, model: str, messages: List[Dict], response: str):
        """Store full SSE response text."""
        key = self._make_key(model, messages)
        if not key or not response:
            return
        self._evict_expired()
        if len(self._cache) >= _MAX_CACHE_SIZE:
            self._cache.popitem(last=False)   # evict LRU
        self._cache[key] = {"response": response, "ts": time.monotonic()}
        logger.debug(f"Cache stored model={model} key={key[:8]}")

    def stats(self) -> Dict[str, Any]:
        self._evict_expired()
        total = self._hits + self._misses
        return {
            "cached_entries" : len(self._cache),
            "cache_hits"     : self._hits,
            "cache_misses"   : self._misses,
            "hit_rate_pct"   : round(self._hits / max(total, 1) * 100, 1),
        }

    def clear(self):
        self._cache.clear()
        logger.info("Response cache cleared")


response_cache = ResponseCache()
