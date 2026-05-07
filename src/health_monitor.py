"""
Health Monitor - Background service that periodically pings each provider
to track latency, availability, and error rates. Updates credential scores
for weighted rotation decisions.

Inspired by enowxai's health tracking approach.
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# How often to run health checks (seconds)
HEALTH_CHECK_INTERVAL = 300   # 5 minutes
HEALTH_CHECK_TIMEOUT = 20.0   # seconds per ping
HEALTH_CHECK_MODEL = "claude-haiku-4.5"  # cheapest/fastest model for pings

# Per-provider health state
_provider_health: Dict[str, Dict[str, Any]] = {}
_credential_health: Dict[str, Dict[str, Any]] = {}  # keyed by credential_id
_monitor_task: Optional[asyncio.Task] = None
_running = False


def get_provider_health(provider: str) -> Dict[str, Any]:
    return _provider_health.get(provider, {
        "status": "unknown",
        "last_check": None,
        "latency_ms": None,
        "consecutive_failures": 0,
        "success_rate": 100.0,
    })


def get_all_health() -> Dict[str, Any]:
    return {
        "providers": dict(_provider_health),
        "last_updated": time.time(),
    }


def mark_credential_success(credential_id: str, latency_ms: float):
    """Called by router on each successful request."""
    h = _credential_health.setdefault(credential_id, {
        "successes": 0, "failures": 0,
        "total_latency_ms": 0.0, "last_used": 0,
    })
    h["successes"] += 1
    h["total_latency_ms"] += latency_ms
    h["last_used"] = time.time()
    h["consecutive_failures"] = 0


def mark_credential_failure(credential_id: str, error: str = ""):
    """Called by router on each failed request."""
    h = _credential_health.setdefault(credential_id, {
        "successes": 0, "failures": 0,
        "total_latency_ms": 0.0, "last_used": 0,
        "consecutive_failures": 0,
    })
    h["failures"] += 1
    h["last_used"] = time.time()
    h["consecutive_failures"] = h.get("consecutive_failures", 0) + 1
    if error:
        h["last_error"] = error


def get_credential_score(credential_id: str) -> float:
    """
    Score 0-1 for a credential. Higher = healthier / prefer for routing.
    Used by token manager for weighted selection.
    """
    h = _credential_health.get(credential_id)
    if not h:
        return 0.5  # Unknown: neutral score

    total = h["successes"] + h["failures"]
    if total == 0:
        return 0.5

    success_rate = h["successes"] / total
    # Penalise consecutive failures heavily
    consec_penalty = min(h.get("consecutive_failures", 0) * 0.1, 0.5)
    # Staleness bonus: prefer credentials used less recently (spread load)
    staleness = min((time.time() - h.get("last_used", 0)) / 3600, 1.0)
    staleness_bonus = staleness * 0.1

    score = success_rate - consec_penalty + staleness_bonus
    return max(0.01, min(1.0, score))


async def _do_health_checks():
    """
    Passive health check — derives provider status from real request
    tracking (mark_credential_success/failure) rather than sending
    synthetic pings that waste quota and cause 400 errors.
    """
    h = _credential_health
    if not h:
        _provider_health["codebuddy"] = {
            "status": "unknown",
            "last_check": time.time(),
            "latency_ms": None,
            "consecutive_failures": 0,
            "note": "No traffic yet",
        }
        return

    total_s = sum(v.get("successes", 0) for v in h.values())
    total_f = sum(v.get("failures",  0) for v in h.values())
    total   = total_s + total_f
    success_rate = total_s / total if total > 0 else 1.0

    # Average latency across credentials that have data
    latencies = [
        v["total_latency_ms"] / v["successes"]
        for v in h.values()
        if v.get("successes", 0) > 0
    ]
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else None

    if success_rate >= 0.9:
        status = "healthy"
    elif success_rate >= 0.5:
        status = "degraded"
    else:
        status = "down"

    _provider_health["codebuddy"] = {
        "status"       : status,
        "last_check"   : time.time(),
        "latency_ms"   : avg_latency,
        "success_rate" : round(success_rate * 100, 1),
        "total_requests": total,
        "note": "Derived from real traffic (no synthetic pings)",
    }
    logger.info(f"Health snapshot: codebuddy {status} "
                f"success_rate={success_rate*100:.0f}% "
                f"avg_latency={avg_latency}ms total={total}")


async def _run_health_checks():
    """Periodic health snapshot loop — passive, no synthetic pings."""
    global _running
    logger.info("Health monitor started")
    while _running:
        try:
            await _do_health_checks()
        except Exception as e:
            logger.error(f"Health check loop error: {e}")
        await asyncio.sleep(HEALTH_CHECK_INTERVAL)


async def startup():
    """Start the background health monitor."""
    global _monitor_task, _running
    if _running:
        return
    _running = True
    _monitor_task = asyncio.create_task(_run_health_checks())
    logger.info("Health monitor task created")


async def shutdown():
    """Stop the health monitor."""
    global _monitor_task, _running
    _running = False
    if _monitor_task and not _monitor_task.done():
        _monitor_task.cancel()
        try:
            await _monitor_task
        except asyncio.CancelledError:
            pass
    _monitor_task = None
    logger.info("Health monitor stopped")
