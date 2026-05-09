"""Context Manager — auto-trims conversation to fit model context windows."""
import re
import logging

logger = logging.getLogger(__name__)

CONTEXT_LIMITS = {
    "claude-opus-4.6": (200_000, 170_000),
    "gpt-5.5": (128_000, 108_000),
    "gpt-5": (128_000, 108_000),
    "gemini-2.5-pro": (1_000_000, 850_000),
    "gemini-2.5-flash": (1_000_000, 850_000),
    "gemini-3.1-pro": (1_000_000, 850_000),
    "o4-mini": (128_000, 108_000),
    "claude-haiku-4.5": (200_000, 170_000),
}

DEFAULT_LIMIT = (128_000, 108_000)

CJK_RANGE = re.compile(r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]")


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk_chars = len(CJK_RANGE.findall(text))
    ascii_chars = len(text) - cjk_chars
    return (ascii_chars // 4) + (cjk_chars // 2)


def _message_tokens(msg: dict) -> int:
    content = msg.get("content", "")
    if isinstance(content, str):
        return _estimate_tokens(content)
    if isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, dict):
                total += _estimate_tokens(block.get("text", ""))
                total += _estimate_tokens(block.get("content", ""))
        return total
    return 0


def _is_tool_result(msg: dict) -> bool:
    return msg.get("role") == "tool" or msg.get("type") == "tool_result"


def _is_tool_use(msg: dict) -> bool:
    if msg.get("role") == "assistant":
        content = msg.get("content", "")
        if isinstance(content, list):
            return any(b.get("type") == "tool_use" for b in content if isinstance(b, dict))
        if msg.get("tool_calls"):
            return True
    return False


def _get_tool_use_ids(msg: dict) -> set:
    ids = set()
    content = msg.get("content", "")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                ids.add(block.get("id", ""))
    for tc in msg.get("tool_calls", []):
        ids.add(tc.get("id", ""))
    return ids


def _get_tool_result_id(msg: dict) -> str:
    return msg.get("tool_use_id", "") or msg.get("tool_call_id", "")


def manage_context(messages: list, model: str) -> list:
    if not messages:
        return messages

    _, threshold = CONTEXT_LIMITS.get(model, DEFAULT_LIMIT)

    total_tokens = sum(_message_tokens(m) for m in messages)
    if total_tokens <= threshold:
        return messages

    logger.info(f"Context trimming: {total_tokens} tokens > {threshold} threshold for {model}")

    system_msgs = []
    conversation = []

    for msg in messages:
        if msg.get("role") == "system":
            system_msgs.append(msg)
        else:
            conversation.append(msg)

    if len(conversation) <= 4:
        return messages

    original_count = len(conversation)

    while len(conversation) > 4:
        current_tokens = sum(_message_tokens(m) for m in system_msgs) + sum(_message_tokens(m) for m in conversation)
        if current_tokens <= threshold:
            break

        removed = conversation.pop(0)

        if _is_tool_use(removed):
            orphaned_ids = _get_tool_use_ids(removed)
            conversation = [
                m for m in conversation
                if not (_is_tool_result(m) and _get_tool_result_id(m) in orphaned_ids)
            ]

    dropped_tool_use_ids = set()
    all_tool_use_ids = set()
    for msg in conversation:
        if _is_tool_use(msg):
            all_tool_use_ids.update(_get_tool_use_ids(msg))

    final_conversation = []
    for msg in conversation:
        if _is_tool_result(msg):
            result_id = _get_tool_result_id(msg)
            if result_id and result_id not in all_tool_use_ids:
                dropped_tool_use_ids.add(result_id)
                continue
        final_conversation.append(msg)

    trimmed_count = original_count - len(final_conversation)

    if trimmed_count > 0:
        summary_msg = {
            "role": "user",
            "content": f"[Previous {trimmed_count} messages truncated to fit context window]",
        }
        result = system_msgs + [summary_msg] + final_conversation
    else:
        result = system_msgs + final_conversation

    new_tokens = sum(_message_tokens(m) for m in result)
    logger.info(f"Context trimmed: {total_tokens} -> {new_tokens} tokens ({original_count} -> {len(final_conversation)} messages)")

    return result
