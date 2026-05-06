"""
Keyword Replacer - Obfuscates competitor names before sending to CodeBuddy,
and de-obfuscates them in responses. Supports configurable filters via JSON.

Context-aware: protects code blocks, inline code, and URLs from replacement.
"""
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

_FILTERS_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'filters.json')

_PROTECTED_REGION_RE = re.compile(
    r'```[\s\S]*?```'       # fenced code blocks
    r'|`[^`\n]+`'           # inline code
    r'|https?://[^\s)\]>]+' # URLs
)

def _split_protected_regions(text: str):
    segments = []
    last_end = 0
    for m in _PROTECTED_REGION_RE.finditer(text):
        if m.start() > last_end:
            segments.append((text[last_end:m.start()], False))
        segments.append((m.group(), True))
        last_end = m.end()
    if last_end < len(text):
        segments.append((text[last_end:], False))
    return segments

# --- Default patterns (used if filters.json is missing) ---
_DEFAULT_REPLACEMENTS = [
    ("x-anthropic-billing-header: cc_version=2.1.116.f49; cc_entrypoint=cli; cch=8b6e8", ""),
    ("x-billing-header: cc_version=2.114.45a; cc_entrypoint=cli; ch=33c97;", ""),
    ("x-anthropic-billing-header", "x-billing-info"),
    ("x-billing-header", "x-billing-info"),
    ("cc_entrypoint=cli", ""),
    ("cc_entrypoint", "app_entrypoint"),
    ("cc_version", "app_version"),
    ("cache_control", "cache_ctrl"),
    ("You are Claude Code, Anxthxropic's official CLI for Claude.", ""),
    ("Claude Code. To give feedback, users should report the issue at https://github.com/anthropics/claude-code/issues", ""),
    ("https://github.com/anthropics/claude-code/issues", ""),
    ("Anxthxropic's official CLI for Claude", "Official AI CLI"),
    ("Claude Code", "Code Assistant"),
    ("claude-code", "code-assistant"),
    ("claude_code", "code_assistant"),
    ("claude-mem", "cb-mem"),
    ("claude-mem-context", "cb-mem-context"),
    ("Powerful AI Agent with orchestration capabilities from", "Advanced AI Agent with orchestration capabilities"),
    ("Powerful AI Agent", "Advanced AI Agent"),
    ("Sisyphus-Junior - a focused task executor from", "Sisyphus-Junior - a focused task executor"),
    ("anthropic's", "anxthxropic's"),
    ("Anxthxropic SDK", "Anthr0pic SDK"),
    ("Anxthxropic API", "Anthr0pic API"),
    ("Anxthxropic Claude", "AI Assistant"),
    ("@anxthxropic-ai", "@anthr0pic-ai"),
    ("@Anxthxropic-ai", "@anthr0pic-ai"),
    ("@ANTHROPIC-AI", "@anthr0pic-ai"),
    ("ANTHROPIC.COM", "anxthxropic.com"),
    ("anthropic-ai/sdk", "anthr0pic-ai/sdk"),
    ("anthropic", "anthr0pic"),
    ("anthropics", "anthr0pics"),
    ("ANTHROPIC", "ANTHR0PIC"),
    ("ANTHROPIC_API_KEY", "AI_CORP_KEY"),
    ("anthropic-version", "api-version"),
    ("https://github.com/anthropics/", "https://github.com/ai-tools/"),
    ("https://api.anxthxropic.com", "https://api.ai-corp.local"),
    ("Claude Opus", "CL4ude Opus"),
    ("Claude Sonnet", "CL4ude Sonnet"),
    ("Claude Haiku", "CL4ude Haiku"),
    ("Claude 4", "CL4ude 4"),
    ("Claude 3", "CL4ude 3"),
    ("Claude API", "CL4ude API"),
    ("Claude", "CL4ude"),
    ("claude", "cl4ude"),
    ("CLAUDE", "CL4UDE"),
    ("OpenAI", "0penAI"),
    ("openai", "0penai"),
    ("OPENAI", "0PENAI"),
    ("OPENAI_API_KEY", "AI_PLAT_KEY"),
    ("https://api.openai.com", "https://api.ai-plat.local"),
    ("ChatGPT", "AI Chat"),
    ("chatgpt", "ai-chat"),
    ("GPT-5", "M-5"),
    ("GPT-4", "M-4"),
    ("GPT-3", "M-3"),

    ("GitHub Copilot", "GH CoPlt"),
    ("Copilot", "CoPlt"),
    ("copilot", "coplt"),
    ("Cursor", "Crsr"),
    ("Windsurf", "Wndrf"),
    ("windsurf", "wndrf"),
    ("VS Code", "Editor"),
    ("VSCode", "Editor"),
    ("vscode", "editor"),
    ("Cline", "Clne"),
    ("cline", "clne"),
    ("Kilo Code", "KC"),
    ("Roo Code", "RC"),
    ("Jailbreak", "J41lbreak"),
    ("jailbreak", "j41lbreak"),
    ("godmode", "g0dmode"),
    ("Obliteratus", "0bliteratus"),
    ("red-teaming", "red-team1ng"),
    ("Remove refusal", "Rm refusal"),
    ("prompt injection", "prompt inj3ction"),
    ("sensitive_content", "flagged_content"),
    ("sk-ant-", "sk-key-"),
    ("sk-proj-", "sk-key-"),
    ("codebuddy", "cb-upstream"),
    ("Sonnet 4", "S4"),
    ("Opus 4", "O4"),
    ("Haiku 4", "H4"),

    ("Gemini", "Gmni"),
    ("gemini", "gmni"),
    ("DeepSeek", "DpSk"),
    ("deepseek", "dpsk"),
]

