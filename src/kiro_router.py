"""
Kiro Router - OpenAI-compatible proxy for Kiro (Amazon Q Developer) API.

Provides /kiro/v1/chat/completions and /kiro/v1/models endpoints that
translate between OpenAI format and Kiro's native API, using ksk_ API keys.

Reference: https://github.com/jwadow/kiro-gateway
"""
import asyncio
import json
import re
import time
import uuid
import logging
from typing import Optional, Dict, Any, List, Tuple

import httpx
from fastapi import APIRouter, HTTPException, Depends, Request, Header
from fastapi.responses import StreamingResponse, JSONResponse

from .auth import authenticate
from .kiro_api_client import kiro_api_client, KIRO_DISPLAY_MODELS

logger = logging.getLogger(__name__)

router = APIRouter()

# Kiro credential storage (simple in-memory, loaded from env or config)
_kiro_api_keys = []
_kiro_key_index = 0
_kiro_lock = asyncio.Lock()

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "*"
}

# HTTP client for Kiro
_kiro_http_client: Optional[httpx.AsyncClient] = None
_kiro_client_lock = asyncio.Lock()


async def get_kiro_http_client() -> httpx.AsyncClient:
    global _kiro_http_client
    if _kiro_http_client is None:
        async with _kiro_client_lock:
            if _kiro_http_client is None:
                _kiro_http_client = httpx.AsyncClient(
                    verify=False,
                    timeout=httpx.Timeout(300.0, connect=30.0, read=300.0),
                    limits=httpx.Limits(max_keepalive_connections=10, max_connections=50),
                )
    return _kiro_http_client


async def close_kiro_http_client():
    global _kiro_http_client
    async with _kiro_client_lock:
        if _kiro_http_client is not None:
            await _kiro_http_client.aclose()
            _kiro_http_client = None


