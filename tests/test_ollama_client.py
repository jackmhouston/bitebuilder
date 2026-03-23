import unittest
from unittest.mock import patch

from llm.ollama_client import generate, generate_text


class OllamaClientTests(unittest.TestCase):
    @patch("llm.ollama_client._request_generate", return_value='{"options":[{"name":"Test","cuts":[]}]}')
    @patch(
        "llm.ollama_client._request_generate_result",
        return_value={"response": '{"options":[{"name":"Test" "cuts":[]}]}'},
    )
    def test_generate_repairs_malformed_json(self, _request_generate_result, _request_generate):
        payload = generate(
            system_prompt="system",
            user_prompt="user",
            model="qwen3:8b",
            host="http://127.0.0.1:11435",
            timeout=30,
            thinking_mode="on",
        )

        self.assertIn("options", payload)
        self.assertEqual(payload["options"][0]["name"], "Test")

    @patch(
        "llm.ollama_client._request_generate_result",
        side_effect=[
            {
                "response": "",
                "thinking": "long reasoning",
                "done_reason": "length",
            },
            {
                "response": "Lead with the objection at 00:02:09:03, then pivot to the 40% proof.",
                "thinking": "short reasoning",
                "done_reason": "stop",
            },
        ],
    )
    def test_generate_text_retries_without_thinking_when_final_response_is_empty(self, request_generate_result):
        debug = {}
        reply = generate_text(
            system_prompt="system",
            user_prompt="What is the strongest hook?",
            model="qwen3:8b",
            host="http://127.0.0.1:11435",
            timeout=30,
            thinking_mode="on",
            debug=debug,
        )

        self.assertIn("Lead with the objection", reply)
        self.assertEqual(debug["raw_text"], reply)
        self.assertEqual(request_generate_result.call_count, 2)
        first_payload = request_generate_result.call_args_list[0].args[0]
        second_payload = request_generate_result.call_args_list[1].args[0]
        self.assertTrue(first_payload["prompt"].startswith("/think\n"))
        self.assertTrue(second_payload["prompt"].startswith("/no_think\n"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
