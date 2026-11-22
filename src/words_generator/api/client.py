from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from words_generator.models.sampling import SamplingSettings


class APIError(RuntimeError):
    """A safe, user-facing API error without credentials."""


@dataclass(slots=True)
class APIConfig:
    base_url: str
    model: str
    api_key: str = ""
    timeout_seconds: float = 60.0

    def validate(self, *, require_model: bool = False) -> None:
        if not self.base_url.strip():
            raise ValueError("API Base URL is required.")
        if require_model and not self.model.strip():
            raise ValueError("Select or enter a model identifier before generating words.")
        if not 1.0 <= self.timeout_seconds <= 600.0:
            raise ValueError("Timeout must be between 1 and 600 seconds.")


class OpenAICompatibleClient:
    """Minimal client for the OpenAI Chat Completions-compatible API."""

    def __init__(
        self,
        config: APIConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self._client = httpx.Client(
            timeout=httpx.Timeout(config.timeout_seconds),
            transport=transport,
            headers={"User-Agent": "Words-Generator/0.1.0"},
        )

    def _url(self, endpoint: str) -> str:
        base = self.config.base_url.strip().rstrip("/")
        endpoint = endpoint.lstrip("/")
        if base.endswith(f"/{endpoint}"):
            return base
        if base.endswith("/v1"):
            return f"{base}/{endpoint}"
        return f"{base}/v1/{endpoint}"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key.strip():
            headers["Authorization"] = f"Bearer {self.config.api_key.strip()}"
        return headers

    def list_models(self) -> list[str]:
        try:
            response = self._client.get(self._url("models"), headers=self._headers())
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise APIError("Timed out while requesting the model list.") from exc
        except httpx.HTTPStatusError as exc:
            raise APIError(f"Model list request failed (HTTP {exc.response.status_code}).") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise APIError(f"Could not read the model list: {exc}") from exc

        items = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise APIError("The /models response has an unexpected format.")
        model_ids = [item.get("id") for item in items if isinstance(item, dict)]
        return [model_id for model_id in model_ids if isinstance(model_id, str)]

    def generate_word(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        sampling: SamplingSettings,
    ) -> str:
        self.config.validate(require_model=True)
        sampling.validate()
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **sampling.to_dict(),
            "stream": False,
        }
        try:
            response = self._client.post(
                self._url("chat/completions"),
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise APIError("The model request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise APIError(f"Model request failed (HTTP {exc.response.status_code}).") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise APIError(f"Could not complete the model request: {exc}") from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise APIError("The Chat Completions response has an unexpected format.") from exc
        if not isinstance(content, str):
            raise APIError("The model returned a non-text response.")
        return content

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OpenAICompatibleClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
