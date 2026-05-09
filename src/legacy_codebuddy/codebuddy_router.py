"""
CodeBuddy API Router - OpenAI-compatible proxy for CodeBuddy API.
Handles streaming/non-streaming, auto-retry on key failure, response
de-obfuscation, caching, and latency tracking.
"""
import copy
import hashlib
import json
import time
import uuid
import logging
import asyncio
from collections import OrderedDict
from typing import Optional, Dict, Any, List, AsyncGenerator

import httpx
from fastapi import APIRouter, HTTPException, Depends, Request, Header
from fastapi.responses import StreamingResponse, JSONResponse

from .auth import authenticate
from .codebuddy_api_client import codebuddy_api_client
from .codebuddy_token_manager import codebuddy_token_manager
from .usage_stats_manager import usage_stats_manager
from .circuit_breaker import CircuitBreakerManager
from .health_db import HealthDatabase, CredentialEvent
from .keyword_replacer import (
    apply_to_message_content,
    deobfuscate_response,
    load_filters,
    get_filter_count,
)
from .model_router import route_model
from .prompt_enhancer import enhance_prompt
from .context_manager import manage_context
from .session_memory import inject_session_context, extract_and_save_facts
from .thinking_stripper import StreamingThinkingStripper, strip_thinking_from_text
from .request_logger import request_logger
from . import health_monitor
from .response_cache import response_cache
from .session_affinity import session_affinity
from .quota_estimator import quota_estimator

logger = logging.getLogger(__name__)

router = APIRouter()

MODEL_MAX_OUTPUT = {
    "claude-opus-4.6": 128000,
    "claude-haiku-4.5": 64000,
    "gpt-5.5": 128000,
    "gpt-5": 128000,
    "gpt-5-mini": 64000,
    "gpt-5-nano": 32000,
    "o4-mini": 100000,
    "gemini-2.5-pro": 65536,
    "gemini-2.5-flash": 65536,
    "gemini-3.1-pro": 65536,
}
DEFAULT_MAX_OUTPUT = 128000

# Config accessors — always read fresh values so hot-reload works

def get_codebuddy_api_url() -> str:
    from config import get_codebuddy_api_endpoint
    return f"{get_codebuddy_api_endpoint()}/v2/chat/completions"


def get_available_models_list() -> List[str]:
    from config import get_available_models
    return get_available_models()


# --- SSL / HTTP client config ---

class SecurityConfig:
    @staticmethod
    def get_ssl_verify() -> bool:
        import os
        ssl_verify_env = os.getenv("CODEBUDDY_SSL_VERIFY", "false").lower()
        return ssl_verify_env == "true"


HTTP_CLIENT_CONFIG = {
    "verify": SecurityConfig.get_ssl_verify(),
    "timeout": httpx.Timeout(300.0, connect=30.0, read=300.0),
    "limits": httpx.Limits(max_keepalive_connections=20, max_connections=100)
}

_http_client_pool: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()


async def get_http_client() -> httpx.AsyncClient:
    global _http_client_pool
    if _http_client_pool is None:
        async with _client_lock:
            if _http_client_pool is None:
                _http_client_pool = httpx.AsyncClient(**HTTP_CLIENT_CONFIG)
    return _http_client_pool


async def close_http_client():
    global _http_client_pool
    async with _client_lock:
        if _http_client_pool is not None:
            await _http_client_pool.aclose()
            _http_client_pool = None


class AppLifecycleManager:
    @staticmethod
    async def startup():
        logger.info("CodeBuddy Router starting...")
        await get_http_client()
        logger.info("HTTP connection pool initialized")

    @staticmethod
    async def shutdown():
        logger.info("CodeBuddy Router shutting down...")
        await close_http_client()
        usage_stats_manager.force_persist()
        quota_estimator.flush()
        logger.info("Resources cleaned up")


lifecycle_manager = AppLifecycleManager()

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "*"
}


# --- LRU Response Cache (Task #10) ---

class LRUCache:
    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds

    def _make_key(self, model: str, messages: list, session_id: Optional[str] = None) -> str:
        content = json.dumps({"model": model, "messages": messages, "session_id": session_id or ""}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()

    def get(self, model: str, messages: list, session_id: Optional[str] = None) -> Optional[Dict]:
        key = self._make_key(model, messages, session_id)
        if key not in self._cache:
            return None
        entry = self._cache[key]
        if time.time() - entry["ts"] > self._ttl:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return entry["data"]

    def put(self, model: str, messages: list, data: Dict, session_id: Optional[str] = None):
        key = self._make_key(model, messages, session_id)
        self._cache[key] = {"data": data, "ts": time.time()}
        self._cache.move_to_end(key)
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)


_response_cache = LRUCache(max_size=100, ttl_seconds=300)

MAX_KEY_RETRIES = 3
SLOW_TTFB_THRESHOLD = 10.0  # seconds
MAX_IDLE_SECONDS = 120  # max time without data before aborting stream


# --- Helpers ---

def format_sse_error(message: str, error_type: str = "stream_error") -> str:
    error_data = {
        "error": {
            "message": message,
            "type": error_type
        }
    }
    return f'data: {json.dumps(error_data, ensure_ascii=False)}\n\n'


class OpenAICompatibilityConverter:

    @staticmethod
    def convert_tool_call_id(codebuddy_id: str) -> str:
        if codebuddy_id.startswith('tooluse_'):
            return f"call_{codebuddy_id[8:]}"
        return codebuddy_id

    @staticmethod
    def convert_sse_chunk_to_openai_format(chunk_data: Dict[str, Any], tool_call_index_map: Dict[str, int]) -> Dict[str, Any]:
        if not chunk_data.get('choices'):
            return chunk_data

        choice = chunk_data['choices'][0]
        delta = choice.get('delta', {})
        tool_calls = delta.get('tool_calls', [])

        if not tool_calls:
            return chunk_data

        converted_tool_calls = []
        for tc in tool_calls:
            converted_tc = tc.copy()

            if tc.get('id'):
                original_id = tc['id']
                converted_id = OpenAICompatibilityConverter.convert_tool_call_id(original_id)
                converted_tc['id'] = converted_id

                if original_id not in tool_call_index_map:
                    tool_call_index_map[original_id] = len(tool_call_index_map)

                converted_tc['index'] = tool_call_index_map[original_id]

            elif tool_call_index_map:
                converted_tc['index'] = max(tool_call_index_map.values())

            converted_tool_calls.append(converted_tc)

        converted_chunk = chunk_data.copy()
        converted_chunk['choices'][0]['delta']['tool_calls'] = converted_tool_calls

        return converted_chunk


def parse_sse_line(line: str) -> Optional[Dict[str, Any]]:
    if line.startswith('data: '):
        data = line[6:]
    elif line.startswith('data:'):
        data = line[5:]
    else:
        return None

    data = data.strip()
    if not data or data == '[DONE]':
        return None

    try:
        return json.loads(data)
    except json.JSONDecodeError:
        logger.debug(f"Unparsable SSE data: {data[:200]}")
        return None


