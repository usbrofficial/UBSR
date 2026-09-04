"""Backend for any OpenAI-compatible chat server: Ollama, LM Studio, llama.cpp, OpenRouter, vLLM..."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from ubsr.ai.base import AIError, ChatMessage, RefusalError, encode_image


class OpenAICompatBackend:
    name = "openai_compat"

    def __init__(self, base_url: str, api_key: str = "", model: str = "llama3.1", timeout: float = 600.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _content(self, msg: ChatMessage):
        if not msg.image_path:
            return msg.text
        try:
            media_type, data = encode_image(msg.image_path)
        except OSError:
            return msg.text
        return [
            {"type": "text", "text": msg.text or "(photo)"},
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{data}"}},
        ]

    def complete(self, system: str, messages: list[ChatMessage], *, max_tokens: int = 4096) -> str:
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}]
            + [{"role": m.role, "content": self._content(m)} for m in messages],
        }
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:300]
            except OSError:
                pass
            raise AIError(f"Server returned HTTP {exc.code}: {detail or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise AIError(f"Could not reach {self.base_url}: {exc.reason}") from exc
        except (OSError, ValueError) as exc:
            raise AIError(f"Bad response from {self.base_url}: {exc}") from exc

        try:
            choice = body["choices"][0]
            message = choice.get("message") or {}
            text = message.get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise AIError(f"Unexpected response shape from server: {str(body)[:200]}") from exc
        if isinstance(text, list):  # some servers return content parts
            text = "".join(part.get("text", "") for part in text if isinstance(part, dict))
        if choice.get("finish_reason") == "content_filter":
            raise RefusalError("The server's content filter blocked this reply.")
        return text.strip()
