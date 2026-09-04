"""Common types for the AI backends."""

from __future__ import annotations

import base64
import json
import mimetypes
import re
from dataclasses import dataclass
from typing import Optional, Protocol


class AIError(Exception):
    """Any failure talking to the model."""


class NotConfiguredError(AIError):
    """No usable backend is configured."""


class RefusalError(AIError):
    """The model declined to answer."""


@dataclass
class ChatMessage:
    role: str  # "user" or "assistant"
    text: str
    image_path: Optional[str] = None


class Backend(Protocol):
    name: str

    def complete(self, system: str, messages: list[ChatMessage], *, max_tokens: int = 4096) -> str:
        ...


def encode_image(path: str) -> tuple[str, str]:
    """Return (media_type, base64 data) for an image file."""
    media_type = mimetypes.guess_type(path)[0] or "image/png"
    if media_type not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
        media_type = "image/png"
    with open(path, "rb") as fh:
        data = base64.standard_b64encode(fh.read()).decode("ascii")
    return media_type, data


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str):
    """Pull the first JSON object/array out of a model reply, tolerating chatter and code fences."""
    if not text:
        raise ValueError("empty reply")
    candidates = [m.strip() for m in _FENCE.findall(text)]
    candidates.append(text.strip())
    for start, end in (("{", "}"), ("[", "]")):
        i = text.find(start)
        j = text.rfind(end)
        if i != -1 and j > i:
            candidates.append(text[i:j + 1])
    last_error: Exception | None = None
    for cand in candidates:
        try:
            return json.loads(cand)
        except ValueError as exc:
            last_error = exc
    raise ValueError(f"no JSON found in reply: {last_error}")


def make_backend(settings) -> Backend:
    """Build the backend selected in settings, raising NotConfiguredError if it can't work."""
    kind = settings.get("backend")
    if kind == "anthropic":
        key = settings.anthropic_key()
        if not key:
            raise NotConfiguredError("Add your Anthropic API key in Preferences to bring the AI users to life.")
        from ubsr.ai.anthropic_backend import AnthropicBackend

        return AnthropicBackend(
            api_key=key,
            model=settings.get("anthropic_model") or "claude-opus-5",
            effort=settings.get("anthropic_effort") or "low",
        )
    if kind == "openai_compat":
        base_url = (settings.get("openai_base_url") or "").strip()
        model = (settings.get("openai_model") or "").strip()
        if not base_url or not model:
            raise NotConfiguredError("Set the server URL and model name for the local/OpenAI-compatible backend.")
        from ubsr.ai.openai_compat import OpenAICompatBackend

        return OpenAICompatBackend(base_url=base_url, api_key=settings.get("openai_api_key") or "", model=model)
    raise NotConfiguredError(f"Unknown backend '{kind}'.")
