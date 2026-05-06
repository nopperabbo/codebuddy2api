"""
Settings Router - Configuration management and filter hot-reload.
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any

from .auth import authenticate
from config import get_active_config, update_settings
from .usage_stats_manager import usage_stats_manager
from .keyword_replacer import load_filters, get_filter_count

logger = logging.getLogger(__name__)
router = APIRouter()

SETTING_LABELS = {
    "CODEBUDDY_HOST": "Server host address",
    "CODEBUDDY_PORT": "Server port",
    "CODEBUDDY_PASSWORD": "API access password",
    "CODEBUDDY_API_ENDPOINT": "CodeBuddy official API endpoint",
    "CODEBUDDY_CREDS_DIR": "Credentials file directory",
    "CODEBUDDY_LOG_LEVEL": "Log level",
    "CODEBUDDY_MODELS": "Available models (comma-separated)",
    "CODEBUDDY_ROTATION_COUNT": "Credential rotation frequency (N requests/credential, 0 to disable)"
}


class Settings(BaseModel):
    settings: Dict[str, Any]


@router.get("/settings", summary="Get all current active settings and labels")
async def get_settings(_token: str = Depends(authenticate)):
    try:
        return {
            "settings": get_active_config(),
            "labels": SETTING_LABELS
        }
    except Exception as e:
        logger.error(f"Error retrieving active config: {e}")
        raise HTTPException(status_code=500, detail="Could not retrieve settings.")


@router.post("/settings", summary="Save and hot-reload settings")
async def save_settings(new_settings: Settings, _token: str = Depends(authenticate)):
    try:
        update_settings(new_settings.settings)
        return {"message": "Settings saved and hot-reloaded successfully!"}
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        raise HTTPException(status_code=500, detail="Could not save settings.")


@router.get("/stats", summary="Get usage statistics")
async def get_usage_stats(_token: str = Depends(authenticate)):
    try:
        stats = usage_stats_manager.get_stats()
        stats["filter_count"] = get_filter_count()
        return stats
    except Exception as e:
        logger.error(f"Error retrieving usage stats: {e}")
        raise HTTPException(status_code=500, detail="Could not retrieve usage statistics.")


@router.post("/filters/reload", summary="Hot-reload filter patterns from config/filters.json")
async def reload_filters(_token: str = Depends(authenticate)):
    try:
        load_filters()
        counts = get_filter_count()
        return {
            "message": "Filters reloaded successfully",
            "filter_count": counts
        }
    except Exception as e:
        logger.error(f"Error reloading filters: {e}")
        raise HTTPException(status_code=500, detail="Could not reload filters.")