def sanitize_sse_chunk(chunk: Dict[str, Any]) -> Dict[str, Any]:
    if not chunk.get('choices'):
        return chunk

    for choice in chunk['choices']:
        delta = choice.get('delta', {})

        for field in ['reasoning_content', 'extra_fields', 'refusal']:
            delta.pop(field, None)

        if delta.get('function_call') is None:
            delta.pop('function_call', None)

        if 'tool_calls' in delta and not delta['tool_calls']:
            delta.pop('tool_calls', None)

        if choice.get('finish_reason') == '':
            choice.pop('finish_reason', None)

        # Per OpenAI spec: finish_reason must be null on all chunks EXCEPT the
        # final one. CodeBuddy sends finish_reason on every chunk, which causes
        # OpenAI-compatible clients (like OpenCode) to think the stream ended
        # on the first chunk (output=0). Null it out whenever there is still
        # streaming content or tool_call deltas in this chunk.
        has_content = bool(delta.get('content') or delta.get('tool_calls'))
        if has_content and choice.get('finish_reason') is not None:
            choice['finish_reason'] = None

    return chunk


def validate_and_fix_tool_call_args(args: str) -> str:
    if not args or not args.strip():
        return '{}'

    args = args.strip()

    try:
        json.loads(args)
        return args
    except json.JSONDecodeError:
        pass

    if args.count('}{') > 0:
        json_objects = []
        current_obj = ""
        brace_count = 0

        for char in args:
            current_obj += char
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and current_obj.strip():
                    try:
                        parsed = json.loads(current_obj.strip())
                        json_objects.append(parsed)
                        current_obj = ""
                    except json.JSONDecodeError:
                        current_obj = ""

        if json_objects:
            if len(json_objects) > 1:
                logger.warning(f"Tool call had {len(json_objects)} concatenated JSON objects, using first")
            return json.dumps(json_objects[0], ensure_ascii=False)

    patched = args
    if not patched.endswith('}') and patched.count('{') > patched.count('}'):
        patched += '}'
    elif not patched.endswith(']') and patched.count('[') > patched.count(']'):
        patched += ']'

    try:
        json.loads(patched)
        return patched
    except json.JSONDecodeError:
        logger.warning(f"Preserving partial tool call args as-is: {args[:200]}")
        return args


def _deobfuscate_sse_chunk(chunk_data: Dict[str, Any]) -> Dict[str, Any]:
    """Apply de-obfuscation + Chinese error translation to an SSE chunk."""
    if not chunk_data.get('choices'):
        return chunk_data
    for choice in chunk_data.get('choices', []):
        delta = choice.get('delta', {})
        if delta.get('content'):
            delta['content'] = deobfuscate_response(delta['content'])
    return chunk_data


_VALID_FINISH_REASONS = {"stop", "length", "tool_calls", "content_filter"}

_FINISH_REASON_MAP = {
    "end_turn": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
    "stop_sequence": "stop",
    "function_call": "tool_calls",
}


def _normalize_finish_reason(chunk_data: Dict[str, Any]) -> Dict[str, Any]:
    for choice in chunk_data.get('choices', []):
        reason = choice.get('finish_reason')
        # Empty string → null (not a valid finish signal)
        if reason == '':
            choice['finish_reason'] = None
        elif reason is not None and reason not in _VALID_FINISH_REASONS:
            choice['finish_reason'] = _FINISH_REASON_MAP.get(reason, 'stop')
    return chunk_data


def _is_content_filter_error(text: str) -> bool:
    """Check if response text indicates a content filter / key issue."""
    indicators = [
        "sensitive content", "content filter", "11128",
        "\u654f\u611f\u5185\u5bb9", "\u5185\u5bb9\u8fdd\u89c4",
        "rate limit", "quota exceeded", "insufficient balance",
        "\u4f59\u989d\u4e0d\u8db3", "\u64cd\u4f5c\u592a\u9891\u7e41",
    ]
    text_lower = text.lower()
    return any(ind.lower() in text_lower for ind in indicators)


def _is_permanently_banned(status_code: int, error_msg: str) -> bool:
    """Check if response indicates a permanently banned/invalid credential."""
    if status_code != 403:
        return False
    banned_indicators = ["11140", "request not illegal"]
    text_lower = error_msg.lower()
    return any(ind in text_lower for ind in banned_indicators)


class SSEConnectionManager:

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def stream_with_retry(self, stream_func, *args, **kwargs):
        content_yielded = False
        for attempt in range(self.max_retries + 1):
            try:
                async for chunk in stream_func(*args, **kwargs):
                    content_yielded = True
                    yield chunk
                break
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if content_yielded:
                    logger.error(f"Connection lost after partial content, cannot retry: {e}")
                    yield format_sse_error(f"Connection lost after partial content: {str(e)}", "stream_error")
                    break
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(f"Connection failed, retrying in {wait_time}s (attempt {attempt + 1}): {e}")
                    yield format_sse_error(f"Connection lost, retrying in {wait_time}s... (attempt {attempt + 1})", "connection_retry")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Reconnect failed after {self.max_retries} retries: {e}")
                    yield format_sse_error(f"Connection failed after {self.max_retries} retries: {str(e)}", "connection_failed")
                    raise
            except Exception as e:
                logger.error(f"Stream processing error: {e}")
                yield format_sse_error(f"Stream error: {str(e)}", "stream_error")
                raise


