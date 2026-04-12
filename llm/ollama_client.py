"""
Ollama local LLM client.

Communicates with Ollama's HTTP API at localhost:11434.
Supports JSON mode for structured output.
"""

import json
import os
import re
import requests
import sys
from json import JSONDecoder

DEFAULT_MODEL = "gemma3:4b"
DEFAULT_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_TIMEOUT = 180  # seconds — local models can be slow on first inference
DEFAULT_CONTEXT_TOKENS = int(os.getenv("BITEBUILDER_NUM_CTX", "12288"))
DEFAULT_THINKING_MODE = os.getenv("BITEBUILDER_THINKING_MODE", "auto")
DEFAULT_SELECTION_TEMPERATURE = float(os.getenv("BITEBUILDER_SELECTION_TEMPERATURE", "0.0"))
DEFAULT_SELECTION_SEED = int(os.getenv("BITEBUILDER_SELECTION_SEED", "0"))
DEFAULT_TEXT_TEMPERATURE = float(os.getenv("BITEBUILDER_TEXT_TEMPERATURE", "0.3"))
DEFAULT_TEXT_SEED = int(os.getenv("BITEBUILDER_TEXT_SEED", "0"))
DEFAULT_JSON_PREDICT_TOKENS = 2048
DEFAULT_TEXT_PREDICT_TOKENS = 768
FALLBACK_HOSTS = ("http://127.0.0.1:11434", "http://127.0.0.1:11435")
VALID_THINKING_MODES = {"auto", "on", "off"}
JSON_REPAIR_SYSTEM_PROMPT = """You repair malformed JSON.

Return only valid JSON.
Do not add commentary.
Do not change the intended meaning or invent new content beyond what is needed to make the JSON valid."""


def normalize_host(host: str | None) -> str:
    """Normalize Ollama host strings to a full http URL."""
    host = (host or DEFAULT_HOST).strip()
    if not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    return host.rstrip("/")


def host_candidates(preferred_host: str | None = None) -> list[str]:
    """Return ordered unique Ollama hosts to probe."""
    candidates = []
    for host in [preferred_host, os.getenv("OLLAMA_HOST"), DEFAULT_HOST, *FALLBACK_HOSTS]:
        if not host:
            continue
        normalized = normalize_host(host)
        if normalized not in candidates:
            candidates.append(normalized)
    return candidates


def normalize_thinking_mode(thinking_mode: str | None) -> str:
    """Normalize thinking-mode aliases into auto/on/off."""
    mode = (thinking_mode or DEFAULT_THINKING_MODE).strip().lower().replace("-", "_")
    aliases = {
        "thinking": "on",
        "think": "on",
        "true": "on",
        "yes": "on",
        "1": "on",
        "disabled": "off",
        "disable": "off",
        "no_think": "off",
        "false": "off",
        "no": "off",
        "0": "off",
        "default": "auto",
    }
    mode = aliases.get(mode, mode)
    if mode not in VALID_THINKING_MODES:
        return "auto"
    return mode


def _request_generate_result(payload: dict, host: str, timeout: int) -> dict:
    """Send a generate request to Ollama and return the parsed JSON body."""
    host = normalize_host(host)
    url = f"{host}/api/generate"

    response = None
    try:
        print(f"  Sending to Ollama ({payload['model']})...", file=sys.stderr)
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
    except requests.ConnectionError:
        raise ConnectionError(
            f"Cannot connect to Ollama at {host}. "
            f"Is Ollama running? Start it with: ollama serve"
        )
    except requests.Timeout:
        raise TimeoutError(
            f"Ollama request timed out after {timeout}s. "
            f"Try a smaller model or increase --timeout."
        )
    except requests.HTTPError as e:
        if response is not None and ("model" in str(e).lower() or response.status_code == 404):
            raise ValueError(
                f"Model '{payload['model']}' not found. Pull it with: ollama pull {payload['model']}"
            )
        raise

    return response.json()


def _extract_response_text(result: dict | None) -> str:
    """Extract the final answer text from an Ollama generate response."""
    if not isinstance(result, dict):
        return ""

    response_text = result.get("response")
    if isinstance(response_text, str) and response_text:
        return response_text

    message = result.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content:
            return content

    return ""


def _request_generate(payload: dict, host: str, timeout: int) -> str:
    """Backward-compatible helper that returns only the final response text."""
    return _extract_response_text(_request_generate_result(payload, host, timeout))


def _prepare_prompt_for_model(
    prompt: str,
    model: str,
    thinking_mode: str = DEFAULT_THINKING_MODE,
) -> str:
    """
    Apply model-specific prompt controls.
    """
    normalized = (model or "").lower()
    mode = normalize_thinking_mode(thinking_mode)

    if normalized.startswith("qwen3"):
        stripped_prompt = prompt.lstrip()
        if stripped_prompt.startswith("/think\n"):
            stripped_prompt = stripped_prompt.split("\n", 1)[1]
        elif stripped_prompt.startswith("/no_think\n"):
            stripped_prompt = stripped_prompt.split("\n", 1)[1]

        if mode == "on":
            return f"/think\n{stripped_prompt}"
        if mode == "off":
            return f"/no_think\n{stripped_prompt}"

    return prompt


