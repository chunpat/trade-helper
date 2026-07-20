from app.services.llm_compat import parse_json_content, prepare_chat_payload


def test_prepare_chat_payload_uses_minimax_compatibility_fields():
    payload = {
        "model": "MiniMax-M3",
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": "return json"}],
    }

    prepared = prepare_chat_payload(payload, "https://api.minimaxi.com/v1", "MiniMax-M3")

    assert "response_format" not in prepared
    assert prepared["reasoning_split"] is True
    assert prepared["thinking"] == {"type": "disabled"}


def test_prepare_chat_payload_keeps_generic_openai_compatible_fields():
    payload = {
        "model": "example-model",
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": "return json"}],
    }

    prepared = prepare_chat_payload(payload, "https://example.com/v1", "example-model")

    assert prepared["response_format"] == {"type": "json_object"}
    assert "reasoning_split" not in prepared


def test_parse_json_content_handles_minimax_thinking_and_fence():
    content = '<think>reasoning here</think>\\n```json\\n{"trade_bias":"neutral"}\\n```'

    assert parse_json_content(content) == {"trade_bias": "neutral"}