class StreamResponseAggregator:

    def __init__(self):
        self.data = {
            "id": None,
            "model": None,
            "content": "",
            "tool_calls": [],
            "finish_reason": None,
            "usage": None,
            "system_fingerprint": None
        }
        self.tool_call_map = {}
        self.tool_call_order = []
        self.current_tool_id = None
        self.chunks_processed = 0

    def process_chunk(self, obj: Dict[str, Any]):
        self.chunks_processed += 1
        self.data["id"] = self.data["id"] or obj.get('id')
        self.data["model"] = self.data["model"] or obj.get('model')
        self.data["system_fingerprint"] = obj.get('system_fingerprint') or self.data["system_fingerprint"]

        if obj.get('usage'):
            self.data["usage"] = obj.get('usage')

        choices = obj.get('choices', [])
        if not choices:
            return

        choice = choices[0]
        if choice.get('finish_reason'):
            self.data["finish_reason"] = choice.get('finish_reason')

        delta = choice.get('delta', {})

        if delta.get('content'):
            self.data["content"] += delta.get('content')

        if delta.get('tool_calls'):
            self._process_tool_calls(delta.get('tool_calls'))

    def _process_tool_calls(self, tool_calls: List[Dict[str, Any]]):
        for tc in tool_calls:
            tool_id = tc.get('id')

            if tool_id:
                if tool_id not in self.tool_call_map:
                    self.tool_call_map[tool_id] = {
                        'id': tool_id,
                        'type': tc.get('type', 'function'),
                        'function': {
                            'name': '',
                            'arguments': ''
                        }
                    }
                    self.tool_call_order.append(tool_id)
                    self.current_tool_id = tool_id
                else:
                    self.current_tool_id = tool_id

                if tc.get('type'):
                    self.tool_call_map[tool_id]['type'] = tc.get('type')

                func = tc.get('function', {})
                if func.get('name'):
                    self.tool_call_map[tool_id]['function']['name'] = func.get('name')
                if func.get('arguments') is not None:
                    self.tool_call_map[tool_id]['function']['arguments'] += func.get('arguments')

            elif self.current_tool_id and self.current_tool_id in self.tool_call_map:
                func = tc.get('function', {})
                if func.get('name'):
                    self.tool_call_map[self.current_tool_id]['function']['name'] = func.get('name')
                if func.get('arguments') is not None:
                    self.tool_call_map[self.current_tool_id]['function']['arguments'] += func.get('arguments')

            else:
                logger.warning("Tool call missing ID and no current tool call context, skipping")

    def finalize(self) -> Dict[str, Any]:
        if self.chunks_processed == 0:
            return {
                "error": {
                    "message": "No valid response data received from upstream",
                    "type": "empty_response"
                }
            }

        if self.tool_call_map:
            self.data["tool_calls"] = []
            for tool_id in self.tool_call_order:
                if tool_id in self.tool_call_map:
                    tc = self.tool_call_map[tool_id]
                    tc['function']['arguments'] = validate_and_fix_tool_call_args(
                        tc['function']['arguments']
                    )
                    self.data["tool_calls"].append(tc)

        # De-obfuscate aggregated content
        self.data["content"] = deobfuscate_response(self.data["content"])

        final_message = {"role": "assistant", "content": self.data["content"]}
        if self.data["tool_calls"]:
            final_message["tool_calls"] = self.data["tool_calls"]

        raw_reason = self.data["finish_reason"] or "stop"
        if raw_reason not in _VALID_FINISH_REASONS:
            raw_reason = "stop"
        finish_reason = "tool_calls" if self.data["tool_calls"] else raw_reason

        final_response = {
            "id": self.data["id"] or str(uuid.uuid4()),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.data["model"] or "unknown",
            "choices": [
                {
                    "index": 0,
                    "message": final_message,
                    "finish_reason": finish_reason,
                    "logprobs": None
                }
            ]
        }

        if self.data["usage"]:
            final_response["usage"] = self.data["usage"]
        if self.data["system_fingerprint"]:
            final_response["system_fingerprint"] = self.data["system_fingerprint"]

        return final_response


