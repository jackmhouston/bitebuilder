import subprocess
import unittest
from unittest.mock import patch

from bitebuilder.claude_client import ClaudeCodeClient, ClaudeCodeError


class ClaudeClientTests(unittest.TestCase):
    def test_parses_headless_json_result(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout='{"result":"{\\"selected_segments\\": []}"}',
            stderr="",
        )
        with patch("bitebuilder.claude_client.subprocess.run", return_value=completed) as run_mock:
            payload = ClaudeCodeClient().generate_json(model="sonnet", prompt="hello", auth_token="token")

        self.assertEqual(payload, {"selected_segments": []})
        kwargs = run_mock.call_args.kwargs
        self.assertEqual(kwargs["env"]["ANTHROPIC_AUTH_TOKEN"], "token")

    def test_raises_on_invalid_result_json(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout='{"result":"not-json"}',
            stderr="",
        )
        with patch("bitebuilder.claude_client.subprocess.run", return_value=completed):
            with self.assertRaises(ClaudeCodeError):
                ClaudeCodeClient().generate_json(model="sonnet", prompt="hello")


if __name__ == "__main__":
    unittest.main()

