import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bitebuilder
from generator.sequence_plan import SequencePlan


TRANSCRIPT_TEXT = """00:00:00:00 - 00:00:02:00
Speaker 1
Hello there.

00:00:02:00 - 00:00:04:00
Speaker 2
General Kenobi.
"""

XML_TEXT = """<?xml version="1.0" encoding="UTF-8"?>
<xmeml version="4">
  <sequence>
    <name>Example Sequence</name>
    <rate>
      <timebase>24</timebase>
      <ntsc>FALSE</ntsc>
    </rate>
    <media>
      <video>
        <format>
          <samplecharacteristics>
            <width>1920</width>
            <height>1080</height>
          </samplecharacteristics>
        </format>
      </video>
      <audio>
        <format>
          <samplecharacteristics>
            <depth>24</depth>
            <samplerate>48000</samplerate>
          </samplecharacteristics>
        </format>
      </audio>
    </media>
  </sequence>
  <file id="file-1">
    <name>clip.mov</name>
    <pathurl>file:///Volumes/Test/clip.mov</pathurl>
    <rate>
      <timebase>24</timebase>
      <ntsc>FALSE</ntsc>
    </rate>
    <duration>240</duration>
    <media>
      <video>
        <samplecharacteristics>
          <width>1920</width>
          <height>1080</height>
        </samplecharacteristics>
      </video>
      <audio>
        <samplecharacteristics>
          <depth>24</depth>
          <samplerate>48000</samplerate>
        </samplecharacteristics>
        <channelcount>2</channelcount>
      </audio>
    </media>
  </file>
</xmeml>
"""


class PipelineTests(unittest.TestCase):
    def test_run_pipeline_writes_xml_and_debug_artifacts(self):
        mocked_response = {
            "selection_status": "ok",
            "options": [
                {
                    "name": "Option 1",
                    "description": "A short cut.",
                    "estimated_duration_seconds": 2.0,
                    "cuts": [
                        {
                            "segment_index": 0,
                            "tc_in": "00:00:00:00",
                            "tc_out": "00:00:02:00",
                            "confidence": 0.95,
                            "purpose": "hook",
                            "dialogue_summary": "Hello there.",
                        }
                    ],
                },
                {
                    "name": "Option 2",
                    "description": "A second short cut.",
                    "estimated_duration_seconds": 2.0,
                    "cuts": [
                        {
                            "segment_index": 1,
                            "tc_in": "00:00:02:00",
                            "tc_out": "00:00:04:00",
                            "confidence": 0.88,
                            "purpose": "close",
                            "dialogue_summary": "General Kenobi.",
                        }
                    ],
                }
            ],
        }
        mocked_debug = {
            "editorial_direction_prompt": "",
            "editorial_direction": "",
            "editorial_direction_raw": "",
            "accepted_plan": {},
            "accepted_plan_text": "",
            "candidate_shortlist": [],
            "generation_prompt": "prompt",
            "attempts": [],
            "selection_retry": {"attempted": False, "errors": [], "parse_or_validation_error": False},
            "selection_warnings": [],
            "used_fallback": False,
            "run_metadata": {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(bitebuilder, "ensure_ollama_ready", return_value=("http://127.0.0.1:11434", ["qwen3:8b"])):
                with patch.object(
                    bitebuilder,
                    "generate_edit_options",
                    return_value=(mocked_response, [], False, {"00:00:00:00", "00:00:02:00"}, {"minimum_seconds": None, "maximum_seconds": None}, mocked_debug),
                ):
                    result = bitebuilder.run_pipeline(
                        transcript_text=TRANSCRIPT_TEXT,
                        xml_text=XML_TEXT,
                        brief="Create a short highlight cut with a strong opening.",
                        project_context="Interview footage about a memorable greeting.",
                        output_dir=tmpdir,
                    )

            self.assertEqual(len(result["output_files"]), 2)
            self.assertTrue(Path(result["debug_path"]).exists())
            self.assertTrue(Path(tmpdir, result["output_files"][0]["filename"]).exists())
            self.assertTrue(Path(tmpdir, result["output_files"][1]["filename"]).exists())
            self.assertIn("run_metadata", result)
            self.assertEqual(result["response"]["selection_status"], "ok")
            self.assertTrue(Path(result["sequence_plan_path"]).exists())
            self.assertEqual(result["debug_files"]["sequence_plan"], result["sequence_plan_path"])
            self.assertEqual(result["output_files"][0]["sequence_plan_option_id"], "option-1")
            self.assertEqual(result["output_files"][1]["sequence_plan_option_id"], "option-2")

            sequence_plan = json.loads(Path(result["sequence_plan_path"]).read_text())
            plan = SequencePlan.from_dict(sequence_plan, transcript_segments=result["segments"])
            self.assertEqual(
                sequence_plan["project_context"],
                "Interview footage about a memorable greeting.",
            )
            self.assertEqual(sequence_plan["goal"], "Create a short highlight cut with a strong opening.")
            self.assertEqual(sequence_plan["options"][0]["option_id"], "option-1")
            self.assertEqual(sequence_plan["options"][1]["option_id"], "option-2")
            for index, option_id in enumerate(["option-1", "option-2"]):
                self.assertEqual(
                    plan.to_cuts(option_id),
                    [
                        {"tc_in": cut["tc_in"], "tc_out": cut["tc_out"]}
                        for cut in result["response"]["options"][index]["cuts"]
                    ],
                )

    def test_run_pipeline_does_not_write_sequence_plan_for_no_candidates(self):
        mocked_response = {
            "selection_status": "no_candidates",
            "options": [],
            "no_candidate_reason": "Nothing matched the brief.",
        }
        mocked_debug = {
            "editorial_direction_prompt": "",
            "editorial_direction": "",
            "editorial_direction_raw": "",
            "accepted_plan": {},
            "accepted_plan_text": "",
            "candidate_shortlist": [],
            "generation_prompt": "prompt",
            "attempts": [],
            "selection_retry": {"attempted": False, "errors": [], "parse_or_validation_error": False},
            "selection_warnings": [],
            "used_fallback": True,
            "run_metadata": {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(bitebuilder, "ensure_ollama_ready", return_value=("http://127.0.0.1:11434", ["qwen3:8b"])):
                with patch.object(
                    bitebuilder,
                    "generate_edit_options",
                    return_value=(mocked_response, [], False, {"00:00:00:00", "00:00:02:00"}, {"minimum_seconds": None, "maximum_seconds": None}, mocked_debug),
                ):
                    result = bitebuilder.run_pipeline(
                        transcript_text=TRANSCRIPT_TEXT,
                        xml_text=XML_TEXT,
                        brief="Create a short highlight cut with a strong opening.",
                        output_dir=tmpdir,
                    )

            self.assertEqual(result["output_files"], [])
            self.assertIsNone(result["sequence_plan_path"])
            self.assertNotIn("sequence_plan", result["debug_files"])
            self.assertFalse(Path(tmpdir, "_sequence_plan.json").exists())


if __name__ == "__main__":
    unittest.main()
