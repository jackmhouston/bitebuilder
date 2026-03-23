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
from generator.xmeml import generate_sequence
from llm.prompts import build_editorial_direction_prompt, build_user_prompt, validate_llm_response
from parser.premiere_xml import parse_premiere_xml
from parser.transcript import format_for_llm, get_valid_timecodes, parse_transcript_file


FIXTURES_DIR = Path(__file__).parent / "fixtures"
TRANSCRIPT_FIXTURE = FIXTURES_DIR / "sample_transcript.txt"
XML_FIXTURE = FIXTURES_DIR / "sample_premiere.xml"

MOCK_RESPONSE = {
    "options": [
        {
            "name": "Margin Story",
            "description": "Frames the objection, proves the upside, and lands on a call to test.",
            "estimated_duration_seconds": 15,
            "cuts": [
                {
                    "order": 1,
                    "tc_in": "00:00:00:00",
                    "tc_out": "00:00:05:00",
                    "speaker": "Speaker 1",
                    "purpose": "HOOK",
                    "dialogue_summary": "States the common objection.",
                },
                {
                    "order": 2,
                    "tc_in": "00:00:05:00",
                    "tc_out": "00:00:10:00",
                    "speaker": "Speaker 1",
                    "purpose": "PROOF",
                    "dialogue_summary": "Explains the operating upside.",
                },
                {
                    "order": 3,
                    "tc_in": "00:00:20:00",
                    "tc_out": "00:00:25:00",
                    "speaker": "Speaker 2",
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
                    "tc_in": "00:00:10:00",
                    "tc_out": "00:00:15:00",
                    "speaker": "Speaker 2",
                    "purpose": "HOOK",
                    "dialogue_summary": "Introduces the product promise.",
                },
                {
                    "order": 2,
                    "tc_in": "00:00:15:00",
                    "tc_out": "00:00:20:00",
                    "speaker": "Speaker 1",
                    "purpose": "PIVOT",
                    "dialogue_summary": "Explains the narrative structure of the edit.",
                },
                {
                    "order": 3,
                    "tc_in": "00:00:20:00",
                    "tc_out": "00:00:25:00",
                    "speaker": "Speaker 2",
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