def generate(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
    host: str = DEFAULT_HOST,
    timeout: int = DEFAULT_TIMEOUT,
    thinking_mode: str = DEFAULT_THINKING_MODE,
    debug: dict | None = None,
) -> dict:
    """
    Send a prompt to Ollama and get a parsed JSON response.
    """
    payload = {
        "model": model,
        "prompt": _prepare_prompt_for_model(user_prompt, model, thinking_mode),
        "system": system_prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": DEFAULT_SELECTION_TEMPERATURE,
            "seed": DEFAULT_SELECTION_SEED,
            "num_ctx": DEFAULT_CONTEXT_TOKENS,
            "num_predict": DEFAULT_JSON_PREDICT_TOKENS,
        }
    }

    result = _request_generate_result(payload, host, timeout)
    raw_text = _extract_response_text(result).strip()
    if not raw_text and result.get("thinking") and normalize_thinking_mode(thinking_mode) == "on":
        retry_payload = {
            **payload,
            "prompt": _prepare_prompt_for_model(user_prompt, model, "off"),
        }
        result = _request_generate_result(retry_payload, host, timeout)
        raw_text = _extract_response_text(result).strip()

    if debug is not None:
        debug["raw_text"] = raw_text
        debug["response_json"] = result

    try:
        return _parse_json_text(raw_text)
    except ValueError:
        repaired_text = _repair_json_text(raw_text, model=model, host=host, timeout=timeout)
        if debug is not None:
            debug["repaired_text"] = repaired_text
        try:
            return _parse_json_text(repaired_text)
        except ValueError as repair_error:
            raise ValueError(
                "Could not parse JSON from Ollama response after repair attempt. "
                f"Raw response:\n{raw_text[:500]}\n\n"
                f"Repair response:\n{repaired_text[:500]}"
            ) from repair_error


def generate_text(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
    host: str = DEFAULT_HOST,
    timeout: int = DEFAULT_TIMEOUT,
    max_tokens: int = DEFAULT_TEXT_PREDICT_TOKENS,
    thinking_mode: str = DEFAULT_THINKING_MODE,
    debug: dict | None = None,
) -> str:
    """
    Send a prompt to Ollama and return plain text.
    """
    payload = {
        "model": model,
        "prompt": _prepare_prompt_for_model(user_prompt, model, thinking_mode),
        "system": system_prompt,
        "stream": False,
        "options": {
            "temperature": DEFAULT_TEXT_TEMPERATURE,
            "seed": DEFAULT_TEXT_SEED,
            "num_ctx": DEFAULT_CONTEXT_TOKENS,
            "num_predict": max(max_tokens, 1536) if normalize_thinking_mode(thinking_mode) == "on" else max_tokens,
        }
    }
    result = _request_generate_result(payload, host, timeout)
    raw_text = _extract_response_text(result).strip()
    if not raw_text and result.get("thinking") and normalize_thinking_mode(thinking_mode) == "on":
        retry_payload = {
            **payload,
            "prompt": _prepare_prompt_for_model(user_prompt, model, "off"),
            "options": {
                **payload["options"],
                "num_predict": max(max_tokens, DEFAULT_TEXT_PREDICT_TOKENS),
            },
        }
        retry_result = _request_generate_result(retry_payload, host, timeout)
        retry_text = _extract_response_text(retry_result).strip()
        if retry_text:
            result = retry_result
            raw_text = retry_text

    if debug is not None:
        debug["raw_text"] = raw_text
        debug["response_json"] = result
        debug["thinking_text"] = result.get("thinking", "")

    if raw_text:
        return raw_text

    raise ValueError(
        "Model returned no final response text. "
        "Try turning thinking mode off or increasing the output budget."
    )


def _parse_json_text(raw_text: str) -> dict:
    """Parse JSON from a raw Ollama response string."""
    cleaned = (raw_text or "").strip()
    decoder = JSONDecoder()

    candidates = [cleaned]
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if fence_match:
        candidates.append(fence_match.group(1).strip())

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        for start_char in ("{", "["):
            start = candidate.find(start_char)
            while start != -1:
                try:
                    parsed, _ = decoder.raw_decode(candidate[start:])
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass
                start = candidate.find(start_char, start + 1)

    raise ValueError(
        f"Could not parse JSON from Ollama response. "
        f"Raw response:\n{cleaned[:500]}"
    )


def _repair_json_text(raw_text: str, model: str, host: str, timeout: int) -> str:
    """Ask the model to repair malformed JSON into valid JSON."""
    if not raw_text.strip():
        return raw_text

    repair_payload = {
        "model": model,
        "prompt": _prepare_prompt_for_model(
            "Repair the following malformed JSON and return only valid JSON:\n\n"
            f"{raw_text}",
            model,
            "off",
        ),
        "system": JSON_REPAIR_SYSTEM_PROMPT,
        "stream": False,
        "options": {
            "temperature": 0,
            "seed": DEFAULT_SELECTION_SEED,
            "num_ctx": DEFAULT_CONTEXT_TOKENS,
            "num_predict": DEFAULT_JSON_PREDICT_TOKENS,
        },
    }
    return _request_generate(repair_payload, host, timeout).strip()


def check_connection(host: str = DEFAULT_HOST) -> bool:
    """Check if Ollama is running and reachable."""
    try:
        host = normalize_host(host)
        r = requests.get(f"{host}/api/tags", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def list_models(host: str = DEFAULT_HOST) -> list[str]:
    """List available models on the local Ollama instance."""
    try:
        host = normalize_host(host)
        r = requests.get(f"{host}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def resolve_host(
    model: str | None = None,
    preferred_host: str | None = None,
) -> tuple[str, list[str]]:
    """
    Resolve the best reachable Ollama host, preferring one that has the requested model.
    """
    connected_hosts = []
    target_name = model.split(":")[0] if model else None

    for host in host_candidates(preferred_host):
        if not check_connection(host):
            continue

        models = list_models(host)
        connected_hosts.append((host, models))

        if model is None:
            return host, models

        model_names = [item.split(":")[0] for item in models]
        if model in models or target_name in model_names:
            return host, models

    if connected_hosts:
        return connected_hosts[0]

    raise ConnectionError("Cannot connect to any local Ollama host.")
