from sideclaw.tools.base import truncate_tool_output


def test_short_output_passes_through():
    text = "hello world"
    assert truncate_tool_output(text) == text


def test_exact_limit_passes_through():
    text = "x" * 10_000
    assert truncate_tool_output(text) == text


def test_long_output_preserves_head_and_tail():
    head = "HEAD" * 1000
    tail = "TAIL" * 1000
    middle = "M" * 5000
    text = head + middle + tail
    result = truncate_tool_output(text, max_chars=10_000)

    assert result.startswith(text[:5000])
    assert result.endswith(text[-5000:])
    assert "chars omitted" in result


def test_marker_contains_correct_omitted_count():
    text = "x" * 15_000
    result = truncate_tool_output(text, max_chars=10_000)
    assert "5,000 chars omitted" in result


def test_custom_max_chars():
    text = "x" * 200
    result = truncate_tool_output(text, max_chars=100)
    assert result.startswith("x" * 50)
    assert result.endswith("x" * 50)
    assert "100 chars omitted" in result
