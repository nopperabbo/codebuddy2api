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

import httpx

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


async def _ping_codebuddy_endpoint(api_url: str, bearer_token: str) -> Optional[float]:
    """
    Send a minimal chat completion to codebuddy and measure latency.
    Returns latency_ms or None on failure.
    """
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(verify=False, timeout=HEALTH_CHECK_TIMEOUT) as client:
            resp = await client.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {bearer_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": HEALTH_CHECK_MODEL,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 5,
                    "stream": False,
                }
            )
            elapsed_ms = (time.monotonic() - start) * 1000
            if resp.status_code == 200:
                return elapsed_ms
            else:
                logger.debug(f"Health ping got {resp.status_code}: {resp.text[:100]}")
                return None
    except Exception as e:
        logger.debug(f"Health ping error: {e}")
        return None


async def _run_health_checks():
    """Main health check loop."""
    global _running
    logger.info("Health monitor started")

    while _running:
        try:
            await _do_health_checks()
        except Exception as e:
            logger.error(f"Health check loop error: {e}")
        await asyncio.sleep(HEALTH_CHECK_INTERVAL)


async def _do_health_checks():
    """Run one round of health checks across all providers."""
    from config import get_codebuddy_api_endpoint
    from src.codebuddy_token_manager import codebuddy_token_manager

    api_url = f"{get_codebuddy_api_endpoint()}/v2/chat/completions"
    creds = codebuddy_token_manager.get_all_credentials()

    if not creds:
        logger.debug("Health monitor: no credentials to check")
        return

    # Sample a few credentials to check — not all 500+ of them
    import random
    sample = random.sample(creds, min(3, len(creds)))

    results = []
    for cred in sample:
        bearer = cred.get("bearer_token")
        if not bearer:
            continue
        latency = await _ping_codebuddy_endpoint(api_url, bearer)
        results.append(latency)

    # Update provider health
    successful = [l for l in results if l is not None]
    failed = len(results) - len(successful)

    prev = _provider_health.get("codebuddy", {"consecutive_failures": 0, "successes": 0, "failures": 0})
    if successful:
        avg_latency = sum(successful) / len(successful)
        prev_fails = prev.get("consecutive_failures", 0)
        _provider_health["codebuddy"] = {
            "status": "healthy",
            "last_check": time.time(),
            "latency_ms": round(avg_latency, 1),
            "consecutive_failures": 0,
            "successes": prev.get("successes", 0) + len(successful),
            "failures": prev.get("failures", 0) + failed,
        }
        logger.info(f"Health check: codebuddy OK — avg {avg_latency:.0f}ms ({len(successful)}/{len(results)} passed)")
    else:
        consec = prev.get("consecutive_failures", 0) + 1
        _provider_health["codebuddy"] = {
            "status": "degraded" if consec < 3 else "down",
            "last_check": time.time(),
            "latency_ms": None,
            "consecutive_failures": consec,
            "successes": prev.get("successes", 0),
            "failures": prev.get("failures", 0) + len(results),
        }
        logger.warning(f"Health check: codebuddy FAILED ({consec} consecutive failures)")


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