def load_kiro_keys():
    """Load Kiro API keys from environment or config."""
    import os
    global _kiro_api_keys

    # Load from KIRO_API_KEYS env var (comma-separated)
    keys_env = os.getenv("KIRO_API_KEYS", "")
    if keys_env:
        _kiro_api_keys = [k.strip() for k in keys_env.split(",") if k.strip()]

    # Load individual key
    single_key = os.getenv("KIRO_API_KEY", "")
    if single_key and single_key not in _kiro_api_keys:
        _kiro_api_keys.append(single_key)

    # Load from kiro_keys.json if exists
    keys_file = os.path.join(os.path.dirname(__file__), '..', 'kiro_keys.json')
    if os.path.exists(keys_file):
        try:
            with open(keys_file, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        key = item if isinstance(item, str) else item.get("api_key", "")
                        if key and key not in _kiro_api_keys:
                            _kiro_api_keys.append(key)
                elif isinstance(data, dict):
                    for key_val in data.values():
                        key = key_val if isinstance(key_val, str) else ""
                        if key and key not in _kiro_api_keys:
                            _kiro_api_keys.append(key)
        except Exception as e:
            logger.error(f"Failed to load kiro_keys.json: {e}")

    logger.info(f"Loaded {len(_kiro_api_keys)} Kiro API key(s)")


def add_kiro_key(api_key: str) -> bool:
    """Add a Kiro API key to the pool."""
    global _kiro_api_keys
    if api_key not in _kiro_api_keys:
        _kiro_api_keys.append(api_key)
        _save_kiro_keys()
        logger.info(f"Added Kiro API key: {api_key[:8]}...{api_key[-4:]}")
        return True
    return False


def _save_kiro_keys():
    """Persist Kiro keys to disk."""
    import os
    keys_file = os.path.join(os.path.dirname(__file__), '..', 'kiro_keys.json')
    try:
        data = [{"api_key": k, "added_at": int(time.time())} for k in _kiro_api_keys]
        with open(keys_file, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved {len(_kiro_api_keys)} Kiro key(s) to {keys_file}")
    except Exception as e:
        logger.error(f"Failed to save kiro_keys.json: {e}")


async def get_next_kiro_key() -> str:
    """Get the next Kiro API key (round-robin)."""
    global _kiro_key_index
    if not _kiro_api_keys:
        raise HTTPException(status_code=401, detail="No Kiro API keys configured")
    async with _kiro_lock:
        key = _kiro_api_keys[_kiro_key_index % len(_kiro_api_keys)]
        _kiro_key_index += 1
        return key


# ============================================================
# AWS Event Stream Parser (ported from kiro-gateway/kiro/parsers.py)
# ============================================================

def _find_matching_brace(text: str, start_pos: int) -> int:
    """Finds the position of the closing brace considering nesting and strings."""
    if start_pos >= len(text) or text[start_pos] != '{':
        return -1
    brace_count = 0
    in_string = False
    escape_next = False
    for i in range(start_pos, len(text)):
        char = text[i]
        if escape_next:
            escape_next = False
            continue
        if char == '\\' and in_string:
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return i
    return -1


class AwsEventStreamParser:
    """
    Parser for AWS Event Stream format used by Kiro/Amazon Q API.

    Extracts JSON events from the binary stream. Events are detected by
    pattern matching for known JSON keys like {"content":, {"name":, etc.
    """
    EVENT_PATTERNS = [
        ('{"content":', 'content'),
        ('{"name":', 'tool_start'),
        ('{"input":', 'tool_input'),
        ('{"stop":', 'tool_stop'),
        ('{"followupPrompt":', 'followup'),
        ('{"usage":', 'usage'),
        ('{"contextUsagePercentage":', 'context_usage'),
    ]

    def __init__(self):
        self.buffer = ""
        self.last_content: Optional[str] = None

    def feed(self, chunk: bytes) -> List[Dict[str, Any]]:
        """Add chunk to buffer and return parsed events."""
        try:
            self.buffer += chunk.decode('utf-8', errors='ignore')
        except Exception:
            return []

        events = []
        while True:
            earliest_pos = -1
            earliest_type = None
            for pattern, event_type in self.EVENT_PATTERNS:
                pos = self.buffer.find(pattern)
                if pos != -1 and (earliest_pos == -1 or pos < earliest_pos):
                    earliest_pos = pos
                    earliest_type = event_type

            if earliest_pos == -1:
                break

            json_end = _find_matching_brace(self.buffer, earliest_pos)
            if json_end == -1:
                break  # Incomplete JSON, wait for more data

            json_str = self.buffer[earliest_pos:json_end + 1]
            self.buffer = self.buffer[json_end + 1:]

            try:
                data = json.loads(json_str)
                event = self._process_event(data, earliest_type)
                if event:
                    events.append(event)
            except json.JSONDecodeError:
                logger.debug(f"[Kiro] Failed to parse JSON event: {json_str[:100]}")

        return events

    def _process_event(self, data: dict, event_type: str) -> Optional[Dict[str, Any]]:
        if event_type == 'content':
            content = data.get('content', '')
            if data.get('followupPrompt'):
                return None
            if content == self.last_content:
                return None  # Deduplicate
            self.last_content = content
            return {"type": "content", "data": content}
        elif event_type == 'usage':
            return {"type": "usage", "data": data.get('usage', 0)}
        elif event_type == 'context_usage':
            return {"type": "context_usage", "data": data.get('contextUsagePercentage', 0)}
        return None


# ============================================================
# SSE Streaming
# ============================================================

async def stream_kiro_response(
    response: httpx.Response,
    model: str,
    completion_id: str,
    request_start: float,
):
    """Stream and convert Kiro AWS Event Stream to OpenAI SSE format."""
    parser = AwsEventStreamParser()
    first_byte = False
    total_content = ""

    try:
        async for chunk in response.aiter_bytes():
            if not chunk:
                continue

            if not first_byte:
                ttfb = time.monotonic() - request_start
                first_byte = True
                logger.info(f"[Kiro] TTFB: {ttfb:.2f}s for model {model}")

            events = parser.feed(chunk)
            for event in events:
                if event["type"] == "content":
                    content = event["data"]
                    total_content += content
                    chunk_data = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": content},
                            "finish_reason": None,
                        }]
                    }
                    yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"

    except Exception as e:
        logger.error(f"[Kiro] Stream error: {e}")
        error_data = {"error": {"message": f"Kiro stream error: {str(e)}", "type": "stream_error"}}
        yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
    finally:
        # Send finish chunk
        finish_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }]
        }
        yield f"data: {json.dumps(finish_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

        total_time = time.monotonic() - request_start
        logger.info(f"[Kiro] Completed: model={model}, time={total_time:.2f}s, content_len={len(total_content)}")


async def collect_kiro_response(
    response: httpx.Response,
) -> str:
    """Collect full Kiro response from AWS Event Stream."""
    parser = AwsEventStreamParser()
    total_content = ""

    async for chunk in response.aiter_bytes():
        if not chunk:
            continue
        events = parser.feed(chunk)
        for event in events:
            if event["type"] == "content":
                total_content += event["data"]

    return total_content


# --- API Endpoints ---

