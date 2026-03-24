import io
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import bitebuilder
from generator.timecode import estimate_duration_seconds
from generator.timecode import frames_to_tc, tc_to_frames
from generator.xmeml import generate_sequence
from llm.prompts import build_editorial_direction_prompt, build_user_prompt, validate_llm_response
from parser.premiere_xml import parse_premiere_xml
from parser.transcript import (
    format_for_llm,
    get_valid_timecodes,
    parse_transcript,
    parse_transcript_file,
    TranscriptValidationError,
)
from bitebuilder import BiteBuilderError
from bitebuilder import run_pipeline


FIXTURES_DIR = Path(__file__).parent / "fixtures"
TRANSCRIPT_FIXTURE = FIXTURES_DIR / "sample_transcript.txt"
XML_FIXTURE = FIXTURES_DIR / "sample_premiere.xml"
INVALID_TRANSCRIPT_FIXTURE = FIXTURES_DIR / "malformed_transcript.txt"
INVALID_XML_FIXTURE = FIXTURES_DIR / "invalid_premiere.xml"

MOCK_RESPONSE = {
    "selection_status": "ok",
    "options": [
        {
            "name": "Margin Story",
            "description": "Frames the objection, proves the upside, and lands on a call to test.",
            "estimated_duration_seconds": 15,
            "cuts": [
                {
                    "order": 1,
                    "segment_index": 0,
                    "tc_in": "00:00:00:00",
                    "tc_out": "00:00:05:00",
                    "speaker": "Speaker 1",
                    "confidence": 0.94,
                    "purpose": "HOOK",
                    "dialogue_summary": "States the common objection.",
                },
                {
                    "order": 2,
                    "segment_index": 1,
                    "tc_in": "00:00:05:00",
                    "tc_out": "00:00:10:00",
                    "speaker": "Speaker 1",
                    "confidence": 0.92,
                    "purpose": "PROOF",
                    "dialogue_summary": "Explains the operating upside.",
                },
                {
                    "order": 3,
                    "segment_index": 4,
                    "tc_in": "00:00:20:00",
                    "tc_out": "00:00:25:00",
                    "speaker": "Speaker 2",
                    "confidence": 0.9,
                    "purpose": "BUTTON",
                    "dialogue_summary": "Ends with a call to test the workflow.",
                },
            ],
        },
        {
            "name": "Proof Points",
            "description": "Moves from product framing into proof-oriented soundbites.",
            "estimated_duration_seconds": 15,
            "cuts": [
                {
                    "order": 1,
                    "segment_index": 2,
                    "tc_in": "00:00:10:00",
                    "tc_out": "00:00:15:00",
                    "speaker": "Speaker 2",
                    "confidence": 0.91,
                    "purpose": "HOOK",
                    "dialogue_summary": "Introduces the product promise.",
                },
                {
                    "order": 2,
                    "segment_index": 3,
                    "tc_in": "00:00:15:00",
                    "tc_out": "00:00:20:00",
                    "speaker": "Speaker 1",
                    "confidence": 0.93,
                    "purpose": "PIVOT",
                    "dialogue_summary": "Explains the narrative structure of the edit.",
                },
                {
                    "order": 3,
                    "segment_index": 4,
                    "tc_in": "00:00:20:00",
                    "tc_out": "00:00:25:00",
                    "speaker": "Speaker 2",
                    "confidence": 0.95,
                    "purpose": "CLOSE",
                    "dialogue_summary": "Closes with a real-project test invitation.",
                },
            ],
        },
    ]
}