class CodeBuddyStreamService:

    def __init__(self):
        self.connection_manager = SSEConnectionManager(max_retries=3, retry_delay=1.0)

    def _handle_api_error(self, status_code: int, error_msg: str) -> None:
        logger.error(f"CodeBuddy API error: {status_code} - {error_msg}")

        if status_code == 401:
            raise HTTPException(status_code=401, detail="CodeBuddy API authentication failed")
        elif status_code == 429:
            raise HTTPException(status_code=429, detail="CodeBuddy API rate limit exceeded")
        elif status_code >= 500:
            raise HTTPException(status_code=502, detail="CodeBuddy API server error")
        else:
            raise HTTPException(status_code=status_code, detail=f"CodeBuddy API error: {error_msg}")

    async def _stream_from_response(self, response, stream_ctx, model: str, request_start: float,
                                    credential_id: str = "", request_id: str = ""):
        first_byte_recorded = False
        ttfb = 0.0
        done_sent = False
        malformed_count = 0
        thinking_stripper = StreamingThinkingStripper()
        total_output_tokens = 0
        final_finish_reason = None
        total_chunks = 0
        KEEPALIVE_INTERVAL = 10.0
        # Repetition detection: only fire for *meaningful* content repeated many times.
        # Whitespace-only chunks (spaces, newlines) are completely ignored.
        # Meaningful chunks (3+ non-whitespace chars) must repeat 150+ times consecutively.
        # Short but non-empty chunks (1-2 chars) must repeat 500+ times.
        REPEAT_LIMIT_LONG = 150    # 3+ visible chars repeated — likely stuck loop
        REPEAT_LIMIT_SHORT = 500   # 1-2 visible chars repeated — very conservative
        REPEAT_MIN_LEN = 3         # threshold between short vs long

        try:
            buffer = ""
            tool_call_index_map = {}
            event_data_lines: list[str] = []
            repeat_content = None
            repeat_count = 0

            last_data_time = time.monotonic()
            aiter = response.aiter_text(chunk_size=8192).__aiter__()
            while True:
                try:
                    chunk = await asyncio.wait_for(aiter.__anext__(), timeout=KEEPALIVE_INTERVAL)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    if time.monotonic() - last_data_time > MAX_IDLE_SECONDS:
                        logger.error(f"Stream timeout: no data received for {MAX_IDLE_SECONDS}s (model={model})")
                        yield format_sse_error(f"Stream timeout: no data received for {MAX_IDLE_SECONDS}s", "stream_timeout")
                        return
                    yield ": keepalive\n\n"
                    continue

                if not chunk:
                    continue

                if not first_byte_recorded:
                    ttfb = time.monotonic() - request_start
                    first_byte_recorded = True
                    if ttfb > SLOW_TTFB_THRESHOLD:
                        logger.warning(f"Slow TTFB: {ttfb:.2f}s for model {model}")

                last_data_time = time.monotonic()
                buffer += chunk

                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    stripped = line.strip()

                    if not stripped:
                        if event_data_lines:
                            combined = "\n".join(event_data_lines)
                            event_data_lines = []

                            if '[DONE]' in combined:
                                total_time = time.monotonic() - request_start
                                usage_stats_manager.record_latency(model, ttfb if first_byte_recorded else total_time, total_time)
                                yield 'data: [DONE]\n\n'
                                done_sent = True
                                return

                            chunk_data = parse_sse_line(f"data: {combined}")
                            if chunk_data:
                                total_chunks += 1
                                chunk_data = _normalize_finish_reason(chunk_data)
                                content_piece = None
                                for ch in chunk_data.get('choices', []):
                                    content_piece = ch.get('delta', {}).get('content')
                                if content_piece is not None:
                                    # Skip pure-whitespace chunks — these are normal in streaming
                                    stripped_piece = content_piece.strip()
                                    if stripped_piece:  # only track non-whitespace content
                                        if content_piece == repeat_content:
                                            repeat_count += 1
                                            limit = REPEAT_LIMIT_LONG if len(stripped_piece) >= REPEAT_MIN_LEN else REPEAT_LIMIT_SHORT
                                            if repeat_count > limit:
                                                logger.error(f"Infinite loop detected: '{content_piece[:50]}' repeated {repeat_count} times (limit={limit})")
                                                yield format_sse_error("Stream terminated: infinite repetition detected", "loop_detected")
                                                return
                                        else:
                                            repeat_content = content_piece
                                            repeat_count = 1

                                converted_chunk = OpenAICompatibilityConverter.convert_sse_chunk_to_openai_format(
                                    chunk_data, tool_call_index_map
                                )
                                sanitized = sanitize_sse_chunk(converted_chunk)
                                sanitized = _deobfuscate_sse_chunk(sanitized)
                                # Strip thinking/signature blocks (enowx-style)
                                sanitized, _ = thinking_stripper.process_chunk(sanitized)
                                # Track finish reason and output tokens for logging
                                for _ch in sanitized.get('choices', []):
                                    if _ch.get('finish_reason'):
                                        final_finish_reason = _ch['finish_reason']
                                    _content = _ch.get('delta', {}).get('content') or ''
                                    total_output_tokens += len(_content.split())
                                yield f"data: {json.dumps(sanitized, ensure_ascii=False)}\n\n"
                            else:
                                malformed_count += 1
                                logger.warning(f"Malformed SSE chunk dropped ({malformed_count}): {combined[:200]}")
                                if malformed_count > 5 and malformed_count > total_chunks * 0.5:
                                    logger.error(f"Too many malformed chunks ({malformed_count}/{malformed_count + total_chunks}), aborting stream")
                                    yield format_sse_error(
                                        f"Stream aborted: too many malformed chunks ({malformed_count} malformed vs {total_chunks} valid)",
                                        "malformed_stream"
                                    )
                                    return
                        continue

                    if stripped.startswith(':'):
                        continue

                    if stripped.startswith('data: '):
                        event_data_lines.append(stripped[6:])
                    elif stripped.startswith('data:'):
                        event_data_lines.append(stripped[5:])
                    elif stripped.startswith('event:') or stripped.startswith('id:') or stripped.startswith('retry:'):
                        continue
                    else:
                        event_data_lines.append(stripped)

            if event_data_lines:
                combined = "\n".join(event_data_lines)
                if '[DONE]' in combined:
                    total_time = time.monotonic() - request_start
                    usage_stats_manager.record_latency(model, ttfb if first_byte_recorded else total_time, total_time)
                    yield 'data: [DONE]\n\n'
                    done_sent = True
                    return
                chunk_data = parse_sse_line(f"data: {combined}")
                if chunk_data:
                    chunk_data = _normalize_finish_reason(chunk_data)
                    converted_chunk = OpenAICompatibilityConverter.convert_sse_chunk_to_openai_format(
                        chunk_data, tool_call_index_map
                    )
                    sanitized = sanitize_sse_chunk(converted_chunk)
                    sanitized = _deobfuscate_sse_chunk(sanitized)
                    yield f"data: {json.dumps(sanitized, ensure_ascii=False)}\n\n"

            if buffer.strip():
                remaining = buffer.strip()
                if '[DONE]' in remaining:
                    pass
                else:
                    chunk_data = parse_sse_line(remaining if remaining.startswith('data:') else f"data: {remaining}")
                    if chunk_data:
                        chunk_data = _normalize_finish_reason(chunk_data)
                        converted_chunk = OpenAICompatibilityConverter.convert_sse_chunk_to_openai_format(
                            chunk_data, tool_call_index_map
                        )
                        sanitized = sanitize_sse_chunk(converted_chunk)
                        sanitized = _deobfuscate_sse_chunk(sanitized)
                        yield f"data: {json.dumps(sanitized, ensure_ascii=False)}\n\n"

            # Flush any remaining buffered content from thinking stripper
            remainder, total_stripped = thinking_stripper.flush()
            if remainder.strip():
                yield f"data: {json.dumps({'choices': [{'delta': {'content': remainder}, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
            if total_stripped:
                logger.info(f"Thinking stripper removed {total_stripped} block(s) from stream (model={model})")

            if first_byte_recorded:
                total_time = time.monotonic() - request_start
                usage_stats_manager.record_latency(model, ttfb, total_time)
                # Health monitor + request log
                health_monitor.mark_credential_success(credential_id, total_time * 1000)
                asyncio.ensure_future(request_logger.log_request(
                    request_id=request_id or str(uuid.uuid4()),
                    model=model,
                    provider="codebuddy",
                    credential_id=credential_id or None,
                    stream=True,
                    input_tokens=0,
                    output_tokens=total_output_tokens,
                    ttfb_ms=ttfb * 1000,
                    total_ms=total_time * 1000,
                    finish_reason=final_finish_reason,
                    thinking_blocks_stripped=thinking_stripper.total_stripped,
                    status="ok",
                ))
        finally:
            if not done_sent:
                if total_chunks == 0 and malformed_count > 0:
                    yield format_sse_error(
                        f"Stream produced no valid data ({malformed_count} malformed chunks)",
                        "empty_stream"
                    )
                yield 'data: [DONE]\n\n'
            await stream_ctx.__aexit__(None, None, None)

    async def handle_stream_response_from_open_stream(self, response, stream_ctx, payload, headers, model: str = "unknown") -> StreamingResponse:
        request_start = time.monotonic()
        return StreamingResponse(
            self._stream_from_response(response, stream_ctx, model, request_start),
            media_type="text/event-stream",
            headers=SSE_HEADERS
        )

    async def handle_stream_response(self, payload: Dict[str, Any], headers: Dict[str, str], model: str = "unknown",
                                     credential_id: str = "", request_id: str = "") -> StreamingResponse:
        request_start = time.monotonic()

        async def stream_core():
            client = await get_http_client()
            stream_ctx = client.stream("POST", get_codebuddy_api_url(), json=payload, headers=headers)
            response = await stream_ctx.__aenter__()

            if response.status_code != 200:
                error_text = await response.aread()
                await stream_ctx.__aexit__(None, None, None)
                error_msg = error_text.decode('utf-8', errors='ignore')
                translated = deobfuscate_response(error_msg)
                health_monitor.mark_credential_failure(credential_id, f"HTTP {response.status_code}")
                asyncio.ensure_future(request_logger.log_request(
                    request_id=request_id or str(uuid.uuid4()),
                    model=model, provider="codebuddy",
                    credential_id=credential_id or None, stream=True,
                    input_tokens=0, output_tokens=0, ttfb_ms=None,
                    total_ms=(time.monotonic() - request_start) * 1000,
                    finish_reason=None, status="error",
                    error=f"HTTP {response.status_code}",
                ))
                yield format_sse_error(f"CodeBuddy API error: {response.status_code} - {translated}", "api_error")
                return

            async for chunk in self._stream_from_response(
                response, stream_ctx, model, request_start,
                credential_id=credential_id, request_id=request_id
            ):
                yield chunk

        async def stream_with_retry():
            async for chunk in self.connection_manager.stream_with_retry(stream_core):
                yield chunk

        return StreamingResponse(stream_with_retry(), media_type="text/event-stream", headers=SSE_HEADERS)

    async def handle_non_stream_response(self, payload: Dict[str, Any], headers: Dict[str, str], model: str = "unknown") -> Dict[str, Any]:
        request_start = time.monotonic()
        try:
            client = await get_http_client()
            response = await client.post(get_codebuddy_api_url(), json=payload, headers=headers)

            ttfb = time.monotonic() - request_start

            if response.status_code != 200:
                error_msg = response.text
                self._handle_api_error(response.status_code, error_msg)

            aggregator = StreamResponseAggregator()
            buffer = ""

            async for chunk in response.aiter_text():
                if not chunk:
                    continue
                buffer += chunk
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    obj = parse_sse_line(line)
                    if obj:
                        aggregator.process_chunk(obj)

            if buffer.strip():
                obj = parse_sse_line(buffer.strip())
                if obj:
                    aggregator.process_chunk(obj)

            total_time = time.monotonic() - request_start
            usage_stats_manager.record_latency(model, ttfb, total_time)

            if ttfb > SLOW_TTFB_THRESHOLD:
                logger.warning(f"Slow TTFB: {ttfb:.2f}s for model {model}")

            result = aggregator.finalize()
            if "error" in result:
                raise HTTPException(status_code=502, detail=result["error"]["message"])
            return result

        except httpx.TimeoutException:
            logger.error("CodeBuddy API timeout")
            raise HTTPException(status_code=504, detail="CodeBuddy API timeout")
        except httpx.NetworkError as e:
            logger.error(f"Network error: {e}")
            raise HTTPException(status_code=502, detail=f"Network error: {str(e)}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Request error: {e}")
            raise HTTPException(status_code=500, detail=f"Request error: {str(e)}")


