"""
Prompt Enhancer — auto-enhances prompts before sending to CodeBuddy.
3 layers: auto system prompt, prompt quality detection, task-type detection.
"""
import re
import logging

logger = logging.getLogger(__name__)

CODING_SYSTEM_PROMPT = (
    "You are an expert software engineer. Write clean, production-ready code with "
    "proper error handling, type hints, and clear documentation. Follow best practices "
    "for the language being used. Explain your reasoning when making design decisions. "
    "If the request is ambiguous, state your assumptions before proceeding."
)

TASK_PATTERNS = {
    "fix": (
        re.compile(r"\b(fix|error|bug|crash|broken|fail|issue|traceback|exception)\b", re.IGNORECASE),
        "Analyze root cause first, then provide minimal fix",
    ),
    "refactor": (
        re.compile(r"\b(refactor|restructure|reorganize|clean\s*up|improve\s*structure)\b", re.IGNORECASE),
        "Preserve existing behavior, improve structure",
    ),
    "explain": (
        re.compile(r"\b(explain|how\s*does|what\s*is|why\s*does|describe|walk\s*through)\b", re.IGNORECASE),
        "Explain step by step with examples",
    ),
    "create": (
        re.compile(r"\b(create|build|implement|write|generate|make|develop|add)\b", re.IGNORECASE),
        "Provide complete implementation with all imports",
    ),
}


def _count_words(text: str) -> int:
    return len(text.split())


def _has_code_block(text: str) -> bool:
    return "```" in text or "    " in text


def _get_system_word_count(messages: list) -> int:
    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            if isinstance(content, str):
                return _count_words(content)
    return 0


def _has_system_message(messages: list) -> bool:
    return any(msg.get("role") == "system" for msg in messages)


def _get_last_user_content(messages: list) -> str:
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


def enhance_prompt(messages: list) -> list:
    if not messages:
        return messages

    # Config toggle — lazy import to avoid circular dependency
    from config import get_prompt_enhance_enabled
    if not get_prompt_enhance_enabled():
        return messages

    # If client sent a system prompt longer than 200 words, skip all enhancement
    if _get_system_word_count(messages) > 200:
        return messages

    result = list(messages)

    # Layer 1: Auto System Prompt
    if not _has_system_message(result):
        result.insert(0, {"role": "system", "content": CODING_SYSTEM_PROMPT})
        logger.debug("Injected auto system prompt")

    # Get last user message for layers 2 and 3
    last_user = _get_last_user_content(result)
    if not last_user:
        return result

    enhancements = []

    # Layer 2: Prompt Quality Detection (only very short prompts)
    if _count_words(last_user) < 10 and not _has_code_block(last_user):
        enhancements.append("Please provide a complete solution with error handling")

    # Layer 3: Task-Type Detection
    for task_type, (pattern, hint) in TASK_PATTERNS.items():
        if pattern.search(last_user):
            enhancements.append(hint)
            break

    # Insert hints as a SEPARATE system message after existing system messages
    if enhancements:
        hint_text = "Task guidance: " + "; ".join(enhancements)
        hint_msg = {"role": "system", "content": hint_text}

        # Find insertion point: after last system message, before conversation
        insert_idx = 0
        for i, msg in enumerate(result):
            if msg.get("role") == "system":
                insert_idx = i + 1
        result.insert(insert_idx, hint_msg)

    return result
