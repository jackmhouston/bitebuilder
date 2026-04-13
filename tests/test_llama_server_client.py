import importlib
import os
import unittest
from unittest.mock import Mock, patch

import requests

from llm import ollama_client


class LlamaServerClientTests(unittest.TestCase):
    def test_default_config_targets_local_gemma4_llama_server(self):
        try:
            with patch.dict(os.environ, {}, clear=True):
                reloaded = importlib.reload(ollama_client)

                self.assertEqual(reloaded.DEFAULT_MODEL, "gemma-4-E2B-it-Q8_0.gguf")
                self.assertEqual(reloaded.DEFAULT_HOST, "http://127.0.0.1:18084")
                self.assertEqual(reloaded.DEFAULT_CONTEXT_TOKENS, 8192)
                self.assertEqual(
                    reloaded.normalize_thinking_mode(reloaded.DEFAULT_THINKING_MODE),
                    "off",
                )
                self.assertIn("http://127.0.0.1:18084", reloaded.host_candidates())
        finally:
            importlib.reload(ollama_client)

    def test_ollama_host_does_not_displace_bitebuilder_gemma4_default(self):
        try:
            with patch.dict(os.environ, {"OLLAMA_HOST": "http://127.0.0.1:11434"}, clear=True):
                reloaded = importlib.reload(ollama_client)

                self.assertEqual(reloaded.DEFAULT_HOST, "http://127.0.0.1:18084")
                self.assertEqual(
                    reloaded.host_candidates()[:2],
                    ["http://127.0.0.1:18084", "http://127.0.0.1:11434"],
                )
        finally:
            importlib.reload(ollama_client)

    def test_extract_response_text_reads_openai_chat_shape(self):
        result = {
            "choices": [
                {"message": {"role": "assistant", "content": "{\"ok\": true}"}}
            ]
        }

        self.assertEqual(ollama_client._extract_response_text(result), "{\"ok\": true}")

    def test_generate_falls_back_to_openai_chat_when_ollama_endpoint_404s(self):
        def fake_get(url, timeout):
            response = Mock()
            response.status_code = 200 if url.endswith("/v1/models") else 404
            response.json.return_value = {"data": [{"id": "gemma-4-E2B-it-Q8_0.gguf"}]}
            return response

        def fake_post(url, json, timeout):
            response = Mock()
            if url.endswith("/api/generate"):
                response.status_code = 404
                response.raise_for_status.side_effect = requests.HTTPError("404 not found")
                return response
            self.assertTrue(url.endswith("/v1/chat/completions"))
            self.assertEqual(json["model"], "gemma-4-E2B-it-Q8_0.gguf")
            self.assertEqual(json["response_format"], {"type": "json_object"})
            response.status_code = 200
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "choices": [
                    {"message": {"role": "assistant", "content": "{\"ok\": true}"}}
                ]
            }
            return response

        with patch.object(ollama_client.requests, "get", side_effect=fake_get):
            with patch.object(ollama_client.requests, "post", side_effect=fake_post):
                result = ollama_client.generate(
                    "Return JSON.",
                    "Return {\"ok\": true}.",
                    model="gemma-4-E2B-it-Q8_0.gguf",
                    host="http://127.0.0.1:18084",
                )

        self.assertEqual(result, {"ok": True})

    def test_list_models_reads_openai_models_endpoint(self):
        def fake_get(url, timeout):
            response = Mock()
            if url.endswith("/api/tags"):
                response.status_code = 404
                return response
            response.status_code = 200
            response.raise_for_status.return_value = None
            response.json.return_value = {"data": [{"id": "gemma-4-E2B-it-Q8_0.gguf"}]}
            return response

        with patch.object(ollama_client.requests, "get", side_effect=fake_get):
            self.assertEqual(
                ollama_client.list_models("http://127.0.0.1:18084"),
                ["gemma-4-E2B-it-Q8_0.gguf"],
            )


if __name__ == "__main__":
    unittest.main()
