import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bitebuilder
from tests.test_pipeline import TRANSCRIPT_TEXT, XML_TEXT
from tests.test_plan_to_xmeml import write_plan


def parse_args(*argv):
    with patch.object(sys, "argv", ["bitebuilder.py", *argv]):
        return bitebuilder.parse_args()


def run_bridge(args):
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        status = bitebuilder.run_go_tui_bridge(args)
    return status, stdout.getvalue()


class GoTuiBridgeTests(unittest.TestCase):
    def write_inputs(self, tmp: Path) -> tuple[Path, Path, Path]:
        transcript_path = tmp / "transcript.txt"
        xml_path = tmp / "source.xml"
        plan_path = tmp / "_sequence_plan.json"
        transcript_path.write_text(TRANSCRIPT_TEXT, encoding="utf-8")
        xml_path.write_text(XML_TEXT, encoding="utf-8")
        write_plan(plan_path)
        return transcript_path, xml_path, plan_path

    def test_setup_operation_outputs_json_only_success_envelope(self):
        args = parse_args("--go-tui-bridge", "setup")

        status, stdout = run_bridge(args)

        self.assertEqual(status, 0)
        self.assertTrue(stdout.startswith("{"), stdout)
        self.assertNotIn("BiteBuilder v1", stdout)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["schema_version"], "go_tui_bridge.v1")
        self.assertEqual(payload["operation"], "setup")
        self.assertFalse(payload["data"]["capabilities"]["mutates_output"])

    def test_media_plan_and_bite_operations_return_valid_read_only_payloads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            transcript_path, xml_path, plan_path = self.write_inputs(tmp)
            output_dir = tmp / "must-not-be-created"
            original_plan = json.loads(plan_path.read_text(encoding="utf-8"))

            media_args = parse_args(
                "--go-tui-bridge", "media",
                "--transcript", str(transcript_path),
                "--xml", str(xml_path),
                "--bridge-count", "1",
            )
            plan_args = parse_args(
                "--go-tui-bridge", "plan",
                "--transcript", str(transcript_path),
                "--xml", str(xml_path),
                "--sequence-plan", str(plan_path),
                "--output", str(output_dir),
            )
            bite_args = parse_args(
                "--bridge-command", "bite",
                "--transcript", str(transcript_path),
                "--xml", str(xml_path),
                "--sequence-plan", str(plan_path),
                "--bridge-bite-id", "bite-001",
                "--output", str(output_dir),
            )

            media_status, media_stdout = run_bridge(media_args)
            plan_status, plan_stdout = run_bridge(plan_args)
            bite_status, bite_stdout = run_bridge(bite_args)

            self.assertEqual(media_status, 0)
            self.assertEqual(plan_status, 0)
            self.assertEqual(bite_status, 0)
            media_payload = json.loads(media_stdout)
            plan_payload = json.loads(plan_stdout)
            bite_payload = json.loads(bite_stdout)
            self.assertEqual(media_payload["data"]["source"]["source_name"], "clip.mov")
            self.assertEqual(media_payload["data"]["transcript"]["count"], 1)
            self.assertEqual(plan_payload["data"]["options"][0]["selected_bite_count"], 1)
            self.assertIn("Spoken text: Hello there.", plan_payload["data"]["summary_text"])
            self.assertEqual(bite_payload["data"]["bite"]["bite_id"], "bite-001")
            self.assertEqual(bite_payload["data"]["segment"]["text"], "Hello there.")
            self.assertFalse(output_dir.exists(), "bridge operation must not render or mutate output")
            self.assertEqual(json.loads(plan_path.read_text(encoding="utf-8")), original_plan)


    def test_assistant_operation_calls_model_with_line_by_line_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            transcript_path, xml_path, _ = self.write_inputs(tmp)
            args = parse_args(
                "--go-tui-bridge", "assistant",
                "--transcript", str(transcript_path),
                "--xml", str(xml_path),
                "--brief", "make this more emotional",
            )

            with patch.object(bitebuilder, "resolve_host", return_value=("http://127.0.0.1:18084", ["gemma-4-E2B-it-Q8_0.gguf"])):
                with patch.object(bitebuilder, "generate_text", return_value="Suggested Creative Brief:\nMake a sharper story.") as generate:
                    status, stdout = run_bridge(args)

            self.assertEqual(status, 0)
            payload = json.loads(stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["operation"], "assistant")
            self.assertIn("Suggested Creative Brief", payload["data"]["suggestion"])
            self.assertGreaterEqual(payload["data"]["transcript"]["segment_count"], 1)
            call = generate.call_args.kwargs
            self.assertIn("## TRANSCRIPT LINE BY LINE", call["user_prompt"])
            self.assertIn("[0] 00:00:00:00 - 00:00:02:00", call["user_prompt"])
            self.assertIn("make this more emotional", call["user_prompt"])
            self.assertEqual(call["model"], bitebuilder.DEFAULT_MODEL)
            self.assertEqual(call["host"], "http://127.0.0.1:18084")

    def test_invalid_operation_returns_json_error_instead_of_argparse_text(self):
        args = parse_args("--go-tui-bridge", "explode")

        status, stdout = run_bridge(args)

        self.assertEqual(status, 1)
        self.assertTrue(stdout.startswith("{"), stdout)
        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["operation"], "explode")
        self.assertEqual(payload["error"]["code"], "GO-TUI-BRIDGE-UNKNOWN-OPERATION")
        self.assertNotIn("usage:", stdout.lower())

    def test_default_tui_parse_behavior_is_preserved(self):
        args = parse_args("--tui")

        self.assertTrue(args.tui)
        self.assertIsNone(args.go_tui_bridge)
        self.assertIsNone(args.transcript)
        self.assertIsNone(args.xml)
        self.assertIsNone(args.brief)

        args_with_plan = parse_args("--tui", "--sequence-plan", "_sequence_plan.json")
        self.assertTrue(args_with_plan.tui)
        self.assertEqual(args_with_plan.sequence_plan, "_sequence_plan.json")


if __name__ == "__main__":
    unittest.main()
