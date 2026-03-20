from __future__ import annotations

import json

import requests


class OllamaError(RuntimeError):
    """Raised when the local Ollama server fails or returns invalid data."""


class OllamaClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11434") -> None:
        self.base_url = base_url.rstrip("/")

    def list_models(self, timeout: float = 10.0) -> list[str]:
        response = requests.get(f"{self.base_url}/api/tags", timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return [model["name"] for model in data.get("models", []) if "name" in model]

    def generate_json(
        self,
        model: str,
        prompt: str,
        timeout: float = 180.0,
    ) -> dict:
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                },
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaError(f"Ollama request failed: {exc}") from exc

        payload = response.json()
        text = payload.get("response", "").strip()
        if not text:
            raise OllamaError("Ollama returned an empty response body.")

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise OllamaError(f"Ollama did not return valid JSON: {text[:200]}") from exc

