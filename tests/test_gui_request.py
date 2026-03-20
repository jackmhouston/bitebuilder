import shutil
import unittest
from pathlib import Path

from bitebuilder.gui import normalize_user_path, prepare_request_from_payload, request_from_payload


class GuiRequestTests(unittest.TestCase):
    def test_builds_generation_request_for_claude(self) -> None:
        request = request_from_payload(
            {
                "transcript_path": "~/transcript.txt",
                "premiere_xml_path": "~/source.xml",
                "output_path": '"C:\\Users\\jackm\\Downloads\\out.xml"',
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
        self.assertEqual(request.output_path, Path("/mnt/c/Users/jackm/Downloads/out.xml"))

    def test_prepares_request_from_uploaded_files(self) -> None:
        prepared = prepare_request_from_payload(
            {
                "transcript_name": "story.txt",
                "transcript_content": "[00:00:01-00:00:03] First beat",
                "premiere_xml_name": "stringout.xml",
                "premiere_xml_content": "<xmeml><sequence><name>Test</name></sequence><clipitem id='1'><name>A</name></clipitem></xmeml>",
                "brief": "Make a good story from this.",
                "provider": "ollama",
            }
        )

        try:
            self.assertIsNotNone(prepared.temporary_dir)
            self.assertTrue(prepared.request.transcript_path.exists())
            self.assertTrue(prepared.request.premiere_xml_path.exists())
            self.assertEqual(prepared.download_name, "story_bitebuilder.xml")
            self.assertIsNone(prepared.saved_output_path)
        finally:
            if prepared.temporary_dir is not None:
                shutil.rmtree(prepared.temporary_dir, ignore_errors=True)

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

    def test_normalizes_windows_path(self) -> None:
        path = normalize_user_path('"C:\\Users\\jackm\\Downloads\\Solar Project Cut Down 2.xml"')
        self.assertEqual(path, Path("/mnt/c/Users/jackm/Downloads/Solar Project Cut Down 2.xml"))


if __name__ == "__main__":
    unittest.main()
