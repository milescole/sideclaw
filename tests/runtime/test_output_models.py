from sideclaw.runtime.models.outputs import RuntimeOutput, RuntimeOutputKind


def test_text_output_factory():
    output = RuntimeOutput.text("hello")

    assert output.kind == RuntimeOutputKind.text
    assert output.text == "hello"
    assert output.path is None
