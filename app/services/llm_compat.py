import json
import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse


def is_minimax_endpoint(base_url: str) -> bool:
    hostname = (urlparse(base_url).hostname or "").lower()
    return hostname == "api.minimax.io" or hostname == "api.minimaxi.com"


def prepare_chat_payload(payload: Dict[str, Any], base_url: str, model: str) -> Dict[str, Any]:
    prepared = dict(payload)
    if not is_minimax_endpoint(base_url):
        return prepared

    # MiniMax's OpenAI-compatible API does not document response_format.
    # Separate reasoning so JSON remains in message.content without <think> tags.
    prepared.pop("response_format", None)
    prepared["reasoning_split"] = True
    if model == "MiniMax-M3":
        prepared["thinking"] = {"type": "disabled"}
    return prepared


def parse_json_content(content: str) -> Optional[Dict[str, Any]]:
    normalized = re.sub(r"<think>.*?</think>", "", str(content or ""), flags=re.DOTALL).strip()
    if normalized.startswith("```"):
        normalized = normalized.strip("`")
        if normalized.startswith("json"):
            normalized = normalized[4:]
        normalized = normalized.strip()

    try:
        parsed = json.loads(normalized)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        start = normalized.find("{")
        end = normalized.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(normalized[start:end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