class RequestProcessor:

    @staticmethod
    def prepare_payload(request_body: Dict[str, Any], session_id: Optional[str] = None) -> Dict[str, Any]:
        payload = request_body.copy()
        payload["stream"] = True

        payload["messages"] = copy.deepcopy(payload.get("messages", []))

        # 1. Route model (resolve auto-smart/auto-fast/auto-cheap)
        model = payload.get("model", "unknown")
        resolved_model, reason = route_model(model, payload["messages"])
        if resolved_model != model:
            payload["model"] = resolved_model

        # 2. Enhance prompt (auto system prompt, quality hints, task detection)
        payload["messages"] = enhance_prompt(payload["messages"])

        # 3. Inject session context
        payload["messages"] = inject_session_context(payload["messages"], session_id)

        # 4. Manage context (trim if exceeds model threshold)
        payload["messages"] = manage_context(payload["messages"], payload.get("model", "unknown"))

        # 5. Keyword replacement
        for msg in payload["messages"]:
            if msg.get("content") is not None:
                if msg.get("role") == "system":
                    msg["content"] = apply_to_message_content(msg["content"])
                else:
                    msg["content"] = apply_to_message_content(msg["content"], light_mode=True)

        # 6. Parameter validation
        if "temperature" in payload:
            try:
                payload["temperature"] = max(0.0, min(2.0, float(payload["temperature"])))
            except (TypeError, ValueError):
                del payload["temperature"]

        if "top_p" in payload:
            try:
                payload["top_p"] = max(0.0, min(1.0, float(payload["top_p"])))
            except (TypeError, ValueError):
                del payload["top_p"]

        model_name = payload.get("model", "")
        model_max = MODEL_MAX_OUTPUT.get(model_name, DEFAULT_MAX_OUTPUT)
        if "max_tokens" in payload:
            try:
                val = int(payload["max_tokens"])
                payload["max_tokens"] = max(model_max, min(val, 128000))
            except (TypeError, ValueError):
                payload["max_tokens"] = model_max
        else:
            payload["max_tokens"] = model_max

        logger.info(f"[FINAL] model={model_name}, max_tokens={payload.get('max_tokens')}")

        for unsupported in ("logit_bias", "logprobs", "top_logprobs", "n", "seed", "user", "service_tier"):
            payload.pop(unsupported, None)

        return payload

    @staticmethod
    def validate_request(request_body: Dict[str, Any]) -> None:
        if not isinstance(request_body, dict):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object")

        messages = request_body.get("messages")
        if not messages or not isinstance(messages, list):
            raise HTTPException(status_code=400, detail="Messages field is required and must be an array")

        if not messages:
            raise HTTPException(status_code=400, detail="At least one message is required")

        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                raise HTTPException(status_code=400, detail=f"Message {i} must be an object")
            if "role" not in msg:
                raise HTTPException(status_code=400, detail=f"Message {i} must have 'role' field")
            role = msg["role"]
            if role not in ("system", "user", "assistant", "tool"):
                raise HTTPException(status_code=400, detail=f"Message {i} has invalid role '{role}'")
            if role in ("system", "user") and not msg.get("content"):
                raise HTTPException(status_code=400, detail=f"Message {i} with role '{role}' must have non-empty 'content'")
            if role == "tool" and not msg.get("tool_call_id"):
                raise HTTPException(status_code=400, detail=f"Message {i} with role 'tool' must have 'tool_call_id' field")
            if role == "assistant" and msg.get("tool_calls"):
                for j, tc in enumerate(msg["tool_calls"]):
                    if not isinstance(tc, dict) or not tc.get("id"):
                        raise HTTPException(status_code=400, detail=f"Message {i} tool_call {j} must have 'id' field")


class CredentialManager:

    @staticmethod
    async def get_valid_credential() -> Dict[str, Any]:
        try:
            credential = await codebuddy_token_manager.get_next_credential_async()
            if not credential:
                raise HTTPException(status_code=401, detail="No available CodeBuddy credentials")

            bearer_token = credential.get('bearer_token')
            if not bearer_token:
                raise HTTPException(status_code=401, detail="Invalid CodeBuddy credential")

            return credential
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get credential: {e}")
            raise HTTPException(status_code=401, detail="Credential retrieval failed")


def _should_retry_status(status_code: int) -> bool:
    return status_code in (401, 403, 429)


