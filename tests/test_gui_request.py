import unittest

from bitebuilder.gui import request_from_payload


class GuiRequestTests(unittest.TestCase):
    def test_builds_generation_request_for_claude(self) -> None:
        request = request_from_payload(
            {
                "transcript_path": "~/transcript.txt",
                "premiere_xml_path": "~/source.xml",
                "output_path": "~/out.xml",
                "brief": "Find the cleanest arc.",
                "provider": "claude-code",
                "model": "sonnet",
                "claude_command": "claude",
                "claude_auth_token": "token",
                "dry_run": False,
            }
        )

        self.assertEqual(request.provider, "claude-code")
        self.assertEqual(request.model, "sonnet")
        self.assertEqual(request.claude_auth_token, "token")

    def test_rejects_unknown_provider(self) -> None:
        with self.assertRaises(ValueError):
            request_from_payload(
                {
                    "transcript_path": "~/transcript.txt",
                    "premiere_xml_path": "~/source.xml",
                    "output_path": "~/out.xml",
                    "brief": "Find the cleanest arc.",
                    "provider": "unsupported",
                }
            )


if __name__ == "__main__":
    unittest.main()
