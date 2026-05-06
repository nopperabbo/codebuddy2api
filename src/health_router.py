import time
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from src.circuit_breaker import CircuitBreakerManager, CircuitState
from src.health_db import HealthDatabase
from src.alerting import AlertManager

health_router = APIRouter(prefix="/api/health", tags=["health"])


@health_router.get("/credentials")
async def get_credentials_health():
    cb = CircuitBreakerManager.get_instance()
    db = HealthDatabase.get_instance()

    all_states = cb.get_all_states()
    result = []

    for cred_id, state_data in all_states.items():
        stats = await db.get_credential_stats(cred_id, window_seconds=3600.0)
        result.append({
            **state_data,
            "stats_1h": stats,
        })

    return {
        "credentials": result,
        "summary": cb.get_summary(),
        "timestamp": time.time(),
    }


@health_router.get("/credentials/{credential_id}")
async def get_credential_detail(credential_id: str):
    cb = CircuitBreakerManager.get_instance()
    db = HealthDatabase.get_instance()

    state = cb.get_circuit_state(credential_id)
    history = await db.get_credential_history(credential_id, limit=50)
    stats = await db.get_credential_stats(credential_id)
    failure_rate = await db.get_failure_rate_history(credential_id)

    return {
        "state": state,
        "history": history,
        "stats_1h": stats,
        "failure_rate_buckets": failure_rate,
    }


@health_router.get("/alerts")
async def get_alerts(
    active_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200)
):
    db = HealthDatabase.get_instance()

    if active_only:
        alerts = await db.get_active_alerts()
    else:
        alerts = await db.get_recent_alerts(limit=limit)

    alert_mgr = AlertManager.get_instance()

    return {
        "alerts": alerts,
        "alert_manager_status": alert_mgr.get_status(),
    }


@health_router.get("/summary")
async def get_health_summary():
    cb = CircuitBreakerManager.get_instance()
    db = HealthDatabase.get_instance()
    alert_mgr = AlertManager.get_instance()

    summary = cb.get_summary()
    active_alerts = await db.get_active_alerts()

    return {
        "circuit_breaker": summary,
        "active_alerts_count": len(active_alerts),
        "alert_manager": alert_mgr.get_status(),
        "timestamp": time.time(),
    }


@health_router.post("/credentials/{credential_id}/force-close")
async def force_close_circuit(credential_id: str):
    cb = CircuitBreakerManager.get_instance()
    await cb.force_close(credential_id)
    return {"status": "ok", "message": f"Circuit for {credential_id[:8]}... forced closed"}


@health_router.post("/credentials/{credential_id}/force-open")
async def force_open_circuit(credential_id: str):
    cb = CircuitBreakerManager.get_instance()
    await cb.force_open(credential_id)
    return {"status": "ok", "message": f"Circuit for {credential_id[:8]}... forced open"}


@health_router.post("/cleanup")
async def cleanup_old_data(retention_hours: int = Query(72, ge=1, le=720)):
    db = HealthDatabase.get_instance()
    await db.cleanup_old_events(retention_hours=retention_hours)
    return {"status": "ok", "message": f"Cleaned events older than {retention_hours}h"}