async def _attempt_request_with_retry(
    request_body: Dict[str, Any],
    client_wants_stream: bool,
    conversation_id: Optional[str] = None,
    conversation_request_id: Optional[str] = None,
    conversation_message_id: Optional[str] = None,
    request_id: Optional[str] = None,
    session_id: Optional[str] = None,
):
    """Try the request up to MAX_KEY_RETRIES times, rotating keys on retryable failures."""
    last_error = None
    # Derive session key from client IP for affinity
    session_key = ""

    for attempt in range(MAX_KEY_RETRIES):
        # --- Session Affinity: try to reuse pinned credential ---
        if attempt == 0 and session_key == "":
            # session_key derived from conversation_id (stable across requests in same OpenCode session)
            session_key = conversation_id or ""

        pinned_cred_id = session_affinity.get_pinned_credential(session_key) if session_key else None

        if pinned_cred_id and attempt == 0:
            # Try to get the pinned credential directly
            idx = codebuddy_token_manager._index_for_credential_id(pinned_cred_id)
            if idx is not None:
                cred_entry = codebuddy_token_manager.credentials[idx]
                credential = cred_entry['data']
                cred_id = pinned_cred_id
                cred_filename = pinned_cred_id
                logger.debug(f"Session affinity: using pinned cred {pinned_cred_id[:12]} for session {session_key[:8]}")
            else:
                # Pinned cred no longer exists
                session_affinity.release_session(session_key)
                credential = await CredentialManager.get_valid_credential()
                cred_id = codebuddy_token_manager.get_credential_id_for_data(credential)
                cred_filename = cred_id or "unknown"
        else:
            credential = await CredentialManager.get_valid_credential()
            cred_id = codebuddy_token_manager.get_credential_id_for_data(credential)
            cred_filename = cred_id or "unknown"

        headers = codebuddy_api_client.generate_codebuddy_headers(
            bearer_token=credential.get('bearer_token'),
            user_id=credential.get('user_id'),
            conversation_id=conversation_id,
            conversation_request_id=conversation_request_id,
            conversation_message_id=conversation_message_id,
            request_id=request_id,
        )

        payload = RequestProcessor.prepare_payload(request_body, session_id=session_id)
        model = payload.get("model", "unknown")
        usage_stats_manager.record_model_usage(model)

        service = CodeBuddyStreamService()

        if client_wants_stream:
            # Stream directly — check status from the stream response itself.
            # No separate probe request (avoids double credit usage).
            try:
                client = await get_http_client()
                stream_response = client.stream("POST", get_codebuddy_api_url(), json=payload, headers=headers)
                response_ctx = await stream_response.__aenter__()
                status = response_ctx.status_code

                if _should_retry_status(status):
                    error_bytes = await response_ctx.aread()
                    error_msg = error_bytes.decode('utf-8', errors='ignore')[:500]
                    await stream_response.__aexit__(None, None, None)
                    logger.warning(f"Key {cred_filename} failed with {status}: {error_msg[:200]}, "
                                   f"attempt {attempt + 1}/{MAX_KEY_RETRIES}")
                    usage_stats_manager.record_credential_failure(cred_filename)
                    cb = CircuitBreakerManager.get_instance()
                    await cb.record_failure(cred_filename, status_code=status, error=error_msg[:200])
                    db = HealthDatabase.get_instance()
                    await db.record_event(CredentialEvent(
                        timestamp=time.time(), credential_id=cred_filename,
                        event_type="failure", status_code=status, error=error_msg[:200]
                    ))
                    if _is_permanently_banned(status, error_msg) and cred_id is not None:
                        await codebuddy_token_manager.disable_key(cred_id)
                        logger.warning(f"Key {cred_filename} auto-disabled: permanently banned (403/11140)")
                    elif status == 429 and cred_id is not None:
                        await codebuddy_token_manager.mark_key_exhausted(cred_id)
                        if session_key:
                            session_affinity.release_session(session_key)
                    elif _is_content_filter_error(error_msg) and cred_id is not None:
                        await codebuddy_token_manager.mark_key_exhausted(cred_id)
                        if session_key:
                            session_affinity.release_session(session_key)
                    last_error = HTTPException(status_code=status, detail=error_msg)
                    continue

                if status != 200:
                    error_bytes = await response_ctx.aread()
                    error_msg = error_bytes.decode('utf-8', errors='ignore')[:500]
                    await stream_response.__aexit__(None, None, None)
                    raise HTTPException(status_code=status, detail=error_msg)

                cb = CircuitBreakerManager.get_instance()
                await cb.record_success(cred_filename)
                db = HealthDatabase.get_instance()
                await db.record_event(CredentialEvent(
                    timestamp=time.time(), credential_id=cred_filename,
                    event_type="success", status_code=200
                ))
                # Pin this credential to the session on first success
                if session_key and cred_id:
                    session_affinity.pin_credential(session_key, cred_id)
                return await service.handle_stream_response_from_open_stream(
                    response_ctx, stream_response, payload, headers, model=model
                )

            except HTTPException:
                raise
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                logger.warning(f"Network error with key {cred_filename}: {e}, attempt {attempt + 1}/{MAX_KEY_RETRIES}")
                usage_stats_manager.record_credential_failure(cred_filename)
                cb = CircuitBreakerManager.get_instance()
                await cb.record_failure(cred_filename, status_code=502, error=str(e)[:200])
                db = HealthDatabase.get_instance()
                await db.record_event(CredentialEvent(
                    timestamp=time.time(), credential_id=cred_filename,
                    event_type="failure", status_code=502, error=str(e)[:200]
                ))
                last_error = HTTPException(status_code=502, detail=str(e))
                continue

        else:
            # Non-streaming: straightforward retry
            try:
                client = await get_http_client()
                response = await client.post(get_codebuddy_api_url(), json=payload, headers=headers)

                if _should_retry_status(response.status_code):
                    error_msg = response.text[:500]
                    logger.warning(f"Key {cred_filename} failed with {response.status_code}: {error_msg[:200]}, "
                                   f"attempt {attempt + 1}/{MAX_KEY_RETRIES}")
                    usage_stats_manager.record_credential_failure(cred_filename)
                    cb = CircuitBreakerManager.get_instance()
                    await cb.record_failure(cred_filename, status_code=response.status_code, error=error_msg[:200])
                    db = HealthDatabase.get_instance()
                    await db.record_event(CredentialEvent(
                        timestamp=time.time(), credential_id=cred_filename,
                        event_type="failure", status_code=response.status_code, error=error_msg[:200]
                    ))
                    if _is_permanently_banned(response.status_code, error_msg) and cred_id is not None:
                        await codebuddy_token_manager.disable_key(cred_id)
                        logger.warning(f"Key {cred_filename} auto-disabled: permanently banned (403/11140)")
                    elif response.status_code == 429 and cred_id is not None:
                        await codebuddy_token_manager.mark_key_exhausted(cred_id)
                    elif _is_content_filter_error(error_msg) and cred_id is not None:
                        await codebuddy_token_manager.mark_key_exhausted(cred_id)
                    last_error = HTTPException(status_code=response.status_code, detail=error_msg)
                    continue

                if response.status_code != 200:
                    error_msg = response.text
                    raise HTTPException(status_code=response.status_code, detail=error_msg)

                request_start = time.monotonic()
                aggregator = StreamResponseAggregator()
                buffer = ""

                async for chunk in response.aiter_text():
                    if not chunk:
                        continue
                    buffer += chunk
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        obj = parse_sse_line(line)
                        if obj:
                            aggregator.process_chunk(obj)

                if buffer.strip():
                    obj = parse_sse_line(buffer.strip())
                    if obj:
                        aggregator.process_chunk(obj)

                total_time = time.monotonic() - request_start
                usage_stats_manager.record_latency(model, total_time, total_time)

                result = aggregator.finalize()
                if "error" in result:
                    raise HTTPException(status_code=502, detail=result["error"]["message"])

                cb = CircuitBreakerManager.get_instance()
                await cb.record_success(cred_filename)
                db = HealthDatabase.get_instance()
                await db.record_event(CredentialEvent(
                    timestamp=time.time(), credential_id=cred_filename,
                    event_type="success", status_code=200, latency_ms=total_time * 1000
                ))
                # Pin session + record quota
                if session_key and cred_id:
                    session_affinity.pin_credential(session_key, cred_id)
                usage_in  = result.get("usage", {}).get("prompt_tokens", 0)
                usage_out = result.get("usage", {}).get("completion_tokens", 0)
                quota_estimator.record_usage(cred_filename, usage_in, usage_out)
                return result

            except HTTPException:
                raise
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                logger.warning(f"Network error with key {cred_filename}: {e}, attempt {attempt + 1}/{MAX_KEY_RETRIES}")
                usage_stats_manager.record_credential_failure(cred_filename)
                cb = CircuitBreakerManager.get_instance()
                await cb.record_failure(cred_filename, status_code=502, error=str(e)[:200])
                db = HealthDatabase.get_instance()
                await db.record_event(CredentialEvent(
                    timestamp=time.time(), credential_id=cred_filename,
                    event_type="failure", status_code=502, error=str(e)[:200]
                ))
                last_error = HTTPException(status_code=502, detail=str(e))
                continue

    # All retries exhausted
    if last_error:
        raise last_error
    raise HTTPException(status_code=503, detail="All credential retries exhausted")


