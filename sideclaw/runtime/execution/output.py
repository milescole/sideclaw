"""Output translation helpers for runtime execution."""

from sideclaw.bus.messages import OutboundMessage
from sideclaw.runtime.models.outputs import RuntimeOutput


def build_outbound_message(
    *,
    output_text: str,
    surface: str | None,
    conversation_id: str | None,
    fallback_channel: str,
    fallback_chat_id: str,
) -> OutboundMessage:
    """Build the transport-shaped outbound message for a completed run."""
    return OutboundMessage(
        channel=surface or fallback_channel,
        chat_id=conversation_id or fallback_chat_id,
        text=output_text,
    )


def build_text_output(output_text: str) -> RuntimeOutput:
    """Build the runtime output for plain text responses."""
    return RuntimeOutput.text(output_text)