class BiteBuilderPipelineTests(unittest.TestCase):
    def test_infer_target_duration_range_reads_min_max_range(self):
        target = bitebuilder.infer_target_duration_range(
            "Need a few options for a :45 to a :60 second cut",
            "Keep it hooky and accessible.",
        )
        self.assertEqual(target, (45, 60))

    def test_transcript_parser_extracts_segments(self):
        segments = parse_transcript_file(str(TRANSCRIPT_FIXTURE))
        self.assertEqual(len(segments), 5)
        self.assertEqual(segments[0].speaker, "Speaker 1")
        self.assertIn("Most shops think better nutrition", segments[0].text)
        self.assertEqual(len(get_valid_timecodes(segments)), 6)

    def test_prompt_validation_accepts_fixture_response(self):
        segments = parse_transcript_file(str(TRANSCRIPT_FIXTURE))
        formatted = format_for_llm(segments)
        prompt = build_user_prompt(formatted, "45 second proof of concept", 2)
        self.assertIn("CREATIVE BRIEF", prompt)

        errors = validate_llm_response(MOCK_RESPONSE, get_valid_timecodes(segments))
        self.assertEqual(errors, [])

    def test_validate_llm_response_checks_segment_definition_boundaries(self):
        segments = parse_transcript_file(str(TRANSCRIPT_FIXTURE))
        response = {
            "selection_status": "ok",
            "options": [
                {
                    "name": "Mismatch",
                    "description": "Wrong segment mapping on purpose.",
                    "estimated_duration_seconds": 10,
                    "cuts": [{
                        "order": 1,
                        "segment_index": 1,
                        "tc_in": "00:00:00:00",
                        "tc_out": "00:00:05:00",
                        "speaker": "Speaker 1",
                        "confidence": 0.91,
                        "purpose": "HOOK",
                        "dialogue_summary": "Mismatch test.",
                    }],
                },
            ],
        }
        errors = validate_llm_response(
            response=response,
            valid_timecodes=get_valid_timecodes(segments),
            expected_options=1,
            transcript_segments=segments,
        )
        self.assertTrue(any("does not match a transcript segment definition" in error for error in errors))

    def test_build_user_prompt_includes_editorial_conversation(self):
        segments = parse_transcript_file(str(TRANSCRIPT_FIXTURE))
        formatted = format_for_llm(segments)
        prompt = build_user_prompt(
            formatted,
            "45 second proof of concept",
            2,
            project_context="B2B nutrition software",
            editorial_messages=[
                {"role": "assistant", "content": "Open with the objection."},
                {"role": "user", "content": "Make it whacky and surprising."},
            ],
        )

        self.assertIn("## EDITORIAL CONVERSATION", prompt)
        self.assertIn("USER: Make it whacky and surprising.", prompt)
        self.assertIn("latest USER message", prompt)

    def test_build_editorial_direction_prompt_includes_latest_chat(self):
        prompt = build_editorial_direction_prompt(
            brief="45 second proof of concept",
            project_context="B2B nutrition software",
            messages=[
                {"role": "assistant", "content": "Open with the objection."},
                {"role": "user", "content": "Make it whacky and off-center."},
            ],
        )

        self.assertIn("## CURRENT BRIEF", prompt)
        self.assertIn("## EDITORIAL CONVERSATION", prompt)
        self.assertIn("USER: Make it whacky and off-center.", prompt)

    def test_premiere_parser_reads_metadata(self):
        source = parse_premiere_xml(str(XML_FIXTURE))
        self.assertEqual(source.source_name, "Sample Interview.mov")
        self.assertEqual(source.source_path, "C:/Projects/BiteBuilder/Sample Interview.mov")
        self.assertEqual(source.timebase, 24)
        self.assertFalse(source.ntsc)
        self.assertEqual(source.duration, 2400)
        self.assertEqual(source.width, 1920)
        self.assertEqual(source.audio_channels, 2)

    def test_xmeml_generation_builds_stereo_sequence(self):
        source = parse_premiere_xml(str(XML_FIXTURE))
        cuts = [
            {"tc_in": cut["tc_in"], "tc_out": cut["tc_out"]}
            for cut in MOCK_RESPONSE["options"][0]["cuts"]
        ]
        xml_str = generate_sequence("Margin Story", cuts, source)
        tree = ET.fromstring(xml_str)

        video_clips = tree.findall(".//video/track/clipitem")
        audio_tracks = tree.findall(".//audio/track")
        self.assertEqual(len(video_clips), 3)
        self.assertEqual(len(audio_tracks), 2)
        self.assertEqual(tree.find(".//file/pathurl").text, source.pathurl)

        total_duration = sum(
            estimate_duration_seconds(cut["tc_in"], cut["tc_out"], source.timebase, source.ntsc)
            for cut in cuts
        )
        self.assertGreater(total_duration, 0)

    def test_timecode_roundtrip_preserved_for_fixture_segments(self):
        segments = parse_transcript_file(str(TRANSCRIPT_FIXTURE))
        source = parse_premiere_xml(str(XML_FIXTURE))
        for seg in segments:
            tc_in_frames = tc_to_frames(seg.tc_in, source.timebase)
            tc_out_frames = tc_to_frames(seg.tc_out, source.timebase)
            self.assertEqual(frames_to_tc(tc_in_frames, source.timebase), seg.tc_in)
            self.assertEqual(frames_to_tc(tc_out_frames, source.timebase), seg.tc_out)
            estimated_seconds = estimate_duration_seconds(
                seg.tc_in, seg.tc_out, source.timebase, source.ntsc,
            )
            expected_seconds = (tc_out_frames - tc_in_frames) / source.actual_fps
            self.assertAlmostEqual(estimated_seconds, expected_seconds, places=6)

    def test_parse_transcript_rejects_reversed_or_zero_length_segments(self):
        transcript = (
            "00:00:05:00 - 00:00:05:00\nSpeaker 1\n"
            "Zero-length cut.\n\n"
            "00:00:10:00 - 00:00:08:00\nSpeaker 1\n"
            "Reversed range.\n"
        )
        with self.assertRaises(TranscriptValidationError) as exc:
            parse_transcript(transcript, strict=True)
        self.assertTrue(
            any("time_range" == error["field"] for error in exc.exception.errors)
        )

    def test_parse_transcript_rejects_overlap(self):
        transcript = (
            "00:00:00:00 - 00:00:06:00\nSpeaker 1\n"
            "First clip.\n\n"
            "00:00:05:00 - 00:00:10:00\nSpeaker 1\n"
            "Overlaps prior clip.\n"
        )
        with self.assertRaises(TranscriptValidationError) as exc:
            parse_transcript(transcript, strict=True)
        self.assertTrue(any("time_transition" in item["field"] for item in exc.exception.errors))

    def test_parse_transcript_rejects_malformed_format_with_line_context(self):
        transcript = (
            "00:00:00:00 - 00:00:05:0\nSpeaker 1\n"
            "One-digit frame should fail strict parsing.\n"
        )
        with self.assertRaises(TranscriptValidationError) as exc:
            parse_transcript(transcript, strict=True)
        self.assertEqual(exc.exception.errors[0]["line"], 1)
        self.assertIn("line 1", exc.exception.errors[0]["context"])

    def test_invalid_transcript_errors_before_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_transcript = (
                "00:00:10:00 - 00:00:05:00\nSpeaker 1\n"
                "Invalid range.\n"
            )
            with self.assertRaises(bitebuilder.BiteBuilderError) as exc:
                run_pipeline(
                    transcript_text=invalid_transcript,
                    xml_text=XML_FIXTURE.read_text(encoding="utf-8"),
                    brief="45 second proof of concept",
                    output_dir=temp_dir,
                )
            self.assertEqual(exc.exception.error["code"], "TRANSCRIPT-TIMECODE-INVALID")
            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_cli_main_writes_output_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "output"
            argv = [
                "bitebuilder.py",
                "--transcript",
                str(TRANSCRIPT_FIXTURE),
                "--xml",
                str(XML_FIXTURE),
                "--brief",
                "45 second proof of concept",
                "--options",
                "2",
                "--output",
                str(output_dir),
            ]

            with patch("bitebuilder.resolve_host", return_value=("http://127.0.0.1:11435", ["qwen3:8b"])), \
                 patch("bitebuilder.ollama_generate", return_value=MOCK_RESPONSE), \
                 patch("sys.argv", argv), \
                 redirect_stdout(io.StringIO()), \
                 redirect_stderr(io.StringIO()):
                bitebuilder.main()

            generated = sorted(output_dir.glob("*.xml"))
            self.assertEqual([path.name for path in generated], [
                "Margin_Story.xml",
                "Proof_Points.xml",
            ])

            debug_response = json.loads((output_dir / "_llm_response.json").read_text())
            self.assertEqual(len(debug_response["options"]), 2)

    def test_cli_fixture_output_shape_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "output"
            argv = [
                "bitebuilder.py",
                "--transcript",
                str(TRANSCRIPT_FIXTURE),
                "--xml",
                str(XML_FIXTURE),
                "--brief",
                "45 second proof of concept",
                "--options",
                "2",
                "--output",
                str(output_dir),
            ]

            with patch("bitebuilder.resolve_host", return_value=("http://127.0.0.1:11435", ["qwen3:8b"])), \
                 patch("bitebuilder.ollama_generate", return_value=MOCK_RESPONSE), \
                 patch("sys.argv", argv), \
                 redirect_stdout(io.StringIO()), \
                 redirect_stderr(io.StringIO()):
                bitebuilder.main()

            generated = sorted(output_dir.glob("*.xml"))
            self.assertEqual([path.name for path in generated], [
                "Margin_Story.xml",
                "Proof_Points.xml",
            ])

            result = json.loads((output_dir / "_llm_response.json").read_text(encoding="utf-8"))
            self.assertEqual(result["selection_status"], "ok")
            self.assertEqual(len(result.get("options", [])), 2)

            option = result["options"][0]
            self.assertIn("name", option)
            self.assertIn("description", option)
            self.assertIn("estimated_duration_seconds", option)
            self.assertIn("cuts", option)
            self.assertEqual(len(option["cuts"]), 3)

            first_cut = option["cuts"][0]
            self.assertEqual(first_cut["segment_index"], 0)
            self.assertEqual(first_cut["tc_in"], "00:00:00:00")
            self.assertEqual(first_cut["tc_out"], "00:00:05:00")
            self.assertEqual(first_cut["speaker"], "Speaker 1")

    def test_cli_rejects_fixtureed_malformed_transcript_with_structured_code(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "output"
            with patch("bitebuilder.resolve_host", return_value=("http://127.0.0.1:11435", ["qwen3:8b"])), \
                 patch("bitebuilder.ollama_generate", return_value=MOCK_RESPONSE), \
                 redirect_stdout(io.StringIO()), \
                 redirect_stderr(io.StringIO()):
                with self.assertRaises(BiteBuilderError) as exc:
                    run_pipeline(
                        transcript_text=INVALID_TRANSCRIPT_FIXTURE.read_text(encoding="utf-8"),
                        xml_text=XML_FIXTURE.read_text(encoding="utf-8"),
                        brief="45 second proof of concept",
                        options=1,
                        output_dir=str(output_dir),
                        host="http://127.0.0.1:11435",
                    )

            self.assertEqual(exc.exception.error["code"], "TRANSCRIPT-TIMECODE-INVALID")
            errors = exc.exception.error.get("details", {}).get("errors", [])
            self.assertTrue(errors)
            self.assertEqual(errors[0]["field"], "timecode")
            if output_dir.exists():
                self.assertEqual(list(output_dir.iterdir()), [])

    def test_cli_rejects_fixtureed_invalid_xml(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "output"
            with patch("bitebuilder.resolve_host", return_value=("http://127.0.0.1:11435", ["qwen3:8b"])), \
                 patch("bitebuilder.ollama_generate", return_value=MOCK_RESPONSE), \
                 redirect_stdout(io.StringIO()), \
                 redirect_stderr(io.StringIO()):
                with self.assertRaises(BiteBuilderError) as exc:
                    run_pipeline(
                        transcript_text=TRANSCRIPT_FIXTURE.read_text(encoding="utf-8"),
                        xml_text=INVALID_XML_FIXTURE.read_text(encoding="utf-8"),
                        brief="45 second proof of concept",
                        options=1,
                        output_dir=str(output_dir),
                        host="http://127.0.0.1:11435",
                    )

            self.assertEqual(exc.exception.error["code"], "XML-MALFORMED")
            if output_dir.exists():
                self.assertEqual(list(output_dir.iterdir()), [])

    def test_generate_edit_options_retries_once_then_succeeds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "output"
            with patch("bitebuilder.ollama_generate", side_effect=[
                {"selection_status": "ok", "options": []},
                MOCK_RESPONSE,
            ]), \
                 patch("bitebuilder.ensure_ollama_ready", return_value=("http://127.0.0.1:11435", ["qwen3:8b"])), \
                 redirect_stdout(io.StringIO()), \
                 redirect_stderr(io.StringIO()):
                result = run_pipeline(
                    transcript_text=TRANSCRIPT_FIXTURE.read_text(encoding="utf-8"),
                    xml_text=XML_FIXTURE.read_text(encoding="utf-8"),
                    brief="45 second proof of concept",
                    options=2,
                    output_dir=str(output_dir),
                )

            self.assertEqual(output_dir.exists(), True)
            generated = sorted(output_dir.glob("*.xml"))
            self.assertEqual([path.name for path in generated], [
                "Margin_Story.xml",
                "Proof_Points.xml",
            ])
            self.assertTrue(result["used_retry"])
            self.assertEqual(result["selection_retry"].get("attempted"), True)
            self.assertTrue(result["selection_retry"].get("errors"))

            debug_response = json.loads((output_dir / "_llm_response.json").read_text())
            self.assertEqual(len(debug_response["options"]), 2)

    def test_run_pipeline_retries_fail_and_skips_xml_generation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "output"
            bad_response = {"selection_status": "ok", "options": []}
            with patch("bitebuilder.ollama_generate", return_value=bad_response), \
                 patch("bitebuilder.ensure_ollama_ready", return_value=("http://127.0.0.1:11435", ["qwen3:8b"])), \
                 redirect_stdout(io.StringIO()), \
                 redirect_stderr(io.StringIO()):
                with self.assertRaises(BiteBuilderError) as exc:
                    run_pipeline(
                        transcript_text=TRANSCRIPT_FIXTURE.read_text(encoding="utf-8"),
                        xml_text=XML_FIXTURE.read_text(encoding="utf-8"),
                        brief="45 second proof of concept",
                        options=2,
                        output_dir=str(output_dir),
                    )

            self.assertEqual(exc.exception.error["code"], "MODEL-RESPONSE-INVALID")
            if output_dir.exists():
                self.assertEqual(list(output_dir.iterdir()), [])

    def test_generate_selection_no_candidates_returns_noop_response(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "output"
            transcript_text = TRANSCRIPT_FIXTURE.read_text(encoding="utf-8")
            xml_text = XML_FIXTURE.read_text(encoding="utf-8")

            with patch("bitebuilder.build_candidate_shortlist", return_value=[]), \
                 patch("bitebuilder.ensure_ollama_ready", return_value=("http://127.0.0.1:11435", ["qwen3:8b"])), \
                 redirect_stdout(io.StringIO()), \
                 redirect_stderr(io.StringIO()):
                result = bitebuilder.run_pipeline(
                    transcript_text=transcript_text,
                    xml_text=xml_text,
                    brief="45 second proof of concept",
                    options=2,
                    output_dir=str(output_dir),
                    host="http://127.0.0.1:11435",
                )

            self.assertEqual(result["response"]["selection_status"], "no_candidates")
            self.assertEqual(result["response"]["options"], [])
            self.assertIn("no_candidate_reason", result["response"])
            self.assertEqual(result["output_files"], [])

    def test_run_pipeline_missing_transcript_file(self):
        with self.assertRaises(BiteBuilderError) as exc:
            run_pipeline(
                transcript_text="",
                xml_text="<xmeml version='4'></xmeml>",
                brief="45 second proof of concept",
            )
        self.assertEqual(exc.exception.error["code"], "TRANSCRIPT-TIMECODE-INVALID")

    def test_run_pipeline_malformed_brief_is_structured(self):
        with self.assertRaises(BiteBuilderError) as exc:
            run_pipeline(
                transcript_text=Path(TRANSCRIPT_FIXTURE).read_text(encoding="utf-8"),
                xml_text="<xmeml version='4'></xmeml>",
                brief="ok",
            )
        self.assertEqual(exc.exception.error["code"], "BRIEF-MALFORMED")
        self.assertIn("expected_input_format", exc.exception.error)
        self.assertIn("next_action", exc.exception.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
