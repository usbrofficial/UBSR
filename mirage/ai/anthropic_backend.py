"""Claude backend using the official Anthropic SDK."""

from __future__ import annotations

from mirage.ai.base import AIError, ChatMessage, NotConfiguredError, RefusalError, encode_image

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicBackend:
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-opus-5", effort: str = "low", timeout: float = 240.0):
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on the install
            raise NotConfiguredError(
                "The 'anthropic' Python package is missing. Run install.sh again or 'pip install anthropic'."
            ) from exc
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)
        self.model = model
        self.effort = effort

    def _content(self, msg: ChatMessage) -> str | list:
        if not msg.image_path:
            return msg.text
        try:
            media_type, data = encode_image(msg.image_path)
        except OSError:
            return msg.text
        return [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
            {"type": "text", "text": msg.text or "(photo)"},
        ]

    def _params(self, system: str, messages: list[ChatMessage], max_tokens: int) -> dict:
        api_messages = []
        for msg in messages:
            role = "assistant" if msg.role == "assistant" else "user"
            content = self._content(msg)
            # The API requires alternating roles; merge consecutive same-role turns.
            if api_messages and api_messages[-1]["role"] == role:
                prev = api_messages[-1]["content"]
                if isinstance(prev, str) and isinstance(content, str):
                    api_messages[-1]["content"] = prev + "\n\n" + content
                else:
                    prev_list = prev if isinstance(prev, list) else [{"type": "text", "text": prev}]
                    cur_list = content if isinstance(content, list) else [{"type": "text", "text": content}]
                    api_messages[-1]["content"] = prev_list + cur_list
            else:
                api_messages.append({"role": role, "content": content})
        if not api_messages or api_messages[0]["role"] != "user":
            api_messages.insert(0, {"role": "user", "content": "(conversation starts)"})
        params: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": api_messages,
        }
        # `effort` is supported on Opus 4.5+ / Sonnet 5 / Fable; Haiku 4.5 rejects it.
        if self.effort and "haiku" not in self.model:
            params["output_config"] = {"effort": self.effort}
        return params

    def complete(self, system: str, messages: list[ChatMessage], *, max_tokens: int = 4096) -> str:
        anthropic = self._anthropic
        params = self._params(system, messages, max_tokens)
        try:
            try:
                response = self.client.beta.messages.create(
                    **params, betas=[FALLBACK_BETA], fallbacks="default"
                )
            except TypeError:
                # Older SDK without the `fallbacks` argument: send it in the raw body instead.
                response = self.client.beta.messages.create(
                    **params, betas=[FALLBACK_BETA], extra_body={"fallbacks": "default"}
                )
        except anthropic.AuthenticationError as exc:
            raise AIError("Anthropic rejected the API key. Check it in Preferences.") from exc
        except anthropic.NotFoundError as exc:
            raise AIError(f"Model '{self.model}' was not found. Check the model name in Preferences.") from exc
        except anthropic.RateLimitError as exc:
            raise AIError("Anthropic rate limit hit. The AI users will try again shortly.") from exc
        except anthropic.BadRequestError as exc:
            raise AIError(f"Anthropic rejected the request: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise AIError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise AIError("Could not reach the Anthropic API. Check your connection.") from exc

        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            explanation = getattr(details, "explanation", None) if details else None
            raise RefusalError(explanation or "The model declined to write this.")
        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        return text.strip()
