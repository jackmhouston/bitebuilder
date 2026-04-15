import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bitebuilder
from generator.sequence_plan import SequencePlan
from parser.premiere_xml import SourceMetadata
from parser.transcript import TranscriptSegment


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


def source_metadata(duration=240):
    return SourceMetadata(
        source_name="clip.mov",
        source_path="/Volumes/Test/clip.mov",
        pathurl="file:///Volumes/Test/clip.mov",
        timebase=24,
        ntsc=False,
        duration=duration,
        width=1920,
        height=1080,
        audio_depth=24,
        audio_samplerate=48000,
        audio_channels=2,
    )


class PipelineTests(unittest.TestCase):
    def test_candidate_scoring_matches_generic_brief_keywords(self):
        segments = [
            TranscriptSegment(
                "00:00:00:00",
                "00:00:06:00",
                "Speaker 1",
                "The handoff became clear, and editors made decisions in minutes.",
            ),
            TranscriptSegment(
                "00:00:06:00",
                "00:00:12:00",
                "Speaker 2",
                "The battery microgrid operated near the old utility meter.",
            ),
        ]

        shortlist = bitebuilder.build_candidate_shortlist(
            segments=segments,
            source=source_metadata(),
            brief="A proof cut about handoff clarity and decision speed.",
            limit=2,
        )

        self.assertEqual(shortlist[0]["segment_index"], 0)
        self.assertIn("brief keyword match", shortlist[0]["reasons"])
        self.assertNotIn("finance framing", shortlist[0]["reasons"])

    def test_speaker_balance_does_not_assume_speaker_one_roles(self):
        segments = [
            TranscriptSegment(
                "00:00:00:00",
                "00:00:05:00",
                "Speaker 1",
                "This line has the same clear proof and complete thought.",
            ),
            TranscriptSegment(
                "00:00:05:00",
                "00:00:10:00",
                "Speaker 2",
                "This line has the same clear proof and complete thought.",
            ),
        ]

        shortlist = bitebuilder.build_candidate_shortlist(
            segments=segments,
            source=source_metadata(),
            brief="Clear proof with a complete thought.",
            speaker_balance="worker",
            limit=2,
        )
        by_index = {item["segment_index"]: item for item in shortlist}

        self.assertEqual(by_index[0]["score"], by_index[1]["score"])
        self.assertNotIn("speaker bias: worker", by_index[1]["reasons"])

    def test_speaker_mix_noops_without_explicit_variety_request(self):
        response = {"selection_status": "ok", "options": []}

        updated, notes = bitebuilder.enforce_requested_speaker_mix(
            response=response,
            candidates=[],
            source=source_metadata(),
            editorial_text="clear proof with a complete thought",
            target_duration_range=None,
        )

        self.assertIs(updated, response)
        self.assertEqual(notes, [])

    def test_fallback_speaker_variety_does_not_assume_speaker_two(self):
        candidates = [
            {
                "segment_index": 0,
                "tc_in": "00:00:00:00",
                "tc_out": "00:00:05:00",
                "speaker": "Alex",
                "text": "This is a clear setup with useful context.",
                "duration_seconds": 5,
                "score": 10,
                "roles": ["CONTEXT"],
            },
            {
                "segment_index": 1,
                "tc_in": "00:00:05:00",
                "tc_out": "00:00:10:00",
                "speaker": "Jordan",
                "text": "This is a proof point from another perspective.",
                "duration_seconds": 5,
                "score": 9,
                "roles": ["PROOF"],
            },
        ]

        response = bitebuilder.build_fallback_response(
            candidates=candidates,
            source=source_metadata(),
            num_options=1,
            target_duration_range=(8, 12),
            editorial_text="include another voice for speaker variety",
        )

        speakers = {cut["speaker"] for cut in response["options"][0]["cuts"]}
        self.assertEqual(speakers, {"Alex", "Jordan"})

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
            self.assertTrue(Path(result["debug_files"]["sequence_plan_summary"]).exists())
            summary_text = Path(result["debug_files"]["sequence_plan_summary"]).read_text()
            self.assertIn("Option option-1", summary_text)
            self.assertIn("00:00:00:00 - 00:00:02:00", summary_text)
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


    def test_repair_response_segment_indexes_handles_missing_index_from_exact_timecodes(self):
        repaired = bitebuilder.repair_response_segment_indexes_from_timecodes(
            {
                "selection_status": "ok",
                "options": [
                    {
                        "cuts": [
                            {"tc_in": "00:00:02:00", "tc_out": "00:00:04:00", "confidence": 0.8}
                        ]
                    }
                ],
            },
            bitebuilder.parse_transcript(TRANSCRIPT_TEXT, strict=True),
        )

        self.assertEqual(repaired["options"][0]["cuts"][0]["segment_index"], 1)

    def test_repair_response_segment_indexes_leaves_invented_timecodes_unrepaired(self):
        repaired = bitebuilder.repair_response_segment_indexes_from_timecodes(
            {
                "selection_status": "ok",
                "options": [
                    {
                        "cuts": [
                            {"tc_in": "00:00:00:01", "tc_out": "00:00:02:01", "confidence": 0.8}
                        ]
                    }
                ],
            },
            bitebuilder.parse_transcript(TRANSCRIPT_TEXT, strict=True),
        )

        self.assertNotIn("segment_index", repaired["options"][0]["cuts"][0])

    def test_run_pipeline_repairs_wrong_segment_index_from_exact_timecodes(self):
        mocked_response = {
            "selection_status": "ok",
            "options": [
                {
                    "name": "Option 1",
                    "description": "A repaired cut.",
                    "estimated_duration_seconds": 2.0,
                    "cuts": [
                        {
                            "segment_index": 99,
                            "tc_in": "00:00:00:00",
                            "tc_out": "00:00:02:00",
                            "confidence": 0.9,
                            "purpose": "hook",
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
                        output_dir=tmpdir,
                    )

            sequence_plan = json.loads(Path(result["sequence_plan_path"]).read_text())
            self.assertEqual(result["response"]["options"][0]["cuts"][0]["segment_index"], 0)
            self.assertEqual(sequence_plan["options"][0]["bites"][0]["segment_index"], 0)
            self.assertTrue(Path(tmpdir, result["output_files"][0]["filename"]).exists())

    def test_run_pipeline_uses_valid_segment_index_over_bad_model_timecodes(self):
        mocked_response = {
            "selection_status": "ok",
            "options": [
                {
                    "name": "Option 1",
                    "description": "A grounded cut.",
                    "estimated_duration_seconds": 2.0,
                    "cuts": [
                        {
                            "segment_index": 0,
                            "tc_in": "00:00:00:01",
                            "tc_out": "00:00:02:01",
                            "confidence": 0.9,
                            "purpose": "hook",
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
                        output_dir=tmpdir,
                    )

            cut = result["response"]["options"][0]["cuts"][0]
            self.assertEqual(cut["segment_index"], 0)
            self.assertEqual(cut["tc_in"], "00:00:00:00")
            self.assertEqual(cut["tc_out"], "00:00:02:00")


    def test_run_pipeline_rejects_invented_timecode_even_with_segment_index(self):
        mocked_response = {
            "selection_status": "ok",
            "options": [
                {
                    "name": "Bad Option",
                    "cuts": [
                        {
                            "segment_index": 0,
                            "tc_in": "00:00:00:01",
                            "tc_out": "00:00:02:01",
                            "confidence": 0.9,
                            "purpose": "hook",
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
                    return_value=(mocked_response, ["validation failed"], False, {"00:00:00:00", "00:00:02:00"}, {"minimum_seconds": None, "maximum_seconds": None}, mocked_debug),
                ):
                    with self.assertRaises(bitebuilder.BiteBuilderError):
                        bitebuilder.run_pipeline(
                            transcript_text=TRANSCRIPT_TEXT,
                            xml_text=XML_TEXT,
                            brief="Create a short highlight cut with a strong opening.",
                            output_dir=tmpdir,
                        )
            self.assertFalse(Path(tmpdir, "_sequence_plan.json").exists())


if __name__ == "__main__":
    unittest.main()
