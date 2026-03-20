"""Tests for token counting and formatting utilities."""

from unittest.mock import patch

from sideclaw.utils.tokens import (
    CHARS_PER_TOKEN_FALLBACK,
    count_message_tokens,
    count_tokens,
    format_duration,
    format_token_count,
    get_context_window,
)


class TestCountTokens:
    def test_empty_string_returns_zero(self):
        assert count_tokens("") == 0

    def test_short_text_returns_positive(self):
        assert count_tokens("hi") >= 1

    def test_model_arg_accepted_gracefully(self):
        r1 = count_tokens("hello world", model="claude-opus-4-6")
        r2 = count_tokens("hello world", model="gpt-4o")
        assert r1 == r2

    def test_tiktoken_gives_real_count(self):
        try:
            import tiktoken  # noqa: F401
        except ImportError:
            return
        result = count_tokens("Hello, world!")
        assert isinstance(result, int)
        assert result > 0

    def test_fallback_when_tiktoken_unavailable(self):
        with patch("sideclaw.utils.tokens._get_encoding", return_value=None):
            text = "a" * 100
            assert count_tokens(text) == 100 // CHARS_PER_TOKEN_FALLBACK

    def test_consistent_results(self):
        r1 = count_tokens("consistent test string")
        r2 = count_tokens("consistent test string")
        assert r1 == r2


class TestCountMessageTokens:
    def test_simple_messages(self):
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = count_message_tokens(msgs)
        assert result > 0

    def test_tool_call_messages(self):
        msgs = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path": "/tmp"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "tc_1", "name": "read_file", "content": "file data"},
        ]
        result = count_message_tokens(msgs)
        assert result > 0

    def test_empty_messages(self):
        assert count_message_tokens([]) == 0


class TestGetContextWindow:
    def test_known_model(self):
        assert get_context_window("claude-opus-4-6") == 1_000_000

    def test_known_openai_model(self):
        assert get_context_window("gpt-4o") == 128_000

    def test_unknown_model_returns_none(self):
        assert get_context_window("totally-fake-model") is None


class TestFormatTokenCount:
    def test_small_number(self):
        assert format_token_count(42) == "42"

    def test_thousands(self):
        assert format_token_count(1_500) == "1.5K"

    def test_millions(self):
        assert format_token_count(2_500_000) == "2.5M"

    def test_zero(self):
        assert format_token_count(0) == "0"

    def test_exact_thousand(self):
        assert format_token_count(1_000) == "1K"

    def test_large_thousands(self):
        assert format_token_count(128_000) == "128K"


class TestFormatDuration:
    def test_seconds(self):
        assert format_duration(45) == "45s"

    def test_minutes(self):
        assert format_duration(125) == "2m"

    def test_hours(self):
        assert format_duration(3700) == "1h 1m"

    def test_days(self):
        assert format_duration(90_000) == "1.0d"