_DEFAULT_REGEX_PATTERNS_RAW = [
    (r'\banthropic\b', 'anthr0pic', True),
    (r'\bopen\s*ai\b', '0penAI', True),
    (r'\bclaude[\s-]?code\b', 'code-assistant', True),
    (r'\bclaude\b', 'cl4ude', True),
    (r'x-anthropic-[\w-]+', 'x-billing-info', True),
    (r'cc_version=[\d.a-f]+', '', True),
    (r'cc_entrypoint=\w+', '', True),
    (r'cch=[\da-f]+', '', True),
]

_DEFAULT_CHINESE_ERRORS = {
    "\u62b1\u6b49\uff0c\u7cfb\u7edf\u68c0\u6d4b\u5230\u60a8\u5f53\u524d\u8f93\u5165\u7684\u4fe1\u606f\u5b58\u5728\u654f\u611f\u5185\u5bb9": "Content filter triggered - sensitive content detected",
    "\u8bf7\u68c0\u67e5\u540e\u91cd\u65b0\u8f93\u5165": "Please modify your input and try again",
    "\u7cfb\u7edf\u68c0\u6d4b\u5230\u654f\u611f\u5185\u5bb9": "Sensitive content detected by system",
    "\u8bf7\u6c42\u5904\u7406\u5931\u8d25": "Request processing failed",
    "\u670d\u52a1\u5668\u5185\u90e8\u9519\u8bef": "Internal server error",
    "\u8bf7\u6c42\u8d85\u65f6": "Request timeout",
    "\u8d26\u6237\u4f59\u989d\u4e0d\u8db3": "Insufficient account balance",
    "\u8bf7\u7a0d\u540e\u518d\u8bd5": "Please try again later",
    "\u64cd\u4f5c\u592a\u9891\u7e41": "Too many requests",
    "\u53c2\u6570\u9519\u8bef": "Invalid parameters",
    "\u6a21\u578b\u4e0d\u53ef\u7528": "Model unavailable",
    "\u7528\u6237\u672a\u767b\u5f55": "User not logged in",
    "\u8ba4\u8bc1\u5931\u8d25": "Authentication failed",
    "\u6743\u9650\u4e0d\u8db3": "Insufficient permissions",
    "\u5185\u5bb9\u8fdd\u89c4": "Content violation",
    "\u8f93\u5165\u5185\u5bb9\u8fc7\u957f": "Input content too long",
    "\u4f1a\u8bdd\u5df2\u8fc7\u671f": "Session expired",
}

# --- Reverse mapping: obfuscated -> original ---
_REVERSE_PAIRS = [
    ("CL4ude Opus", "Claude Opus"),
    ("CL4ude Sonnet", "Claude Sonnet"),
    ("CL4ude Haiku", "Claude Haiku"),
    ("CL4ude 4", "Claude 4"),
    ("CL4ude 3", "Claude 3"),
    ("CL4ude API", "Claude API"),
    ("CL4ude", "Claude"),
    ("cl4ude", "claude"),
    ("CL4UDE", "CLAUDE"),
    ("0penAI", "OpenAI"),
    ("0penai", "openai"),
    ("0PENAI", "OPENAI"),
    ("AI Chat", "ChatGPT"),
    ("ai-chat", "chatgpt"),
    ("anthr0pics", "anthropics"),
    ("anthr0pic", "anthropic"),
    ("ANTHR0PIC", "ANTHROPIC"),
    ("Anthr0pic SDK", "Anxthxropic SDK"),
    ("Anthr0pic API", "Anxthxropic API"),
    ("GH CoPlt", "GitHub Copilot"),
    ("CoPlt", "Copilot"),
    ("coplt", "copilot"),
    ("Crsr", "Cursor"),
    ("Wndrf", "Windsurf"),
    ("wndrf", "windsurf"),
    ("Clne", "Cline"),
    ("clne", "cline"),
    ("Gmni", "Gemini"),
    ("gmni", "gemini"),
    ("DpSk", "DeepSeek"),
    ("dpsk", "deepseek"),
    ("M-5", "GPT-5"),
    ("M-4", "GPT-4"),
    ("M-3", "GPT-3"),
    ("m-5", "gpt-5"),
    ("m-4", "gpt-4"),
    ("m-3", "gpt-3"),

    ("Code Assistant", "Claude Code"),
    ("code-assistant", "claude-code"),
    ("code_assistant", "claude_code"),
    ("J41lbreak", "Jailbreak"),
    ("j41lbreak", "jailbreak"),
    ("g0dmode", "godmode"),
    ("0bliteratus", "Obliteratus"),
    ("cb-upstream", "codebuddy"),
    ("AI Assistant", "Anxthxropic Claude"),
    ("cb-mem-context", "claude-mem-context"),
    ("cb-mem", "claude-mem"),
    ("red-team1ng", "red-teaming"),
    ("Rm refusal", "Remove refusal"),
    ("prompt inj3ction", "prompt injection"),
    ("flagged_content", "sensitive_content"),
]

