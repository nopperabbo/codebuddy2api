"""Model Router — meta-model routing for auto-smart/auto-fast/auto-cheap."""
import re
import logging

logger = logging.getLogger(__name__)

from .context_manager import _estimate_tokens, _message_tokens

REASONING_PATTERN = re.compile(
    r"\b(reasoning|math|algorithm|prove|calculate|theorem|proof|equation)\b", re.IGNORECASE
)
ARCHITECTURE_PATTERN = re.compile(
    r"\b(refactor|architecture|design|migrate|rewrite|multi.?file|restructure)\b", re.IGNORECASE
)
SIMPLE_PATTERN = re.compile(
    r"\b(fix\s*typo|rename|simple|quick|trivial|minor)\b", re.IGNORECASE
)

META_MODELS = {"auto-smart", "auto-fast", "auto-cheap"}


def _get_last_user_text(messages: list) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                return " ".join(parts)
    return ""


def _total_tokens(messages: list) -> int:
    return sum(_message_tokens(m) for m in messages)


def route_model(model: str, messages: list) -> tuple:
    if model not in META_MODELS:
        return (model, "passthrough")

    if model == "auto-fast":
        logger.info("Auto-routed to gpt-5-mini (reason: auto-fast)")
        return ("gpt-5-mini", "auto-fast")

    if model == "auto-cheap":
        logger.info("Auto-routed to gpt-5-nano (reason: auto-cheap)")
        return ("gpt-5-nano", "auto-cheap")

    # auto-smart routing
    total = _total_tokens(messages)
    last_text = _get_last_user_text(messages)

    if total > 100_000:
        reason = f"large context ({total} tokens)"
        logger.info(f"Auto-routed to gemini-3.1-pro (reason: {reason})")
        return ("gemini-3.1-pro", reason)

    if REASONING_PATTERN.search(last_text):
        reason = "reasoning/math task detected"
        logger.info(f"Auto-routed to o4-mini (reason: {reason})")
        return ("o4-mini", reason)

    if ARCHITECTURE_PATTERN.search(last_text):
        reason = "architecture/refactor task detected"
        logger.info(f"Auto-routed to claude-opus-4.6 (reason: {reason})")
        return ("claude-opus-4.6", reason)

    if SIMPLE_PATTERN.search(last_text):
        reason = "simple task detected"
        logger.info(f"Auto-routed to gpt-5-mini (reason: {reason})")
        return ("gpt-5-mini", reason)

    logger.info("Auto-routed to gpt-5.5 (reason: default auto-smart)")
    return ("gpt-5.5", "default auto-smart")
