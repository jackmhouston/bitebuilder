import contextlib
import io
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


import bitebuilder
from generator.sequence_plan import build_sequence_plan
from parser.transcript import TranscriptSegment


SEGMENTS = [
    TranscriptSegment("00:00:00:00", "00:00:02:00", "Speaker 1", "Hello there."),
    TranscriptSegment("00:00:02:00", "00:00:04:00", "Speaker 2", "General Kenobi."),
]


def args(**overrides):
    data = {
        "transcript": None,
        "xml": None,
        "brief": None,
        "options": 1,
        "model": "gemma3:4b",
        "output": "./output",
        "host": "http://127.0.0.1:11434",
        "timeout": 1,
        "thinking_mode": "auto",
        "option_id": None,
        "build": False,
        "max_bite_duration": None,
        "max_total_duration": None,
        "require_changed_cuts": False,
        "refinement_retries": 1,
    }
    data.update(overrides)
    return Namespace(**data)


def plan_payload():
    return build_sequence_plan(
        transcript_segments=SEGMENTS,
        options=[
            {
                "option_id": "option-1",
                "name": "Greeting",
                "estimated_duration_seconds": 2,
                "bites": [
                    {
                        "segment_index": 0,
                        "tc_in": "00:00:00:00",
                        "tc_out": "00:00:02:00",
                        "purpose": "HOOK",
                        "text": "Hello there.",
                        "dialogue_summary": "Hello there.",
                    }
                ],
            }
        ],
    ).to_dict()


def two_bite_plan_payload():
    return build_sequence_plan(
        transcript_segments=SEGMENTS,
        options=[
            {
                "option_id": "option-1",
                "name": "Greeting",
                "estimated_duration_seconds": 4,
                "bites": [
                    {
                        "segment_index": 0,
                        "tc_in": "00:00:00:00",
                        "tc_out": "00:00:02:00",
                        "purpose": "HOOK",
                        "text": "Hello there.",
                        "dialogue_summary": "Hello there.",
                        "rationale": "Starts with the clearest line.",
                    },
                    {
                        "segment_index": 1,
                        "tc_in": "00:00:02:00",
                        "tc_out": "00:00:04:00",
                        "purpose": "BUTTON",
                        "text": "General Kenobi.",
                        "dialogue_summary": "General Kenobi.",
                    },
                ],
            }
        ],
    ).to_dict()


def fake_reader_for(sequence_plan_path: Path):
    def fake_read_text_file(path):
        if Path(path) == sequence_plan_path:
            return sequence_plan_path.read_text(encoding="utf-8")
        return f"contents:{path}"
    return fake_read_text_file