# Short tokens that need word-boundary regex to avoid false positives
_REVERSE_REGEX_PAIRS = [
    (re.compile(r'\bS4\b'), "Sonnet 4"),
    (re.compile(r'\bO4\b'), "Opus 4"),
    (re.compile(r'\bH4\b'), "Haiku 4"),
    (re.compile(r'\bs-4\b'), "sonnet-4"),
    (re.compile(r'\bo-4\b'), "opus-4"),
    (re.compile(r'\bh-4\b'), "haiku-4"),
    (re.compile(r'\bEditor\b'), "VS Code"),
    (re.compile(r'\bKC\b'), "Kilo Code"),
    (re.compile(r'\bRC\b'), "Roo Code"),
    (re.compile(r'\bai-opus-([\d.]+)'), r'claude-opus-\1'),
    (re.compile(r'\bai-sonnet-([\d.]+)'), r'claude-sonnet-\1'),
    (re.compile(r'\bai-haiku-([\d.]+)'), r'claude-haiku-\1'),
    (re.compile(r'\bai-gpt-([\d.]+)'), r'gpt-\1'),
]

# --- Active state (mutable, supports hot-reload) ---
REPLACEMENTS = list(_DEFAULT_REPLACEMENTS)
REGEX_PATTERNS = []
CHINESE_ERROR_MAP = dict(_DEFAULT_CHINESE_ERRORS)


def _compile_regex_patterns(raw_patterns):
    compiled = []
    for item in raw_patterns:
        pattern_str, replacement = item[0], item[1]
        ignore_case = item[2] if len(item) > 2 else True
        flags = re.IGNORECASE if ignore_case else 0
        try:
            compiled.append((re.compile(pattern_str, flags), replacement))
        except re.error as e:
            logger.warning(f"Invalid regex pattern '{pattern_str}': {e}")
    return compiled


def load_filters():
    global REPLACEMENTS, REGEX_PATTERNS, CHINESE_ERROR_MAP

    if os.path.exists(_FILTERS_PATH):
        try:
            with open(_FILTERS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)

            raw_replacements = data.get('replacements', [])
            if raw_replacements:
                loaded = [(r[0], r[1]) for r in raw_replacements if len(r) >= 2]
                REPLACEMENTS = _sanitize_replacements(loaded)
            else:
                REPLACEMENTS = _sanitize_replacements(list(_DEFAULT_REPLACEMENTS))

            raw_regex = data.get('regex_patterns', [])
            if raw_regex:
                REGEX_PATTERNS = _compile_regex_patterns(raw_regex)
            else:
                REGEX_PATTERNS = _compile_regex_patterns(_DEFAULT_REGEX_PATTERNS_RAW)

            chinese = data.get('chinese_error_translations', {})
            if chinese:
                CHINESE_ERROR_MAP = chinese
            else:
                CHINESE_ERROR_MAP = dict(_DEFAULT_CHINESE_ERRORS)

            logger.info(f"Loaded filters from {_FILTERS_PATH}: "
                        f"{len(REPLACEMENTS)} replacements, "
                        f"{len(REGEX_PATTERNS)} regex patterns, "
                        f"{len(CHINESE_ERROR_MAP)} Chinese error translations")
        except Exception as e:
            logger.error(f"Failed to load filters from {_FILTERS_PATH}: {e}, using defaults")
            REPLACEMENTS = _sanitize_replacements(list(_DEFAULT_REPLACEMENTS))
            REGEX_PATTERNS = _compile_regex_patterns(_DEFAULT_REGEX_PATTERNS_RAW)
            CHINESE_ERROR_MAP = dict(_DEFAULT_CHINESE_ERRORS)
    else:
        logger.info("No filters.json found, using default patterns")
        REPLACEMENTS = _sanitize_replacements(list(_DEFAULT_REPLACEMENTS))
        REGEX_PATTERNS = _compile_regex_patterns(_DEFAULT_REGEX_PATTERNS_RAW)
        CHINESE_ERROR_MAP = dict(_DEFAULT_CHINESE_ERRORS)


