from sideclaw.runtime.execution.output import build_outbound_message, build_text_output


def test_output_builder_returns_outbound_message_for_surface_and_conversation():
    outbound = build_outbound_message(
        output_text="Hello!",
        surface="telegram",
        conversation_id="chat-1",
        fallback_channel="cli",
        fallback_chat_id="fallback",
    )

    assert outbound.channel == "telegram"
    assert outbound.chat_id == "chat-1"
    assert outbound.text == "Hello!"


def test_output_builder_falls_back_to_transport_ids_when_runtime_context_missing():
    outbound = build_outbound_message(
        output_text="Hello!",
        surface=None,
        conversation_id=None,
        fallback_channel="cli",
        fallback_chat_id="chat-9",
    )

    assert outbound.channel == "cli"
    assert outbound.chat_id == "chat-9"
    assert outbound.text == "Hello!"


def test_build_text_output_wraps_plain_text():
    output = build_text_output("Done")
    assert output.kind == "text"
    assert output.text == "Done"
