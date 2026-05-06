"""
Main Web Service for CodeBuddy2API
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.codebuddy_router import router as codebuddy_router, lifecycle_manager
from src.codebuddy_auth_router import router as codebuddy_auth_router
from src.settings_router import router as settings_router
from src.frontend_router import router as frontend_router

from config import get_server_host, get_server_port, get_log_level

logging.basicConfig(
    level=getattr(logging, get_log_level().upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

_server_start_time: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _server_start_time
    _server_start_time = time.time()
    logger.info("Starting CodeBuddy2API Service")
    try:
        await lifecycle_manager.startup()
        yield
    finally:
        await lifecycle_manager.shutdown()
        logger.info("CodeBuddy2API Service stopped")


app = FastAPI(
    title="CodeBuddy2API",
    description="CodeBuddy API proxy with OpenAI-compatible interface",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    frontend_router,
    tags=["Frontend"]
)

app.include_router(
    codebuddy_auth_router,
    prefix="/codebuddy",
    tags=["CodeBuddy OAuth2 Authentication"]
)

app.include_router(
    codebuddy_router,
    prefix="/codebuddy",
    tags=["CodeBuddy Compatible API"]
)

app.include_router(
    settings_router,
    prefix="/api",
    tags=["Settings Management"]
)


@app.get("/health")
async def health_check():
    from src.codebuddy_token_manager import codebuddy_token_manager as tm

    creds_info = tm.get_credentials_info()
    total = len(creds_info)
    healthy = sum(
        1 for c in creds_info
        if not c.get("is_expired") and not c.get("is_exhausted") and not c.get("is_disabled")
    )
    expired = sum(1 for c in creds_info if c.get("is_expired"))
    exhausted = sum(1 for c in creds_info if c.get("is_exhausted") and not c.get("is_expired"))
    disabled = sum(1 for c in creds_info if c.get("is_disabled"))

    if total == 0 or healthy == 0:
        status = "critical"
    elif healthy / total < 0.2:
        status = "degraded"
    else:
        status = "healthy"

    uptime_seconds = round(time.time() - _server_start_time, 1) if _server_start_time else 0.0

    return {
        "status": status,
        "service": "codebuddy2api",
        "total_credentials": total,
        "healthy_credentials": healthy,
        "expired_credentials": expired,
        "exhausted_credentials": exhausted,
        "disabled_credentials": disabled,
        "server_uptime_seconds": uptime_seconds,
    }


@app.get("/")
async def root():
    return {
        "service": "CodeBuddy2API",
        "version": "2.0.0",
        "description": "CodeBuddy API proxy with OpenAI-compatible interface",
        "endpoints": {
            "models": "/codebuddy/v1/models",
            "chat": "/codebuddy/v1/chat/completions",
            "credentials": "/codebuddy/v1/credentials",
            "stats": "/codebuddy/v1/stats",
            "filter_reload": "/api/filters/reload",
            "auth_start": "/codebuddy/auth/start",
            "auth_poll": "/codebuddy/auth/poll",
            "auth_callback": "/codebuddy/auth/callback",
            "get_settings": "/api/settings",
            "save_settings": "/api/settings"
        }
    }


if __name__ == "__main__":
    from hypercorn.asyncio import serve
    from hypercorn.config import Config

    port = get_server_port()
    host = get_server_host()

    logger.info("=" * 60)
    logger.info("Starting CodeBuddy2API")
    logger.info("=" * 60)
    logger.info(f"Main Service: http://{host}:{port}")
    logger.info("=" * 60)
    logger.info("Web Interface:")
    logger.info(f"   Admin Panel: http://{host}:{port}/")
    logger.info("=" * 60)
    logger.info("API Endpoints:")
    logger.info(f"   Models: GET http://{host}:{port}/codebuddy/v1/models")
    logger.info(f"   Chat: POST http://{host}:{port}/codebuddy/v1/chat/completions")
    logger.info(f"   Credentials: GET http://{host}:{port}/codebuddy/v1/credentials")
    logger.info(f"   Stats: GET http://{host}:{port}/codebuddy/v1/stats")
    logger.info(f"   Filter Reload: POST http://{host}:{port}/api/filters/reload")
    logger.info("=" * 60)
    logger.info("Authentication:")
    logger.info("   Set CODEBUDDY_PASSWORD environment variable")
    logger.info("   Use Bearer token in Authorization header")
    logger.info("=" * 60)

    config = Config()
    config.bind = [f"{host}:{port}", f"[::]:{port}"]
    config.accesslog = None
    config.errorlog = "-"
    config.loglevel = "INFO"
    config.use_colors = True

    asyncio.run(serve(app, config))
