"""
Kiro API Client - Handles communication with Kiro (Amazon Q Developer) API.

Uses the ksk_ API key format DIRECTLY as a Bearer token for headless authentication.
No token exchange is needed - the ksk_ key is used as-is with a tokentype: API_KEY header.

Auth flow:
1. Use ksk_ key directly as Bearer token in Authorization header
2. Add tokentype: API_KEY header to identify API key authentication
3. Make API calls to https://q.{region}.amazonaws.com/generateAssistantResponse

Reference: https://github.com/hank9999/kiro.rs/commit/fbc5f4bcd0eb6d7e645ec3c6331f7b1bb9b664ba
"""
import asyncio
import hashlib
import json
import os
import uuid
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

import httpx

logger = logging.getLogger(__name__)

# Kiro API endpoint
KIRO_API_HOST_TEMPLATE = "https://q.{region}.amazonaws.com"
KIRO_CHAT_PATH = "/generateAssistantResponse"

# Default region
DEFAULT_KIRO_REGION = "us-east-1"


def get_machine_fingerprint() -> str:
    """Generate a unique machine fingerprint for User-Agent."""
    try:
        import socket
        import getpass
        hostname = socket.gethostname()
        username = getpass.getuser()
        unique_string = f"{hostname}-{username}-kiro-gateway"
        return hashlib.sha256(unique_string.encode()).hexdigest()[:16]
    except Exception:
        return hashlib.sha256(b"default-kiro-gateway").hexdigest()[:16]


# Kiro model ID mapping (friendly name -> Kiro internal model ID)
# IMPORTANT: Kiro API uses DOT format (claude-opus-4.7), NOT DASH (claude-opus-4-7)
KIRO_MODEL_MAP = {
    # Claude Opus 4.7
    "claude-opus-4.7": "claude-opus-4.7",
    "claude-opus-4-7": "claude-opus-4.7",
    # Claude Sonnet 4.7
    "claude-sonnet-4.7": "claude-sonnet-4.7",
    "claude-sonnet-4-7": "claude-sonnet-4.7",
    # Claude Opus 4.5
    "claude-opus-4.5": "claude-opus-4.5",
    "claude-opus-4-5": "claude-opus-4.5",
    # Claude Sonnet 4.5
    "claude-sonnet-4.5": "claude-sonnet-4.5",
    "claude-sonnet-4-5": "claude-sonnet-4.5",
    # Claude Haiku 4.5
    "claude-haiku-4.5": "claude-haiku-4.5",
    "claude-haiku-4-5": "claude-haiku-4.5",
    # Claude Sonnet 4
    "claude-sonnet-4": "claude-sonnet-4",
    # Claude 3.7 Sonnet (legacy — needs special internal ID)
    "claude-3.7-sonnet": "claude-3.7-sonnet",
    "claude-3-7-sonnet": "claude-3.7-sonnet",
    "claude-3.7-sonnet-20250219": "claude-3.7-sonnet",
    # DeepSeek
    "deepseek-v3.2": "deepseek-v3.2",
    "deepseek-v3-2": "deepseek-v3.2",
    "deepseek-v3": "deepseek-v3.2",
    # GLM
    "glm-5": "glm-5",
    "glm5": "glm-5",
    # Qwen
    "qwen3-coder-next": "qwen3-coder-next",
    "qwen3-coder": "qwen3-coder-next",
    # Minimax
    "minimax-m2.5": "minimax-m2.5",
    "minimax-m2-5": "minimax-m2.5",
    "minimax-m2.1": "minimax-m2.1",
    "minimax-m2-1": "minimax-m2.1",
    # Auto (let Kiro pick the best)
    "auto": "auto",
    "auto-kiro": "auto",
}

# Models exposed via /v1/models (OpenCode, Cursor, etc will read this list)
KIRO_DISPLAY_MODELS = [
    # Claude models
    "claude-opus-4.7",
    "claude-sonnet-4.7",
    "claude-opus-4.5",
    "claude-sonnet-4.5",
    "claude-haiku-4.5",
    "claude-sonnet-4",
    "claude-3.7-sonnet",
    # Other providers via Kiro
    "deepseek-v3.2",
    "glm-5",
    "qwen3-coder-next",
    "minimax-m2.5",
    "minimax-m2.1",
    # Auto mode
    "auto",
]