@router.post("/v1/chat/completions")
async def kiro_chat_completions(
    request: Request,
    _token: str = Depends(authenticate),
):
    """Kiro chat completions endpoint (OpenAI-compatible)."""
    try:
        request_body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    messages = request_body.get("messages")
    if not messages or not isinstance(messages, list):
        raise HTTPException(status_code=400, detail="messages field is required")

    model = request_body.get("model", "claude-sonnet-4.5")
    client_wants_stream = request_body.get("stream", False)
    completion_id = f"chatcmpl-kiro-{uuid.uuid4().hex[:12]}"

    logger.info(f"[Kiro] Request: model={model}, stream={client_wants_stream}, messages={len(messages)}")

    api_key = await get_next_kiro_key()
    headers = kiro_api_client.generate_headers(api_key)

    # Convert payload
    kiro_payload = kiro_api_client.convert_openai_to_kiro_payload(request_body)
    chat_url = kiro_api_client.get_chat_url()

    request_start = time.monotonic()

    MAX_RETRIES = 2
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            client = await get_kiro_http_client()

            if client_wants_stream:
                stream_ctx = client.stream("POST", chat_url, json=kiro_payload, headers=headers)
                response = await stream_ctx.__aenter__()

                if response.status_code != 200:
                    error_bytes = await response.aread()
                    await stream_ctx.__aexit__(None, None, None)
                    error_msg = error_bytes.decode('utf-8', errors='ignore')[:500]
                    logger.error(f"[Kiro] API error: {response.status_code} - {error_msg[:200]}")

                    if response.status_code == 403 and attempt < MAX_RETRIES - 1:
                        # Try next key
                        api_key = await get_next_kiro_key()
                        headers = kiro_api_client.generate_headers(api_key)
                        last_error = HTTPException(status_code=response.status_code, detail=error_msg)
                        continue

                    if response.status_code in (429,) and attempt < MAX_RETRIES - 1:
                        api_key = await get_next_kiro_key()
                        headers = kiro_api_client.generate_headers(api_key)
                        last_error = HTTPException(status_code=response.status_code, detail=error_msg)
                        continue

                    raise HTTPException(status_code=response.status_code, detail=f"Kiro API error: {error_msg}")

                async def generate():
                    try:
                        async for chunk in stream_kiro_response(
                            response, model, completion_id, request_start
                        ):
                            yield chunk
                    finally:
                        await stream_ctx.__aexit__(None, None, None)

                return StreamingResponse(
                    generate(),
                    media_type="text/event-stream",
                    headers=SSE_HEADERS,
                )

            else:
                # Non-streaming: still use stream internally to parse AWS Event Stream
                async with client.stream("POST", chat_url, json=kiro_payload, headers=headers) as response:
                    if response.status_code != 200:
                        error_bytes = await response.aread()
                        error_msg = error_bytes.decode('utf-8', errors='ignore')[:500]
                        logger.error(f"[Kiro] API error: {response.status_code} - {error_msg[:200]}")

                        if response.status_code == 403 and attempt < MAX_RETRIES - 1:
                            api_key = await get_next_kiro_key()
                            headers = kiro_api_client.generate_headers(api_key)
                            last_error = HTTPException(status_code=response.status_code, detail=error_msg)
                            continue

                        if response.status_code in (429,) and attempt < MAX_RETRIES - 1:
                            api_key = await get_next_kiro_key()
                            headers = kiro_api_client.generate_headers(api_key)
                            last_error = HTTPException(status_code=response.status_code, detail=error_msg)
                            continue

                        raise HTTPException(status_code=response.status_code, detail=f"Kiro API error: {error_msg}")

                    # Collect full response
                    total_content = await collect_kiro_response(response)

                # Build OpenAI-format response
                result = {
                    "id": completion_id,
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": total_content,
                        },
                        "finish_reason": "stop",
                    }],
                    "usage": {
                        "prompt_tokens": 0,
                        "completion_tokens": len(total_content.split()),
                        "total_tokens": len(total_content.split()),
                    }
                }

                total_time = time.monotonic() - request_start
                logger.info(f"[Kiro] Non-streaming completed: model={model}, time={total_time:.2f}s, len={len(total_content)}")
                return JSONResponse(content=result)

        except HTTPException:
            raise
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            logger.warning(f"[Kiro] Network error: {e}, attempt {attempt + 1}/{MAX_RETRIES}")
            last_error = HTTPException(status_code=502, detail=str(e))
            if attempt < MAX_RETRIES - 1:
                continue
            raise last_error
        except Exception as e:
            logger.error(f"[Kiro] Unexpected error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    if last_error:
        raise last_error
    raise HTTPException(status_code=503, detail="All Kiro retries exhausted")


@router.get("/v1/models")
async def list_kiro_models(_token: str = Depends(authenticate)):
    """List available Kiro models."""
    return {
        "object": "list",
        "data": [{
            "id": model,
            "object": "model",
            "created": 1746748800,  # fixed timestamp
            "owned_by": "kiro/aws",
            "description": f"Kiro (Amazon Q Developer) – {model}",
        } for model in KIRO_DISPLAY_MODELS]
    }


@router.get("/v1/keys")
async def list_kiro_keys(_token: str = Depends(authenticate)):
    """List configured Kiro API keys (masked)."""
    return {
        "keys": [
            {
                "index": i,
                "preview": f"{k[:8]}...{k[-4:]}" if len(k) > 12 else "***",
                "type": "ksk" if k.startswith("ksk_") else "unknown",
            }
            for i, k in enumerate(_kiro_api_keys)
        ],
        "total": len(_kiro_api_keys),
    }


@router.post("/v1/keys")
async def add_kiro_key_endpoint(request: Request, _token: str = Depends(authenticate)):
    """Add a new Kiro API key."""
    data = await request.json()
    api_key = data.get("api_key", "").strip()
    if not api_key:
        raise HTTPException(status_code=422, detail="api_key is required")

    if add_kiro_key(api_key):
        return {"message": "Kiro API key added successfully", "total_keys": len(_kiro_api_keys)}
    else:
        return {"message": "Key already exists", "total_keys": len(_kiro_api_keys)}


# Initialize on import
load_kiro_keys()
