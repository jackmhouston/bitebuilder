import contextlib
import io
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
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


def run_generation(args):
    stdout = io.StringIO()
    status = bitebuilder.run_go_tui_generation(args, writer=stdout)
    return status, stdout.getvalue()


def run_refinement(args):
    stdout = io.StringIO()
    status = bitebuilder.run_go_tui_refinement(args, writer=stdout)
    return status, stdout.getvalue()


def run_export(args):
    stdout = io.StringIO()
    status = bitebuilder.run_go_tui_export(args, writer=stdout)
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

    def write_secondary_inputs(self, tmp: Path) -> tuple[Path, Path]:
        transcript_path = tmp / "transcript-b.txt"
        xml_path = tmp / "source-b.xml"
        transcript_path.write_text(
            "00:00:00:00 - 00:00:02:00\nSpeaker 2\nSecondary hello.\n\n00:00:02:00 - 00:00:04:00\nSpeaker 2\nSecondary proof.\n",
            encoding="utf-8",
        )
        root = ET.fromstring(XML_TEXT)
        pathurl = root.findtext('.//pathurl') or 'file://localhost/source.mov'
        source_name = root.findtext('.//file/name') or 'source.mov'
        xml_path.write_text(
            f'''<?xml version="1.0" encoding="UTF-8"?>
<xmeml version="4">
  <sequence>
    <name>Secondary Interview</name>
    <rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>
    <media>
      <video>
        <track>
          <clipitem>
            <name>{source_name}</name>
            <start>0</start>
            <end>48</end>
            <in>48</in>
            <out>96</out>
            <file>
              <name>{source_name}</name>
              <pathurl>{pathurl}</pathurl>
              <rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>
              <duration>240</duration>
              <media>
                <video><samplecharacteristics><width>1920</width><height>1080</height></samplecharacteristics></video>
                <audio>
                  <channelcount>2</channelcount>
                  <samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics>
                </audio>
              </media>
            </file>
          </clipitem>
        </track>
      </video>
    </media>
  </sequence>
</xmeml>
''',
            encoding="utf-8",
        )
        return transcript_path, xml_path

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
        boundary = payload["data"]["capabilities"]["runtime_boundary"]
        self.assertEqual(
            boundary["python_authoritative_for"],
            [
                "model_calls",
                "sequence_plan_refinement",
                "sequence_plan_validation",
                "xmeml_generation",
            ],
        )
        self.assertEqual(boundary["go_tui_role"], "bubble_tea_ui_and_subprocess_event_client")
        self.assertEqual(boundary["generation_transport"], "subprocess_ndjson")
        self.assertIn("summary", payload["data"]["capabilities"]["operations"])

    def test_media_plan_and_bite_operations_return_valid_read_only_payloads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            transcript_path, xml_path, plan_path = self.write_inputs(tmp)
            output_dir = tmp / "must-not-be-created"
            plan_with_editorial_context = json.loads(plan_path.read_text(encoding="utf-8"))
            first_bite = plan_with_editorial_context["options"][0]["bites"][0]
            first_bite["purpose"] = "opening proof point"
            first_bite["rationale"] = "Starts with the strongest line."
            second_bite = plan_with_editorial_context["options"][0]["bites"][1]
            second_bite["purpose"] = "alternate response"
            second_bite["rationale"] = "Useful if the cut needs a reply beat."
            plan_path.write_text(json.dumps(plan_with_editorial_context), encoding="utf-8")
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
            self.assertEqual(plan_payload["data"]["sequence_plan_path"], str(plan_path))
            board = plan_payload["data"]["board"]
            self.assertEqual(board["sequence_plan_path"], str(plan_path))
            self.assertEqual(len(board["candidates"]), 2)
            self.assertEqual(len(board["selected"]), 1)
            self.assertEqual(board["selected"][0]["bite_id"], "bite-001")
            self.assertEqual(board["selected"][0]["purpose"], "opening proof point")
            self.assertEqual(board["selected"][0]["rationale"], "Starts with the strongest line.")
            self.assertEqual(board["selected"][0]["timecode"], "00:00:00:00 - 00:00:02:00")
            self.assertEqual(board["candidates"][1]["status"], "removed")
            self.assertEqual(board["candidates"][1]["rationale"], "Useful if the cut needs a reply beat.")
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

    def test_assistant_operation_includes_selected_bites_and_question_in_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            transcript_path, xml_path, plan_path = self.write_inputs(tmp)
            selected_intent = {
                "selected_bites": [
                    {
                        "bite_id": "bite-002",
                        "segment_index": 1,
                        "tc_in": "00:00:02:00",
                        "tc_out": "00:00:04:00",
                        "purpose": "alternate closing",
                        "text": "How are you?",
                    }
                ]
            }
            args = parse_args(
                "--go-tui-bridge", "assistant",
                "--transcript", str(transcript_path),
                "--xml", str(xml_path),
                "--sequence-plan", str(plan_path),
                "--brief", "make this more emotional",
                "--refine-instruction", "why this bite?",
                "--selected-bites-json", json.dumps(selected_intent),
            )

            with patch.object(bitebuilder, "resolve_host", return_value=("http://127.0.0.1:18084", ["gemma-4-E2B-it-Q8_0.gguf"])):
                with patch.object(bitebuilder, "generate_text", return_value="Selection Read:\nUse the reply.") as generate:
                    status, stdout = run_bridge(args)

            self.assertEqual(status, 0)
            payload = json.loads(stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["operation"], "assistant")
            self.assertEqual(payload["data"]["selection_context"]["question"], "why this bite?")
            self.assertEqual(payload["data"]["selection_context"]["sequence_plan_path"], str(plan_path))
            self.assertEqual(payload["data"]["selection_context"]["selected_bites"][0]["bite_id"], "bite-002")
            self.assertEqual(payload["data"]["selection_context"]["selected_bites"][0]["text"], "How are you?")
            call = generate.call_args.kwargs
            self.assertIn("## CURRENT SELECTED BITES", call["user_prompt"])
            self.assertIn("bite-002", call["user_prompt"])
            self.assertIn("00:00:02:00 - 00:00:04:00", call["user_prompt"])
            self.assertIn("How are you?", call["user_prompt"])
            self.assertIn("## EDITOR QUESTION ABOUT CURRENT SELECTION", call["user_prompt"])
            self.assertIn("why this bite?", call["user_prompt"])

    def test_summary_operation_calls_model_and_returns_plain_summary_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            transcript_path, xml_path, _ = self.write_inputs(tmp)
            args = parse_args(
                "--go-tui-bridge", "summary",
                "--transcript", str(transcript_path),
                "--xml", str(xml_path),
            )

            with patch.object(bitebuilder, "resolve_host", return_value=("http://127.0.0.1:18084", ["gemma-4-E2B-it-Q8_0.gguf"])):
                with patch.object(bitebuilder, "generate_text", return_value="A concise interview summary with themes.") as generate:
                    status, stdout = run_bridge(args)

            self.assertEqual(status, 0)
            payload = json.loads(stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["operation"], "summary")
            self.assertEqual(payload["data"]["summary_text"], "A concise interview summary with themes.")
            call = generate.call_args.kwargs
            self.assertIn("## TRANSCRIPT LINE BY LINE", call["user_prompt"])
            self.assertIn("[0] 00:00:00:00 - 00:00:02:00", call["user_prompt"])
            self.assertIn("Summarize this interview transcript", call["user_prompt"])

    def test_summary_operation_combines_secondary_transcript_with_source_offset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            transcript_path, xml_path, _ = self.write_inputs(tmp)
            transcript_b_path, xml_b_path = self.write_secondary_inputs(tmp)
            args = parse_args(
                "--go-tui-bridge", "summary",
                "--transcript", str(transcript_path),
                "--xml", str(xml_path),
                "--transcript-b", str(transcript_b_path),
                "--xml-b", str(xml_b_path),
            )

            with patch.object(bitebuilder, "resolve_host", return_value=("http://127.0.0.1:18084", ["gemma-4-E2B-it-Q8_0.gguf"])):
                with patch.object(bitebuilder, "generate_text", return_value="Combined summary.") as generate:
                    status, stdout = run_bridge(args)

            self.assertEqual(status, 0)
            payload = json.loads(stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["data"]["summary_text"], "Combined summary.")
            prompt = generate.call_args.kwargs["user_prompt"]
            self.assertIn("Secondary hello.", prompt)
            self.assertIn("[2] 00:00:02:00 - 00:00:04:00", prompt)
            self.assertIn("[3] 00:00:04:00 - 00:00:06:00", prompt)

    def test_refinement_stream_calls_python_refine_helper_and_emits_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            transcript_path, xml_path, plan_path = self.write_inputs(tmp)
            output_dir = tmp / "refined"
            revision_path = output_dir / "_sequence_plan_revision_2.json"
            xml_out = output_dir / "option-1.xml"
            metadata_path = output_dir / "_sequence_plan_render.json"
            args = parse_args(
                "--go-tui-refine",
                "--sequence-plan", str(plan_path),
                "--transcript", str(transcript_path),
                "--xml", str(xml_path),
                "--output", str(output_dir),
                "--refine-instruction", "make it shorter",
                "--option-id", "option-1",
                "--max-bite-duration", "8",
                "--max-total-duration", "40",
                "--require-changed-cuts",
                "--refinement-retries", "2",
            )

            with patch.object(bitebuilder, "refine_sequence_plan", return_value={
                "revision_path": str(revision_path),
                "output_path": str(xml_out),
                "metadata_path": str(metadata_path),
                "revision": 2,
            }) as refine:
                status, stdout = run_refinement(args)

            self.assertEqual(status, 0)
            events = [json.loads(line) for line in stdout.splitlines()]
            self.assertEqual([event["event"] for event in events], [
                "started",
                "progress",
                "progress",
                "artifact",
                "artifact",
                "artifact",
                "completed",
            ])
            self.assertTrue(all(event["schema_version"] == "go_tui_generation_events.v1" for event in events))
            self.assertEqual(events[0]["command"], "refine")
            self.assertEqual(events[3]["kind"], "sequence_plan")
            self.assertEqual(events[3]["path"], str(revision_path))
            self.assertEqual(events[3]["data"]["exportable_sequence_plan_path"], str(revision_path))
            self.assertEqual(events[4]["kind"], "xmeml")
            self.assertEqual(events[-1]["data"]["revision"], 2)
            call = refine.call_args.kwargs
            self.assertEqual(call["sequence_plan_path"], str(plan_path))
            self.assertEqual(call["instruction"], "make it shorter")
            self.assertEqual(call["option_id"], "option-1")
            self.assertEqual(call["max_bite_duration_seconds"], 8)
            self.assertEqual(call["max_total_duration_seconds"], 40)
            self.assertTrue(call["require_changed_selected_cuts"])
            self.assertEqual(call["refinement_retries"], 2)

    def test_refinement_stream_returns_structured_error_for_missing_instruction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            transcript_path, xml_path, plan_path = self.write_inputs(tmp)
            args = parse_args(
                "--go-tui-refine",
                "--sequence-plan", str(plan_path),
                "--transcript", str(transcript_path),
                "--xml", str(xml_path),
            )

            with patch.object(bitebuilder, "refine_sequence_plan") as refine:
                status, stdout = run_refinement(args)

            self.assertEqual(status, 1)
            refine.assert_not_called()
            events = [json.loads(line) for line in stdout.splitlines()]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event"], "error")
            self.assertEqual(events[0]["error"]["code"], "GO-TUI-REFINEMENT-MISSING-ARG")
            self.assertIn("--refine-instruction", events[0]["error"]["message"])

    def test_export_stream_calls_python_validation_render_and_emits_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            transcript_path, xml_path, plan_path = self.write_inputs(tmp)
            output_dir = tmp / "exports"
            xml_out = output_dir / "Option_1.xml"
            metadata_path = output_dir / "_sequence_plan_render.json"
            args = parse_args(
                "--go-tui-export",
                "--sequence-plan", str(plan_path),
                "--transcript", str(transcript_path),
                "--xml", str(xml_path),
                "--output", str(output_dir),
                "--option-id", "option-1",
            )

            with patch.object(bitebuilder, "render_sequence_plan", return_value={
                "output_path": str(xml_out),
                "metadata_path": str(metadata_path),
                "option_id": "option-1",
                "sequence_name": "Option 1",
                "cuts": [{"name": "cut 1"}, {"name": "cut 2"}],
            }) as render:
                status, stdout = run_export(args)

            self.assertEqual(status, 0)
            events = [json.loads(line) for line in stdout.splitlines()]
            self.assertEqual([event["event"] for event in events], [
                "started",
                "progress",
                "progress",
                "artifact",
                "artifact",
                "completed",
            ])
            self.assertTrue(all(event["schema_version"] == "go_tui_generation_events.v1" for event in events))
            self.assertEqual(events[0]["command"], "export")
            self.assertEqual(events[1]["stage"], "sequence_plan_validation")
            self.assertEqual(events[2]["stage"], "xmeml_generation")
            self.assertEqual(events[3]["kind"], "xmeml")
            self.assertEqual(events[3]["path"], str(xml_out))
            self.assertEqual(events[3]["data"], {
                "option_id": "option-1",
                "sequence_name": "Option 1",
                "cut_count": 2,
            })
            self.assertEqual(events[4]["kind"], "metadata")
            self.assertTrue(events[-1]["ok"])
            self.assertEqual(events[-1]["data"]["output_path"], str(xml_out))
            call = render.call_args.kwargs
            self.assertEqual(call["sequence_plan_text"], plan_path.read_text(encoding="utf-8"))
            self.assertEqual(call["transcript_text"], transcript_path.read_text(encoding="utf-8"))
            self.assertEqual(call["xml_text"], xml_path.read_text(encoding="utf-8"))
            self.assertEqual(call["output_dir"], str(output_dir))
            self.assertEqual(call["option_id"], "option-1")
            self.assertEqual(call["sequence_plan_path"], str(plan_path))
            self.assertEqual(call["selected_bites_json"], "")

    def test_export_stream_applies_selected_board_intent_before_rendering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            transcript_path, xml_path, plan_path = self.write_inputs(tmp)
            output_dir = tmp / "exports"
            selected_intent = {
                "selected_bites": [
                    {
                        "bite_id": "bite-002",
                        "segment_index": 1,
                        "tc_in": "00:00:02:12",
                        "tc_out": "00:00:03:12",
                        "purpose": "replacement ending",
                        "rationale": "Use the reply instead of the greeting.",
                        "status": "replacement",
                        "replaces_bite_id": "bite-001",
                    }
                ]
            }
            args = parse_args(
                "--go-tui-export",
                "--sequence-plan", str(plan_path),
                "--transcript", str(transcript_path),
                "--xml", str(xml_path),
                "--output", str(output_dir),
                "--selected-bites-json", json.dumps(selected_intent),
            )

            status, stdout = run_export(args)

            self.assertEqual(status, 0, stdout)
            events = [json.loads(line) for line in stdout.splitlines()]
            sequence_artifacts = [event for event in events if event.get("kind") == "sequence_plan"]
            self.assertEqual(len(sequence_artifacts), 1)
            selected_plan_path = Path(sequence_artifacts[0]["path"])
            selected_plan = json.loads(selected_plan_path.read_text(encoding="utf-8"))
            bites = selected_plan["options"][0]["bites"]
            self.assertEqual(bites[0]["bite_id"], "bite-002")
            self.assertEqual(bites[0]["status"], "selected")
            self.assertEqual(bites[0]["tc_in"], "00:00:02:12")
            self.assertEqual(bites[0]["tc_out"], "00:00:03:12")
            self.assertEqual(bites[0]["replaces_bite_id"], "bite-001")
            self.assertEqual(bites[0]["purpose"], "replacement ending")
            self.assertEqual(bites[1]["bite_id"], "bite-001")
            self.assertEqual(bites[1]["status"], "removed")
            completed = events[-1]["data"]
            self.assertEqual(completed["cut_count"], 1)
            xmeml_artifacts = [event for event in events if event.get("kind") == "xmeml"]
            self.assertEqual(len(xmeml_artifacts), 1)
            xmeml_root = ET.parse(xmeml_artifacts[0]["path"]).getroot()
            video_clipitems = xmeml_root.findall(".//video/track/clipitem")
            self.assertEqual(len(video_clipitems), 1)
            self.assertEqual(video_clipitems[0].findtext("start"), "0")
            self.assertEqual(video_clipitems[0].findtext("end"), "24")
            self.assertEqual(video_clipitems[0].findtext("in"), "60")
            self.assertEqual(video_clipitems[0].findtext("out"), "84")

    def test_export_stream_preserves_selected_board_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            transcript_path, xml_path, plan_path = self.write_inputs(tmp)
            output_dir = tmp / "exports"
            selected_intent = {
                "selected_bites": [
                    {
                        "bite_id": "bite-002",
                        "segment_index": 1,
                        "tc_in": "00:00:02:00",
                        "tc_out": "00:00:04:00",
                        "status": "selected",
                    },
                    {
                        "bite_id": "bite-001",
                        "segment_index": 0,
                        "tc_in": "00:00:00:00",
                        "tc_out": "00:00:02:00",
                        "status": "selected",
                    },
                ]
            }
            args = parse_args(
                "--go-tui-export",
                "--sequence-plan", str(plan_path),
                "--transcript", str(transcript_path),
                "--xml", str(xml_path),
                "--output", str(output_dir),
                "--selected-bites-json", json.dumps(selected_intent),
            )

            status, stdout = run_export(args)

            self.assertEqual(status, 0, stdout)
            events = [json.loads(line) for line in stdout.splitlines()]
            selected_plan_path = Path([event for event in events if event.get("kind") == "sequence_plan"][0]["path"])
            selected_plan = json.loads(selected_plan_path.read_text(encoding="utf-8"))
            selected_ids = [
                bite["bite_id"]
                for bite in selected_plan["options"][0]["bites"]
                if bite["status"] == "selected"
            ]
            self.assertEqual(selected_ids, ["bite-002", "bite-001"])
            self.assertEqual(events[-1]["data"]["cut_count"], 2)

    def test_export_stream_returns_structured_error_for_invalid_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            transcript_path, xml_path, plan_path = self.write_inputs(tmp)
            plan_path.write_text("{not-json", encoding="utf-8")
            args = parse_args(
                "--go-tui-export",
                "--sequence-plan", str(plan_path),
                "--transcript", str(transcript_path),
                "--xml", str(xml_path),
            )

            status, stdout = run_export(args)

            self.assertEqual(status, 1)
            events = [json.loads(line) for line in stdout.splitlines()]
            self.assertEqual(events[-1]["event"], "error")
            self.assertEqual(events[-1]["error"]["code"], "SEQUENCE-PLAN-JSON-INVALID")
            self.assertEqual(events[-1]["stage"], "sequence_plan")
            self.assertNotIn("usage:", stdout.lower())

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

    def test_generation_command_emits_ordered_ndjson_events(self):
        args = parse_args(
            "--go-tui-generate",
            "--transcript", "interview.txt",
            "--xml", "source.xml",
            "--brief", "make a proof point",
            "--output", "out",
            "--options", "1",
        )

        def fake_run_pipeline(**kwargs):
            kwargs["progress_callback"]("Parsing transcript.")
            kwargs["progress_callback"]("Running generation attempt 1.")
            kwargs["progress_callback"]("Writing output files.")
            return {
                "sequence_plan_path": "out/_sequence_plan.json",
                "output_files": [
                    {
                        "filename": "Option_1.xml",
                        "path": "out/Option_1.xml",
                        "cut_count": 2,
                        "sequence_plan_option_id": "option-1",
                    }
                ],
                "output_dir": str(Path("out").resolve()),
            }

        with patch.object(bitebuilder, "read_text_file", side_effect=["TRANSCRIPT", "XML"]):
            with patch.object(bitebuilder, "run_pipeline", side_effect=fake_run_pipeline) as pipeline:
                status, stdout = run_generation(args)

        self.assertEqual(status, 0)
        self.assertNotIn("BiteBuilder v1", stdout)
        events = [json.loads(line) for line in stdout.splitlines()]
        self.assertEqual(
            [event["event"] for event in events],
            ["started", "progress", "progress", "progress", "artifact", "artifact", "completed"],
        )
        self.assertTrue(all(event["schema_version"] == "go_tui_generation_events.v1" for event in events))
        request_ids = {event["request_id"] for event in events}
        self.assertEqual(len(request_ids), 1)
        self.assertEqual(events[2]["stage"], "model_request")
        self.assertEqual(events[4]["kind"], "sequence_plan")
        self.assertEqual(events[4]["data"]["exportable_sequence_plan_path"], "out/_sequence_plan.json")
        self.assertEqual(events[5]["kind"], "xmeml")
        self.assertTrue(events[-1]["ok"])
        call = pipeline.call_args.kwargs
        self.assertEqual(call["transcript_text"], "TRANSCRIPT")
        self.assertEqual(call["xml_text"], "XML")
        self.assertEqual(call["brief"], "make a proof point")
        self.assertEqual(call["options"], 1)

    def test_generation_stream_preserves_python_xmeml_export_artifacts(self):
        args = parse_args(
            "--go-tui-generate",
            "--transcript", "interview.txt",
            "--xml", "source.xml",
            "--brief", "make a proof point",
            "--output", "python-out",
        )

        def fake_run_pipeline(**kwargs):
            return {
                "sequence_plan_path": "python-out/_sequence_plan.json",
                "output_files": [
                    {
                        "filename": "Option_1.xml",
                        "path": "python-out/Option_1.xml",
                        "cut_count": 2,
                        "sequence_plan_option_id": "option-1",
                    },
                    {
                        "filename": "Option_2.xml",
                        "path": "python-out/Option_2.xml",
                        "cut_count": 3,
                        "sequence_plan_option_id": "option-2",
                    },
                ],
                "output_dir": "python-out",
            }

        with patch.object(bitebuilder, "read_text_file", side_effect=["TRANSCRIPT", "XML"]):
            with patch.object(bitebuilder, "run_pipeline", side_effect=fake_run_pipeline) as pipeline:
                status, stdout = run_generation(args)

        self.assertEqual(status, 0)
        pipeline.assert_called_once()
        self.assertEqual(pipeline.call_args.kwargs["output_dir"], "python-out")
        events = [json.loads(line) for line in stdout.splitlines()]
        xmeml_events = [event for event in events if event.get("kind") == "xmeml"]
        self.assertEqual([event["path"] for event in xmeml_events], [
            "python-out/Option_1.xml",
            "python-out/Option_2.xml",
        ])
        self.assertEqual(xmeml_events[0]["data"], {
            "filename": "Option_1.xml",
            "cut_count": 2,
            "sequence_plan_option_id": "option-1",
        })
        self.assertEqual(events[-1]["data"], {
            "output_dir": "python-out",
            "output_file_count": 2,
            "sequence_plan_path": "python-out/_sequence_plan.json",
        })

    def test_generation_command_emits_json_error_for_missing_required_args(self):
        args = parse_args("--go-tui-generate", "--transcript", "interview.txt", "--xml", "source.xml")

        status, stdout = run_generation(args)

        self.assertEqual(status, 1)
        self.assertTrue(stdout.startswith("{"), stdout)
        payload = json.loads(stdout)
        self.assertEqual(payload["event"], "error")
        self.assertEqual(payload["schema_version"], "go_tui_generation_events.v1")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "GO-TUI-GENERATION-MISSING-ARG")
        self.assertEqual(payload["error"]["details"]["field"], "brief")
        self.assertNotIn("usage:", stdout.lower())

    def test_default_tui_parse_behavior_is_preserved(self):
        args = parse_args("--tui")

        self.assertTrue(args.tui)
        self.assertIsNone(args.go_tui_bridge)
        self.assertFalse(args.go_tui_generate)
        self.assertFalse(args.go_tui_export)
        self.assertIsNone(args.transcript)
        self.assertIsNone(args.xml)
        self.assertIsNone(args.brief)

        args_with_plan = parse_args("--tui", "--sequence-plan", "_sequence_plan.json")
        self.assertTrue(args_with_plan.tui)
        self.assertEqual(args_with_plan.sequence_plan, "_sequence_plan.json")


if __name__ == "__main__":
    unittest.main()