def _extract_text_content(content: Any) -> str:
    """Extract text from various content formats."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif item.get("type") == "tool_result":
                    parts.append(json.dumps(item, ensure_ascii=False))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content)


class KiroAPIClient:

    def __init__(self):
        self.region = os.getenv("KIRO_REGION", DEFAULT_KIRO_REGION)
        self.api_host = KIRO_API_HOST_TEMPLATE.format(region=self.region)
        self.fingerprint = get_machine_fingerprint()
        logger.info(f"Kiro API client initialized: region={self.region}, host={self.api_host}")

    def get_chat_url(self) -> str:
        """Get the Kiro chat completions URL."""
        return f"{self.api_host}{KIRO_CHAT_PATH}"

    def resolve_model(self, model_name: str) -> str:
        """Resolve a friendly model name to a Kiro model ID."""
        clean = model_name.replace("kiro-", "")
        if clean in KIRO_MODEL_MAP:
            return KIRO_MODEL_MAP[clean]
        if model_name in KIRO_MODEL_MAP:
            return KIRO_MODEL_MAP[model_name]
        return model_name

    def generate_headers(self, api_key: str) -> Dict[str, str]:
        """
        Generate Kiro API request headers.

        Args:
            api_key: The ksk_ API key
        """
        return {
            "Authorization": f"Bearer {api_key}",
            "tokentype": "API_KEY",
            "Content-Type": "application/json",
            "User-Agent": f"aws-sdk-js/1.0.27 ua/2.1 os/darwin#23.0.0 lang/js "
                          f"md/nodejs#22.13.1 api/codewhispererstreaming#1.0.27 "
                          f"m/E KiroIDE-0.7.45-{self.fingerprint}",
            "x-amz-user-agent": f"aws-sdk-js/1.0.27 KiroIDE-0.7.45-{self.fingerprint}",
            "x-amzn-codewhisperer-optout": "true",
            "x-amzn-kiro-agent-mode": "vibe",
            "amz-sdk-invocation-id": str(uuid.uuid4()),
            "amz-sdk-request": "attempt=1; max=3",
            "Connection": "close",
        }

    def convert_openai_to_kiro_payload(
        self,
        openai_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Convert an OpenAI-format chat completions request to Kiro native format.
        """
        model = openai_payload.get("model", "auto")
        resolved_model = self.resolve_model(model)
        messages = openai_payload.get("messages", [])
        conversation_id = str(uuid.uuid4())

        # Separate system prompt
        system_prompt = ""
        non_system_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                text = _extract_text_content(msg.get("content"))
                system_prompt += text + "\n"
            else:
                non_system_messages.append(msg)
        system_prompt = system_prompt.strip()

        # Normalize roles
        normalized = []
        for msg in non_system_messages:
            role = msg.get("role", "user")
            if role in ("user", "human"):
                normalized.append({"role": "user", "content": msg.get("content")})
            elif role == "assistant":
                normalized.append({"role": "assistant", "content": msg.get("content")})
            elif role == "tool":
                tool_text = _extract_text_content(msg.get("content"))
                tool_id = msg.get("tool_call_id", "")
                result_text = f"[Tool Result ({tool_id})]\n{tool_text}" if tool_id else f"[Tool Result]\n{tool_text}"
                normalized.append({"role": "user", "content": result_text})
            else:
                normalized.append({"role": "user", "content": _extract_text_content(msg.get("content"))})

        if not normalized:
            normalized.append({"role": "user", "content": "Hello"})

        # Ensure alternating roles
        alternated = []
        for msg in normalized:
            if alternated and alternated[-1]["role"] == msg["role"]:
                if msg["role"] == "user":
                    alternated.append({"role": "assistant", "content": "(empty)"})
                else:
                    alternated[-1]["content"] = _extract_text_content(alternated[-1]["content"]) + "\n" + _extract_text_content(msg["content"])
                    continue
            alternated.append(msg)

        if alternated and alternated[0]["role"] != "user":
            alternated.insert(0, {"role": "user", "content": "(empty)"})

        history_messages = alternated[:-1] if len(alternated) > 1 else []
        current_msg = alternated[-1]

        # Build Kiro history
        history = []
        for msg in history_messages:
            content = _extract_text_content(msg.get("content"))
            if not content:
                content = "(empty)"
            if msg["role"] == "user":
                history.append({"userInputMessage": {"content": content, "modelId": resolved_model, "origin": "AI_EDITOR"}})
            elif msg["role"] == "assistant":
                history.append({"assistantResponseMessage": {"content": content}})

        current_content = _extract_text_content(current_msg.get("content"))
        if not current_content:
            current_content = "Continue"

        if system_prompt:
            if history and "userInputMessage" in history[0]:
                original = history[0]["userInputMessage"]["content"]
                history[0]["userInputMessage"]["content"] = f"{system_prompt}\n\n{original}"
            else:
                current_content = f"{system_prompt}\n\n{current_content}"

        user_input_message: Dict[str, Any] = {"content": current_content, "modelId": resolved_model, "origin": "AI_EDITOR"}

        tools = openai_payload.get("tools", [])
        if tools:
            kiro_tools = []
            for tool in tools:
                if tool.get("type") == "function":
                    func = tool.get("function", {})
                    kiro_tools.append({"name": func.get("name", ""), "description": (func.get("description", "") or "")[:10000], "inputSchema": func.get("parameters", {})})
            if kiro_tools:
                user_input_message["userInputMessageContext"] = {"tools": kiro_tools}

        payload = {
            "conversationState": {
                "chatTriggerType": "MANUAL",
                "conversationId": conversation_id,
                "currentMessage": {"userInputMessage": user_input_message},
            }
        }
        if history:
            payload["conversationState"]["history"] = history

        return payload

    def get_available_models(self) -> List[str]:
        return list(KIRO_DISPLAY_MODELS)


# Singleton
kiro_api_client = KiroAPIClient()