# --- API Endpoints ---

@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    x_conversation_id: Optional[str] = Header(None, alias="X-Conversation-ID"),
    x_conversation_request_id: Optional[str] = Header(None, alias="X-Conversation-Request-ID"),
    x_conversation_message_id: Optional[str] = Header(None, alias="X-Conversation-Message-ID"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    _token: str = Depends(authenticate)
):
    try:
        try:
            request_body = await request.json()
        except Exception as e:
            logger.error(f"Failed to parse request body: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid JSON request body: {str(e)}")

        RequestProcessor.validate_request(request_body)

        logger.info(f"[REQ] model={request_body.get('model')}, max_tokens={request_body.get('max_tokens', 'NOT_SET')}, stream={request_body.get('stream')}")

        client_wants_stream = request_body.get("stream", False)
        model = request_body.get("model", "unknown")
        messages = request_body.get("messages", [])

        # --- Response Dedup Cache (streaming: SSE replay, non-streaming: JSON) ---
        if response_cache.should_cache(messages):
            cached_sse = response_cache.get(model, messages)
            if cached_sse is not None:
                if client_wants_stream:
                    async def replay_cache():
                        yield cached_sse
                        yield 'data: [DONE]\n\n'
                    return StreamingResponse(replay_cache(), media_type="text/event-stream",
                                            headers={**SSE_HEADERS, "X-Cache": "HIT"})
                else:
                    cached_json = _response_cache.get(model, messages, session_id=x_conversation_id)
                    if cached_json is not None:
                        return JSONResponse(content=cached_json, headers={"X-Cache": "HIT"})

        # Non-streaming JSON cache (existing)
        if not client_wants_stream:
            cached = _response_cache.get(model, messages, session_id=x_conversation_id)
            if cached is not None:
                logger.info(f"Cache HIT for model={model}")
                return JSONResponse(content=cached, headers={"X-Cache": "HIT"})

        # --- Cache-Control Injection (promotes prompt caching on Claude backend) ---
        if messages:
            for msg in messages:
                if msg.get("role") == "system" and isinstance(msg.get("content"), str):
                    if "cache_control" not in str(msg.get("content", "")):
                        msg["cache_control"] = {"type": "ephemeral"}
                    break

        result = await _attempt_request_with_retry(
            request_body,
            client_wants_stream,
            conversation_id=x_conversation_id,
            conversation_request_id=x_conversation_request_id,
            conversation_message_id=x_conversation_message_id,
            request_id=x_request_id,
            session_id=x_conversation_id,
        )

        if client_wants_stream:
            return result
        else:
            # Extract session facts from non-streaming responses
            if isinstance(result, dict) and x_conversation_id:
                try:
                    for choice in result.get("choices", []):
                        msg_content = choice.get("message", {}).get("content", "")
                        if msg_content:
                            extract_and_save_facts(msg_content, x_conversation_id)
                            break
                except Exception:
                    pass

            has_tool_calls = False
            if isinstance(result, dict):
                for choice in result.get("choices", []):
                    msg = choice.get("message", {})
                    if msg.get("tool_calls"):
                        has_tool_calls = True
                        break

            if not has_tool_calls and isinstance(result, dict):
                _response_cache.put(model, messages, result, session_id=x_conversation_id)

            return JSONResponse(content=result, headers={"X-Cache": "MISS"})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CodeBuddy V1 API error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/v1/models")
async def list_v1_models(_token: str = Depends(authenticate)):
    try:
        return {
            "object": "list",
            "data": [{
                "id": model,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "codebuddy"
            } for model in get_available_models_list()]
        }
    except Exception as e:
        logger.error(f"Error listing V1 models: {e}")
        raise HTTPException(status_code=500, detail="Failed to list models")


@router.get("/v1/quota", summary="Per-credential quota usage estimates")
async def get_quota_usage(_token: str = Depends(authenticate)):
    try:
        return {
            "daily_budget_tokens" : quota_estimator.DEFAULT_DAILY_TOKEN_BUDGET
                                    if hasattr(quota_estimator, 'DEFAULT_DAILY_TOKEN_BUDGET')
                                    else 500_000,
            "usage"               : quota_estimator.get_all_usage(),
        }
    except Exception as e:
        logger.error(f"Error retrieving quota usage: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve quota usage")


@router.get("/v1/sessions", summary="Active session affinity map")
async def get_active_sessions(_token: str = Depends(authenticate)):
    try:
        return session_affinity.stats()
    except Exception as e:
        logger.error(f"Error retrieving sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve sessions")


@router.get("/v1/stats")
async def get_detailed_stats(_token: str = Depends(authenticate)):
    try:
        stats = usage_stats_manager.get_stats()
        stats["healthy_keys"] = codebuddy_token_manager.get_healthy_keys_count()
        stats["exhausted_keys_count"] = len(codebuddy_token_manager.exhausted_keys)
        stats["filter_count"] = get_filter_count()
        stats["cache_size"] = len(_response_cache._cache)
        return stats
    except Exception as e:
        logger.error(f"Error retrieving stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve stats")


@router.get("/v1/stats/history", summary="Get hourly stats history")
async def get_stats_history(hours: int = 24, _token: str = Depends(authenticate)):
    try:
        if hours < 1:
            hours = 1
        elif hours > 72:
            hours = 72
        return usage_stats_manager.get_hourly_history(hours)
    except Exception as e:
        logger.error(f"Error retrieving stats history: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve stats history")