class GuidedCliFlowTests(unittest.TestCase):
    def test_prompt_with_default_strips_wrapping_quotes(self):
        self.assertEqual(
            bitebuilder.prompt_with_default("Path", None, input_func=lambda prompt: "'/tmp/example file.txt'"),
            "/tmp/example file.txt",
        )

    def test_guided_accept_path_uses_prompt_defaults_and_summarizes_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            sequence_plan_path = tmp / "_sequence_plan.json"
            sequence_plan_path.write_text(json.dumps(plan_payload()), encoding="utf-8")
            outputs = []
            values = iter(["", "", "context", "", "", "", "", "", "", "a"])
            mocked_result = {
                "sequence_plan_path": str(sequence_plan_path),
                "segments": SEGMENTS,
                "output_dir": str(tmp),
            }

            with patch.object(bitebuilder, "read_text_file", side_effect=fake_reader_for(sequence_plan_path)):
                with patch.object(bitebuilder, "run_pipeline", return_value=mocked_result) as run_pipeline:
                    result = bitebuilder.run_guided_flow(
                        args(transcript="transcript.txt", xml="source.xml", brief="goal", output=str(tmp)),
                        input_func=lambda prompt: next(values),
                        print_func=outputs.append,
                    )

            self.assertEqual(result["action"], "accept")
            run_pipeline.assert_called_once()
            self.assertEqual(run_pipeline.call_args.kwargs["project_context"], "context")
            self.assertEqual(run_pipeline.call_args.kwargs["brief"], "goal")
            self.assertTrue(any("Option option-1: Greeting" in item for item in outputs))
            self.assertTrue(any("Spoken text: Hello there." in item for item in outputs))

    def test_summarize_sequence_plan_includes_editorial_duration_and_rationale(self):
        plan = bitebuilder.SequencePlan.from_dict(two_bite_plan_payload(), transcript_segments=SEGMENTS)

        summary = bitebuilder.summarize_sequence_plan(plan, timebase=24, ntsc=False)

        self.assertIn("Total selected duration: 4.0s", summary)
        self.assertIn("00:00:00:00 - 00:00:02:00 (2.0s)", summary)
        self.assertIn("Rationale: Starts with the clearest line.", summary)
        self.assertIn("Spoken text: Hello there.", summary)

    def test_sequence_plan_direct_edits_add_delete_and_move_selected_segments(self):
        plan = bitebuilder.SequencePlan.from_dict(plan_payload(), transcript_segments=SEGMENTS)

        added = bitebuilder.add_segment_to_sequence_plan(
            plan,
            transcript_segments=SEGMENTS,
            segment_index=1,
            timebase=24,
            ntsc=False,
        )
        self.assertEqual([bite.segment_index for bite in added.options[0].selected_bites()], [0, 1])

        moved = bitebuilder.move_selected_bite_in_sequence_plan(
            added,
            transcript_segments=SEGMENTS,
            from_position=2,
            to_position=1,
            timebase=24,
            ntsc=False,
        )
        self.assertEqual([bite.segment_index for bite in moved.options[0].selected_bites()], [1, 0])

        removed = bitebuilder.remove_selected_bite_from_sequence_plan(
            moved,
            transcript_segments=SEGMENTS,
            selected_position=2,
            timebase=24,
            ntsc=False,
        )
        self.assertEqual([bite.segment_index for bite in removed.options[0].selected_bites()], [1])

    def test_guided_build_path_enters_persistent_builder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            sequence_plan_path = tmp / "_sequence_plan.json"
            sequence_plan_path.write_text(json.dumps(plan_payload()), encoding="utf-8")
            values = iter(["transcript.txt", "source.xml", "context", "goal", "gemma3:4b", str(tmp), "", "", "N", "b"])
            mocked_result = {
                "sequence_plan_path": str(sequence_plan_path),
                "segments": SEGMENTS,
                "output_dir": str(tmp),
            }
            mocked_builder = {"action": "build", "status": "accept", "plan_path": str(sequence_plan_path)}

            with patch.object(bitebuilder, "read_text_file", side_effect=fake_reader_for(sequence_plan_path)):
                with patch.object(bitebuilder, "run_pipeline", return_value=mocked_result):
                    with patch.object(bitebuilder, "run_guided_build_loop", return_value=mocked_builder) as build_loop:
                        result = bitebuilder.run_guided_flow(
                            args(),
                            input_func=lambda prompt: next(values),
                            print_func=lambda message: None,
                        )

            self.assertEqual(result["action"], "build")
            self.assertEqual(result["builder"], mocked_builder)
            build_loop.assert_called_once()

    def test_guided_refine_path_uses_revision_safe_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            sequence_plan_path = tmp / "_sequence_plan.json"
            sequence_plan_path.write_text(json.dumps(plan_payload()), encoding="utf-8")
            values = iter(["transcript.txt", "source.xml", "context", "goal", "gemma3:4b", str(tmp), "10", "90", "y", "r", "make shorter"])
            mocked_result = {"sequence_plan_path": str(sequence_plan_path), "segments": SEGMENTS, "output_dir": str(tmp)}
            mocked_refinement = {"output_path": str(tmp / "refinement-2" / "out.xml"), "revision_path": str(tmp / "refinement-2" / "_sequence_plan_revision_2.json")}

            with patch.object(bitebuilder, "read_text_file", side_effect=fake_reader_for(sequence_plan_path)):
                with patch.object(bitebuilder, "run_pipeline", return_value=mocked_result):
                    with patch.object(bitebuilder, "refine_sequence_plan", return_value=mocked_refinement) as refine:
                        result = bitebuilder.run_guided_flow(
                            args(),
                            input_func=lambda prompt: next(values),
                            print_func=lambda message: None,
                        )

            self.assertEqual(result["action"], "refine")
            refine.assert_called_once()
            self.assertTrue(refine.call_args.kwargs["output_dir"].endswith("refinement-2"))
            self.assertEqual(refine.call_args.kwargs["max_bite_duration_seconds"], 10.0)
            self.assertEqual(refine.call_args.kwargs["max_total_duration_seconds"], 90.0)
            self.assertTrue(refine.call_args.kwargs["require_changed_selected_cuts"])

    def test_guided_stop_path_returns_without_refinement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            sequence_plan_path = tmp / "_sequence_plan.json"
            sequence_plan_path.write_text(json.dumps(plan_payload()), encoding="utf-8")
            values = iter(["transcript.txt", "source.xml", "context", "goal", "gemma3:4b", str(tmp), "", "", "N", "s"])
            mocked_result = {"sequence_plan_path": str(sequence_plan_path), "segments": SEGMENTS, "output_dir": str(tmp)}

            with patch.object(bitebuilder, "read_text_file", side_effect=fake_reader_for(sequence_plan_path)):
                with patch.object(bitebuilder, "run_pipeline", return_value=mocked_result):
                    with patch.object(bitebuilder, "refine_sequence_plan") as refine:
                        result = bitebuilder.run_guided_flow(args(), input_func=lambda prompt: next(values), print_func=lambda message: None)

            self.assertEqual(result["action"], "stop")
            refine.assert_not_called()

    def test_invalid_action_reprompts_once_then_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            sequence_plan_path = tmp / "_sequence_plan.json"
            sequence_plan_path.write_text(json.dumps(plan_payload()), encoding="utf-8")
            values = iter(["transcript.txt", "source.xml", "context", "goal", "gemma3:4b", str(tmp), "", "", "N", "x", "x"])
            mocked_result = {"sequence_plan_path": str(sequence_plan_path), "segments": SEGMENTS, "output_dir": str(tmp)}

            with patch.object(bitebuilder, "read_text_file", side_effect=fake_reader_for(sequence_plan_path)):
                with patch.object(bitebuilder, "run_pipeline", return_value=mocked_result):
                    with self.assertRaises(bitebuilder.BiteBuilderError):
                        bitebuilder.run_guided_flow(args(), input_func=lambda prompt: next(values), print_func=lambda message: None)

    def test_parse_args_allows_guided_without_required_paths(self):
        with patch("sys.argv", ["bitebuilder.py", "--guided"]):
            parsed = bitebuilder.parse_args()
        self.assertTrue(parsed.guided)
        self.assertIsNone(parsed.transcript)
        self.assertIsNone(parsed.xml)
        self.assertIsNone(parsed.brief)

    def test_non_guided_still_requires_transcript_xml_and_brief(self):
        with patch("sys.argv", ["bitebuilder.py", "--transcript", "t.txt", "--xml", "x.xml"]):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    bitebuilder.parse_args()

    def test_build_requires_sequence_plan(self):
        with patch("sys.argv", ["bitebuilder.py", "--build"]):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    bitebuilder.parse_args()

    def test_sequence_plan_build_mode_parses(self):
        with patch("sys.argv", ["bitebuilder.py", "--sequence-plan", "plan.json", "--transcript", "t.txt", "--xml", "x.xml", "--build"]):
            parsed = bitebuilder.parse_args()
        self.assertTrue(parsed.build)
        self.assertEqual(parsed.sequence_plan, "plan.json")

    def test_missing_sequence_plan_before_refine_fails(self):
        values = iter(["transcript.txt", "source.xml", "context", "goal", "gemma3:4b", "out", "", "", "N", "r"])
        mocked_result = {"sequence_plan_path": None, "segments": SEGMENTS, "output_dir": "out"}

        with patch.object(bitebuilder, "read_text_file", side_effect=lambda path: f"contents:{path}"):
            with patch.object(bitebuilder, "run_pipeline", return_value=mocked_result):
                with self.assertRaises(bitebuilder.BiteBuilderError) as ctx:
                    bitebuilder.run_guided_flow(args(), input_func=lambda prompt: next(values), print_func=lambda message: None)

        self.assertEqual(ctx.exception.error["code"], "GUIDED-SEQUENCE-PLAN-MISSING")

    def test_guided_refine_schema_retry_retries_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            sequence_plan_path = tmp / "_sequence_plan.json"
            sequence_plan_path.write_text(json.dumps(plan_payload()), encoding="utf-8")
            values = iter(["transcript.txt", "source.xml", "context", "goal", "gemma3:4b", str(tmp), "", "", "N", "r", "make shorter"])
            mocked_result = {"sequence_plan_path": str(sequence_plan_path), "segments": SEGMENTS, "output_dir": str(tmp)}
            schema_error = bitebuilder.BiteBuilderError(bitebuilder.build_validation_error(
                code="SEQUENCE-PLAN-REFINE-FAILED",
                error_type="runtime_model_output",
                message="bad schema",
                expected_input_format="sequence_plan.v1",
                next_action="retry",
                stage="sequence_plan_refinement",
            ))
            mocked_refinement = {"output_path": str(tmp / "refinement-2" / "out.xml"), "revision_path": str(tmp / "refinement-2" / "_sequence_plan_revision_2.json")}

            with patch.object(bitebuilder, "read_text_file", side_effect=fake_reader_for(sequence_plan_path)):
                with patch.object(bitebuilder, "run_pipeline", return_value=mocked_result):
                    with patch.object(bitebuilder, "refine_sequence_plan", side_effect=[schema_error, mocked_refinement]) as refine:
                        result = bitebuilder.run_guided_flow(args(), input_func=lambda prompt: next(values), print_func=lambda message: None)

            self.assertEqual(result["action"], "refine")
            self.assertEqual(refine.call_count, 2)


if __name__ == "__main__":
    unittest.main()
