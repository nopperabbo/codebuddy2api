"""
Main Web Service for Kiro Gateway (formerly CodeBuddy2API)
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.settings_router import router as settings_router
from src.frontend_router import router as frontend_router
from src.kiro_router import router as kiro_router

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
    logger.info("Starting Kiro Gateway Service")

    try:
        yield
    finally:
        from src.kiro_router import close_kiro_http_client
        await close_kiro_http_client()
        logger.info("Kiro Gateway Service stopped")


app = FastAPI(
    title="Kiro Gateway",
    description="API proxy for Amazon Q Developer with OpenAI-compatible interface",
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
    kiro_router,
    prefix="/kiro",
    tags=["Kiro (Amazon Q) Compatible API"]
)

app.include_router(
    settings_router,
    prefix="/api",
    tags=["Settings Management"]
)

@app.get("/health", tags=["Health"])
async def health_check():
    """Simple health check endpoint."""
    uptime = time.time() - _server_start_time if _server_start_time else 0
    return {
        "status": "healthy",
        "service": "kiro-gateway",
        "uptime_seconds": round(uptime, 2)
    }

if __name__ == "__main__":
    import uvicorn
    host = get_server_host()
    port = get_server_port()
    
    logger.info("="*60)
    logger.info("Starting Kiro Gateway")
    logger.info("="*60)
    logger.info(f"Main Service: http://{host}:{port}")
    logger.info("="*60)
    logger.info("API Endpoints:")
    logger.info(f"   Models: GET http://{host}:{port}/kiro/v1/models")
    logger.info(f"   Chat: POST http://{host}:{port}/kiro/v1/chat/completions")
    logger.info("="*60)
    
    uvicorn.run(
        "web:app",
        host=host,
        port=port,
        log_level=get_log_level().lower(),
        reload=False
    )
