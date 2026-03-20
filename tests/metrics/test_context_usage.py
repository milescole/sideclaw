"""Tests for context usage breakdown."""

from sideclaw.metrics.context_usage import ContextUsageBreakdown, compute_context_usage


class TestContextUsageBreakdown:
    def test_total_and_free_space(self):
        b = ContextUsageBreakdown(
            model="claude-opus-4-6",
            context_window=1000,
            system_prompt_tokens=100,
            memory_files_tokens=50,
            skills_tokens=30,
            tools_tokens=20,
            messages_tokens=200,
            autocompact_buffer_tokens=100,
        )
        assert b.total_used_tokens == 500
        assert b.free_space_tokens == 500

    def test_render_compact(self):
        b = ContextUsageBreakdown(
            model="gpt-4o",
            context_window=128_000,
            system_prompt_tokens=1000,
            messages_tokens=2000,
        )
        text = b.render_compact()
        assert "gpt-4o" in text
        assert "tokens" in text

    def test_render_bar(self):
        b = ContextUsageBreakdown(
            model="test",
            context_window=100,
            system_prompt_tokens=25,
            messages_tokens=25,
        )
        bar = b.render_bar(width=20)
        assert len(bar) == 22  # 20 + brackets
        assert bar.startswith("[")
        assert bar.endswith("]")

    def test_render_detail(self):
        b = ContextUsageBreakdown(
            model="test",
            context_window=1000,
            system_prompt_tokens=100,
            memory_files_tokens=200,
        )
        detail = b.render_detail()
        assert "System prompt" in detail
        assert "Memory files" in detail
        assert "10.0%" in detail  # 100/1000


class TestComputeContextUsage:
    def test_basic_computation(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello there!"},
            {"role": "assistant", "content": "Hi!"},
        ]
        result = compute_context_usage(
            messages=messages,
            system_prompt="You are helpful.",
            model="gpt-4o",
        )
        assert result.context_window == 128_000
        assert result.system_prompt_tokens > 0
        assert result.messages_tokens > 0
        assert result.free_space_tokens > 0

    def test_with_tools(self):
        messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "hi"},
        ]
        tools = [{"type": "function", "function": {"name": "test", "parameters": {}}}]
        result = compute_context_usage(
            messages=messages,
            system_prompt="test",
            model="gpt-4o",
            tools=tools,
        )
        assert result.tools_tokens > 0

    def test_with_bundle_sections(self):
        messages = [{"role": "user", "content": "hi"}]
        result = compute_context_usage(
            messages=messages,
            system_prompt="identity text plus memory content",
            model="gpt-4o",
            bundle_sections={"docs/user.md": 50, "docs/profile.md": 30},
        )
        assert result.memory_files_tokens == 80

    def test_unknown_model_uses_fallback_window(self):
        result = compute_context_usage(
            messages=[],
            system_prompt="test",
            model="unknown-model",
        )
        assert result.context_window == 200_000