@router.get("/v1/credentials", summary="List all available credentials")
async def list_credentials(_token: str = Depends(authenticate)):
    try:
        credentials_info = codebuddy_token_manager.get_credentials_info()
        safe_credentials = []

        credentials = codebuddy_token_manager.get_all_credentials()

        for info in credentials_info:
            bearer_token = credentials[info['index']].get("bearer_token", "") if info['index'] < len(credentials) else ""

            if info['time_remaining'] is not None and info['time_remaining'] > 0:
                days, remainder = divmod(info['time_remaining'], 86400)
                hours, remainder = divmod(remainder, 3600)
                minutes = remainder // 60
                time_remaining_str = f"{days}d {hours}h" if days > 0 else f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            else:
                time_remaining_str = "Expired" if info['time_remaining'] is not None else "Unknown"

            safe_credentials.append({
                **info,
                "time_remaining_str": time_remaining_str,
                "has_token": bool(bearer_token),
                "token_preview": f"{bearer_token[:10]}...{bearer_token[-4:]}" if len(bearer_token) > 14 else "Invalid Token"
            })

        return {"credentials": safe_credentials}

    except Exception as e:
        logger.error(f"Failed to list credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v1/credentials", summary="Add a new credential")
async def add_credential(
    request: Request,
    _token: str = Depends(authenticate)
):
    try:
        data = await request.json()
        if not data.get("bearer_token"):
            raise HTTPException(status_code=422, detail="bearer_token is required")

        success = codebuddy_token_manager.add_credential(
            data.get("bearer_token"),
            data.get("user_id"),
            data.get("filename")
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save credential file")

        return {"message": "Credential added successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add credential: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v1/credentials/select", summary="Manually select a credential")
async def select_credential(
    request: Request,
    _token: str = Depends(authenticate)
):
    try:
        data = await request.json()
        credential_id = data.get("credential_id")
        index = data.get("index")

        if credential_id:
            result = await codebuddy_token_manager.set_manual_credential(credential_id)
        elif index is not None:
            result = codebuddy_token_manager.set_manual_credential_by_index(index)
        else:
            raise HTTPException(status_code=422, detail="credential_id or index is required")

        if not result:
            raise HTTPException(status_code=400, detail="Invalid credential")

        return {"message": f"Credential {credential_id or index} selected successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to select credential: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v1/credentials/auto", summary="Resume automatic credential rotation")
async def resume_auto_rotation(_token: str = Depends(authenticate)):
    try:
        await codebuddy_token_manager.resume_auto_rotation()
        return {"message": "Resumed automatic credential rotation"}
    except Exception as e:
        logger.error(f"Failed to resume auto rotation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v1/credentials/toggle-rotation", summary="Toggle automatic credential rotation")
async def toggle_auto_rotation(_token: str = Depends(authenticate)):
    try:
        is_enabled = await codebuddy_token_manager.toggle_auto_rotation()
        status = "enabled" if is_enabled else "disabled"
        return {
            "message": f"Auto rotation {status}",
            "auto_rotation_enabled": is_enabled
        }
    except Exception as e:
        logger.error(f"Failed to toggle auto rotation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/credentials/current", summary="Get current credential info")
async def get_current_credential(_token: str = Depends(authenticate)):
    try:
        return codebuddy_token_manager.get_current_credential_info()
    except Exception as e:
        logger.error(f"Failed to get current credential info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v1/credentials/disable", summary="Disable a credential (skip in rotation)")
async def disable_credential(request: Request, _token: str = Depends(authenticate)):
    """Disable a credential so it is skipped during rotation."""
    try:
        data = await request.json()
        credential_id = data.get("credential_id")
        if not credential_id:
            raise HTTPException(status_code=422, detail="credential_id is required")

        result = await codebuddy_token_manager.disable_key(credential_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"Credential {credential_id} not found")

        return {"message": f"Credential {credential_id} disabled", "credential_id": credential_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disable credential: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v1/credentials/enable", summary="Re-enable a disabled credential")
async def enable_credential(request: Request, _token: str = Depends(authenticate)):
    """Re-enable a previously disabled credential."""
    try:
        data = await request.json()
        credential_id = data.get("credential_id")
        if not credential_id:
            raise HTTPException(status_code=422, detail="credential_id is required")

        result = await codebuddy_token_manager.enable_key(credential_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"Credential {credential_id} not found or not disabled")

        return {"message": f"Credential {credential_id} re-enabled", "credential_id": credential_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enable credential: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v1/credentials/test", summary="Test a specific credential")
async def test_credential(request: Request, _token: str = Depends(authenticate)):
    """Send a minimal chat request with a specific credential to verify it works."""
    try:
        data = await request.json()
        credential_id = data.get("credential_id")
        if not credential_id:
            raise HTTPException(status_code=422, detail="credential_id is required")

        idx = codebuddy_token_manager._index_for_credential_id(credential_id)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"Credential {credential_id} not found")

        cred_entry = codebuddy_token_manager.credentials[idx]
        cred_data = cred_entry.get("data", cred_entry)
        bearer_token = cred_data.get("bearer_token")
        user_id = cred_data.get("user_id")

        if not bearer_token:
            raise HTTPException(status_code=400, detail="Credential has no bearer_token")

        headers = codebuddy_api_client.generate_codebuddy_headers(
            bearer_token=bearer_token,
            user_id=user_id,
        )

        payload = {
            "model": "auto-chat",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hi"},
            ],
            "max_tokens": 5,
            "stream": True,
        }

        start_time = time.time()
        try:
            client = await get_http_client()
            async with client.stream("POST", get_codebuddy_api_url(), json=payload, headers=headers) as response:
                latency_ms = round((time.time() - start_time) * 1000)

                if response.status_code == 200:
                    async for _ in response.aiter_lines():
                        break
                    return {
                        "success": True,
                        "credential_id": credential_id,
                        "latency_ms": latency_ms,
                        "message": f"Key healthy ({latency_ms}ms)",
                    }
                else:
                    error_bytes = await response.aread()
                    error_text = error_bytes.decode('utf-8', errors='ignore')[:300]
                    return {
                        "success": False,
                        "credential_id": credential_id,
                        "latency_ms": latency_ms,
                        "status_code": response.status_code,
                        "message": f"Key failed: HTTP {response.status_code}",
                        "error": error_text,
                    }
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            latency_ms = round((time.time() - start_time) * 1000)
            return {
                "success": False,
                "credential_id": credential_id,
                "latency_ms": latency_ms,
                "message": f"Key failed: {type(e).__name__}",
                "error": str(e),
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test credential: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v1/credentials/delete", summary="Delete a credential")
async def delete_credential(request: Request, _token: str = Depends(authenticate)):
    try:
        data = await request.json()
        credential_id = data.get("credential_id")
        index = data.get("index")

        if credential_id:
            result = await codebuddy_token_manager.delete_credential(credential_id)
        elif index is not None and isinstance(index, int):
            result = codebuddy_token_manager.delete_credential_by_index(index)
        else:
            raise HTTPException(status_code=422, detail="credential_id or integer index is required")

        if not result:
            raise HTTPException(status_code=400, detail="Invalid credential or failed to delete")

        return {"message": f"Credential {credential_id or index} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete credential: {e}")
        raise HTTPException(status_code=500, detail=str(e))
