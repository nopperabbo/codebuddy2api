import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ.setdefault("CODEBUDDY_PASSWORD", "test123")
os.environ.setdefault("CODEBUDDY_PORT", "8003")
os.environ.setdefault("CODEBUDDY_HOST", "0.0.0.0")
os.environ.setdefault("CODEBUDDY_API_ENDPOINT", "https://www.codebuddy.ai")
os.environ.setdefault("CODEBUDDY_CREDS_DIR", ".codebuddy_creds")
os.environ.setdefault("CODEBUDDY_LOG_LEVEL", "WARNING")
os.environ.setdefault("CODEBUDDY_MODELS", "claude-opus-4.6,gpt-5")
os.environ.setdefault("CODEBUDDY_ROTATION_COUNT", "1")

from src.keyword_replacer import (
    apply_keyword_replacement,
    reverse_replacements,
    translate_chinese_errors,
    deobfuscate_response,
    load_filters,
    get_filter_count,
)


class TestKeywordReplacement:
    def test_obfuscates_claude(self):
        assert "CL4ude" in apply_keyword_replacement("Claude is great")

    def test_obfuscates_openai(self):
        assert "0penAI" in apply_keyword_replacement("OpenAI makes GPT")

    def test_obfuscates_anthropic(self):
        result = apply_keyword_replacement("anthropic released claude")
        assert "anthr0pic" in result
        assert "cl4ude" in result

    def test_obfuscates_cursor(self):
        assert "Crsr" in apply_keyword_replacement("Cursor IDE")

    def test_obfuscates_gemini(self):
        assert "Gmni" in apply_keyword_replacement("Gemini model")

    def test_obfuscates_deepseek(self):
        assert "DpSk" in apply_keyword_replacement("DeepSeek v3")

    def test_preserves_non_matching_text(self):
        text = "Hello world, this is a test"
        assert apply_keyword_replacement(text) == text

    def test_empty_string(self):
        assert apply_keyword_replacement("") == ""

    def test_non_string_returns_as_is(self):
        assert apply_keyword_replacement(None) is None
        assert apply_keyword_replacement(42) == 42


class TestReverseReplacement:
    def test_reverses_claude(self):
        assert "Claude" in reverse_replacements("CL4ude is great")

    def test_reverses_openai(self):
        assert "OpenAI" in reverse_replacements("0penAI makes models")

    def test_reverses_anthropic(self):
        assert "anthropic" in reverse_replacements("anthr0pic released")

    def test_reverses_cursor(self):
        assert "Cursor" in reverse_replacements("Crsr IDE")

    def test_reverses_gemini(self):
        assert "Gemini" in reverse_replacements("Gmni model")

    def test_reverses_deepseek(self):
        assert "DeepSeek" in reverse_replacements("DpSk v3")

    def test_reverses_chatgpt(self):
        assert "ChatGPT" in reverse_replacements("AI Chat is popular")

    def test_reverses_copilot(self):
        assert "Copilot" in reverse_replacements("CoPlt helps coding")

    def test_roundtrip_claude(self):
        original = "Claude Opus is powerful"
        obfuscated = apply_keyword_replacement(original)
        restored = reverse_replacements(obfuscated)
        assert "Claude" in restored
        assert "Opus" in restored

    def test_empty_string(self):
        assert reverse_replacements("") == ""

    def test_non_string(self):
        assert reverse_replacements(None) is None


class TestChineseErrorTranslation:
    def test_sensitive_content(self):
        result = translate_chinese_errors("\u62b1\u6b49\uff0c\u7cfb\u7edf\u68c0\u6d4b\u5230\u60a8\u5f53\u524d\u8f93\u5165\u7684\u4fe1\u606f\u5b58\u5728\u654f\u611f\u5185\u5bb9")
        assert "Content filter triggered" in result

    def test_retry_message(self):
        result = translate_chinese_errors("\u8bf7\u68c0\u67e5\u540e\u91cd\u65b0\u8f93\u5165")
        assert "Please modify your input" in result

    def test_balance_error(self):
        result = translate_chinese_errors("\u8d26\u6237\u4f59\u989d\u4e0d\u8db3")
        assert "Insufficient account balance" in result

    def test_rate_limit(self):
        result = translate_chinese_errors("\u64cd\u4f5c\u592a\u9891\u7e41")
        assert "Too many requests" in result

    def test_mixed_content(self):
        result = translate_chinese_errors("Error: \u7cfb\u7edf\u68c0\u6d4b\u5230\u654f\u611f\u5185\u5bb9, please retry")
        assert "Sensitive content detected" in result
        assert "please retry" in result

    def test_no_chinese(self):
        text = "Normal English error message"
        assert translate_chinese_errors(text) == text

    def test_deobfuscate_response_combined(self):
        text = "CL4ude says: \u8bf7\u7a0d\u540e\u518d\u8bd5"
        result = deobfuscate_response(text)
        assert "Claude" in result
        assert "Please try again later" in result


class TestFilterConfig:
    def test_load_filters(self):
        load_filters()
        counts = get_filter_count()
        assert counts["replacements"] > 0
        assert counts["regex_patterns"] > 0
        assert counts["chinese_error_translations"] > 0

    def test_filter_count_structure(self):
        counts = get_filter_count()
        assert "replacements" in counts
        assert "regex_patterns" in counts
        assert "chinese_error_translations" in counts


class TestLRUCache:
    def test_cache_hit_miss(self):
        from src.codebuddy_router import LRUCache
        cache = LRUCache(max_size=10, ttl_seconds=60)

        model = "test-model"
        messages = [{"role": "user", "content": "hello"}]
        response = {"id": "123", "choices": []}

        assert cache.get(model, messages) is None

        cache.put(model, messages, response)
        cached = cache.get(model, messages)
        assert cached is not None
        assert cached["id"] == "123"

    def test_cache_ttl_expiry(self):
        from src.codebuddy_router import LRUCache
        cache = LRUCache(max_size=10, ttl_seconds=1)

        model = "test-model"
        messages = [{"role": "user", "content": "hello"}]
        response = {"id": "456"}

        cache.put(model, messages, response)
        assert cache.get(model, messages) is not None

        time.sleep(1.1)
        assert cache.get(model, messages) is None

    def test_cache_max_size(self):
        from src.codebuddy_router import LRUCache
        cache = LRUCache(max_size=3, ttl_seconds=60)

        for i in range(5):
            cache.put(f"model-{i}", [{"role": "user", "content": f"msg-{i}"}], {"id": str(i)})

        assert len(cache._cache) == 3

    def test_cache_different_messages(self):
        from src.codebuddy_router import LRUCache
        cache = LRUCache(max_size=10, ttl_seconds=60)

        cache.put("model", [{"role": "user", "content": "hello"}], {"id": "1"})
        cache.put("model", [{"role": "user", "content": "world"}], {"id": "2"})

        r1 = cache.get("model", [{"role": "user", "content": "hello"}])
        r2 = cache.get("model", [{"role": "user", "content": "world"}])
        assert r1["id"] == "1"
        assert r2["id"] == "2"
