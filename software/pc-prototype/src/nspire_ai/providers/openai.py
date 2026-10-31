"""OpenAI Responses API adapter; provider-specific HTTP stays behind AIProvider."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Sequence
from typing import Any

import httpx

from nspire_ai.errors import ProviderError
from nspire_ai.messages import Message, validate_provider_messages
from nspire_ai.providers.base import ProviderResponse


class OpenAIProvider:
    """Synchronous OpenAI adapter using the official Responses API endpoint."""

    def __init__(
        self,
        model: str = "gpt-4.1-mini",
        timeout: float = 30.0,
        *,
        api_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self._timeout = timeout
        self._api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY")
        self._client = client

    @property
    def name(self) -> str:
        return "openai"

    def generate(self, prompt: str) -> ProviderResponse:
        if not prompt.strip():
            raise ProviderError("Prompt cannot be empty.")
        if not self._api_key or not self._api_key.strip():
            raise ProviderError("OpenAI API key is not configured.")

        return self._send_input(prompt)

    def generate_messages(self, messages: Sequence[Message]) -> ProviderResponse:
        """Send role-tagged conversation context using Responses API input messages."""
        try:
            validated = validate_provider_messages(messages)
        except ValueError as exc:
            raise ProviderError("Conversation context is invalid.") from exc
        if not self._api_key or not self._api_key.strip():
            raise ProviderError("OpenAI API key is not configured.")
        payload = [{"role": message.role, "content": message.content} for message in validated]
        return self._send_input(payload)

    def stream(self, prompt: str) -> Iterator[str]:
        if not prompt.strip():
            raise ProviderError("Prompt cannot be empty.")
        if not self._api_key or not self._api_key.strip():
            raise ProviderError("OpenAI API key is not configured.")
        yield from self._stream_input(prompt)

    def stream_messages(self, messages: Sequence[Message]) -> Iterator[str]:
        try:
            validated = validate_provider_messages(messages)
        except ValueError as exc:
            raise ProviderError("Conversation context is invalid.") from exc
        if not self._api_key or not self._api_key.strip():
            raise ProviderError("OpenAI API key is not configured.")
        payload = [{"role": message.role, "content": message.content} for message in validated]
        yield from self._stream_input(payload)

    def _stream_input(self, input_value: str | list[dict[str, str]]) -> Iterator[str]:
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        body = {"model": self._model, "input": input_value, "stream": True}
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=self._timeout)
        completed = False
        try:
            request = client.build_request("POST", "https://api.openai.com/v1/responses", headers=headers, json=body)
            result = client.send(request, stream=True)
            try:
                result.raise_for_status()
                event_type: str | None = None
                data_lines: list[str] = []
                for line in result.iter_lines():
                    if not line:
                        if data_lines:
                            data = "\n".join(data_lines)
                            try:
                                payload = json.loads(data)
                            except ValueError:
                                raise ProviderError("OpenAI returned an invalid streaming response.") from None
                            if not isinstance(payload, dict):
                                raise ProviderError("OpenAI returned an invalid streaming response.")
                            kind = event_type or payload.get("type")
                            if completed:
                                raise ProviderError("OpenAI returned an invalid streaming response.")
                            if kind == "response.output_text.delta":
                                delta = payload.get("delta")
                                if not isinstance(delta, str) or not delta:
                                    raise ProviderError("OpenAI returned an invalid streaming response.")
                                yield delta
                            elif kind == "response.completed":
                                response_data = payload.get("response")
                                if not isinstance(response_data, dict) or response_data.get("status") != "completed":
                                    raise ProviderError("OpenAI returned an invalid streaming response.")
                                completed = True
                            elif kind in {"response.failed", "response.incomplete", "error"}:
                                raise ProviderError("OpenAI streaming request failed.")
                            elif kind not in {"response.created", "response.in_progress", "response.output_item.added", "response.content_part.added", "response.content_part.done", "response.output_item.done", "response.output_text.done", "response.completed"}:
                                raise ProviderError("OpenAI returned an unsupported streaming event.")
                            event_type, data_lines = None, []
                        continue
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                if data_lines:
                    raise ProviderError("OpenAI returned an incomplete streaming response.")
                if not completed:
                    raise ProviderError("OpenAI streaming response did not complete.")
            finally:
                result.close()
        except httpx.TimeoutException:
            raise ProviderError("OpenAI request timed out.", code="timeout") from None
        except httpx.HTTPStatusError:
            raise ProviderError("OpenAI request failed.", code="http_error") from None
        except httpx.RequestError:
            raise ProviderError("OpenAI service is unavailable.", code="unavailable") from None
        finally:
            if owns_client:
                client.close()

    def _send_input(self, input_value: str | list[dict[str, str]]) -> ProviderResponse:
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        body = {"model": self._model, "input": input_value}
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=self._timeout)
        try:
            response = client.post("https://api.openai.com/v1/responses", headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderError("OpenAI request timed out.", code="timeout") from None
        except httpx.HTTPStatusError as exc:
            # Do not expose response bodies, which may contain user or account details.
            raise ProviderError("OpenAI request failed.", code="http_error") from None
        except httpx.RequestError as exc:
            raise ProviderError("OpenAI service is unavailable.", code="unavailable") from None
        except ValueError as exc:
            raise ProviderError("OpenAI returned an invalid response.") from exc
        finally:
            if owns_client:
                client.close()

        text = _extract_output_text(payload)
        if not text.strip():
            raise ProviderError("OpenAI returned an empty response.")
        return ProviderResponse(text=text, provider=self.name)


def _extract_output_text(payload: Any) -> str:
    if (
        not isinstance(payload, dict)
        or payload.get("status") != "completed"
        or not isinstance(payload.get("output"), list)
    ):
        raise ProviderError("OpenAI returned an invalid response.")
    parts: list[str] = []
    for item in payload["output"]:
        if not isinstance(item, dict) or not isinstance(item.get("content", []), list):
            raise ProviderError("OpenAI returned an invalid response.")
        for content in item.get("content", []):
            if not isinstance(content, dict):
                raise ProviderError("OpenAI returned an invalid response.")
            if content.get("type") == "output_text":
                value = content.get("text")
                if not isinstance(value, str):
                    raise ProviderError("OpenAI returned an invalid response.")
                parts.append(value)
    if not parts:
        raise ProviderError("OpenAI returned an invalid response.")
    return "".join(parts)