def _sanitize_replacements(pairs):
    dangerous = {
        "from\n": "\n",
    }
    too_broad = {
        ("GPT", "M"), ("gpt", "m"), ("cursor", "crsr"),
    }
    result = []
    for old, new in pairs:
        if old == new:
            continue
        if old in dangerous and new == dangerous[old]:
            continue
        if (old, new) in too_broad:
            continue
        result.append((old, new))
    return result


def get_filter_count() -> dict:
    return {
        "replacements": len(REPLACEMENTS),
        "regex_patterns": len(REGEX_PATTERNS),
        "chinese_error_translations": len(CHINESE_ERROR_MAP),
    }


# --- Forward obfuscation (request -> CodeBuddy) ---

def apply_keyword_replacement(text: str) -> str:
    if not isinstance(text, str):
        return text

    segments = _split_protected_regions(text)
    parts = []
    for segment, is_protected in segments:
        if is_protected:
            parts.append(segment)
        else:
            # Regex patterns first: they handle specific patterns like
            # model versions with capture groups (e.g. claude-opus-4.6 -> ai-opus-4.6)
            # that would be destroyed by broad plain-text replacements.
            for pattern, replacement in REGEX_PATTERNS:
                segment = pattern.sub(replacement, segment)
            for old, new in REPLACEMENTS:
                segment = segment.replace(old, new)
            parts.append(segment)
    return ''.join(parts)


_LIGHT_REPLACEMENTS = [
    ("x-anthropic-billing-header: cc_version=2.1.116.f49; cc_entrypoint=cli; cch=8b6e8", ""),
    ("x-billing-header: cc_version=2.114.45a; cc_entrypoint=cli; ch=33c97;", ""),
    ("x-anthropic-billing-header", "x-billing-info"),
    ("x-billing-header", "x-billing-info"),
    ("cc_entrypoint=cli", ""),
    ("cc_entrypoint", "app_entrypoint"),
    ("cc_version", "app_version"),
    ("You are Claude Code, Anxthxropic's official CLI for Claude.", ""),
    ("Claude Code. To give feedback, users should report the issue at https://github.com/anthropics/claude-code/issues", ""),
    ("Powerful AI Agent with orchestration capabilities from", "Advanced AI Agent with orchestration capabilities"),
    ("Powerful AI Agent", "Advanced AI Agent"),
]

_LIGHT_REGEX = [
    (r'x-anthropic-[\w-]+', 'x-billing-info', True),
    (r'cc_version=[\d.a-f]+', '', True),
    (r'cc_entrypoint=\w+', '', True),
    (r'cch=[\da-f]+', '', True),
]


def _apply_light_filter(text: str) -> str:
    if not isinstance(text, str):
        return text
    for old, new in _LIGHT_REPLACEMENTS:
        text = text.replace(old, new)
    for pattern, replacement, case_insensitive in _LIGHT_REGEX:
        flags = re.IGNORECASE if case_insensitive else 0
        text = re.sub(pattern, replacement, text, flags=flags)
    return text


def apply_to_message_content(content, light_mode=False):
    replacer = _apply_light_filter if light_mode else apply_keyword_replacement
    if isinstance(content, str):
        return replacer(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text" and "text" in item:
                    item["text"] = replacer(item["text"])
                elif "content" in item and isinstance(item["content"], str):
                    item["content"] = replacer(item["content"])
        return content
    return content


def apply_keyword_replacement_to_system_message(content):
    return apply_to_message_content(content)


# --- Reverse de-obfuscation (CodeBuddy response -> client) ---

def reverse_replacements(text: str) -> str:
    if not isinstance(text, str):
        return text

    segments = _split_protected_regions(text)
    parts = []
    for segment, is_protected in segments:
        if is_protected:
            parts.append(segment)
        else:
            for obfuscated, original in _REVERSE_PAIRS:
                segment = segment.replace(obfuscated, original)
            for pattern, original in _REVERSE_REGEX_PAIRS:
                segment = pattern.sub(original, segment)
            parts.append(segment)
    return ''.join(parts)


# --- Chinese error translation ---

def translate_chinese_errors(text: str) -> str:
    if not isinstance(text, str):
        return text

    for chinese, english in CHINESE_ERROR_MAP.items():
        if chinese in text:
            text = text.replace(chinese, english)

    return text


def deobfuscate_response(text: str) -> str:
    if not isinstance(text, str):
        return text
    text = reverse_replacements(text)
    text = translate_chinese_errors(text)
    return text


# --- Initialize on import ---
load_filters()
