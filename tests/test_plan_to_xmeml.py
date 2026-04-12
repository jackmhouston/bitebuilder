import json
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from bitebuilder import BiteBuilderError, render_sequence_plan
from generator.sequence_plan import build_sequence_plan
from parser.transcript import TranscriptSegment
from tests.test_pipeline import TRANSCRIPT_TEXT, XML_TEXT


SEGMENTS = [
    TranscriptSegment("00:00:00:00", "00:00:02:00", "Speaker 1", "Hello there."),
    TranscriptSegment("00:00:02:00", "00:00:04:00", "Speaker 2", "General Kenobi."),
]


def write_plan(path: Path, *, option_id="option-1", option_name="Named Plan") -> dict:
    plan = build_sequence_plan(
        transcript_segments=SEGMENTS,
        project_context="A greeting exchange.",
        goal="Render the selected greeting.",
        options=[
            {
                "option_id": option_id,
                "name": option_name,
                "bites": [
                    {
                        "segment_index": 0,
                        "tc_in": "00:00:00:00",
                        "tc_out": "00:00:02:00",
                        "status": "selected",
                    },
                    {
                        "segment_index": 1,
                        "tc_in": "00:00:02:00",
                        "tc_out": "00:00:04:00",
                        "status": "removed",
                    },
                ],
            }
        ],
    ).to_dict()
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return plan


class PlanToXmemlTests(unittest.TestCase):
    def test_helper_renders_selected_bites_and_metadata_without_mutating_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "_sequence_plan.json"
            transcript_path = tmp / "transcript.txt"
            xml_path = tmp / "source.xml"
            output_dir = tmp / "rendered"
            original_plan = write_plan(plan_path)
            transcript_path.write_text(TRANSCRIPT_TEXT, encoding="utf-8")
            xml_path.write_text(XML_TEXT, encoding="utf-8")

            result = render_sequence_plan(
                sequence_plan_text=plan_path.read_text(encoding="utf-8"),
                transcript_text=TRANSCRIPT_TEXT,
                xml_text=XML_TEXT,
                output_dir=str(output_dir),
                sequence_plan_path=str(plan_path),
            )

            rendered_xml = Path(result["output_path"])
            metadata_path = Path(result["metadata_path"])
            self.assertTrue(rendered_xml.exists())
            self.assertEqual(rendered_xml.name, "Named_Plan.xml")
            self.assertTrue(metadata_path.exists())
            self.assertEqual(json.loads(plan_path.read_text(encoding="utf-8")), original_plan)

            root = ET.fromstring(rendered_xml.read_text(encoding="utf-8"))
            clipitems = list(root.iter("clipitem"))
            self.assertEqual(len(clipitems), 3)
            self.assertTrue(all(clip.findtext("in") == "0" for clip in clipitems))
            self.assertTrue(all(clip.findtext("out") == "48" for clip in clipitems))

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["option_id"], "option-1")
            self.assertEqual(metadata["cut_count"], 1)
            self.assertEqual(os.path.realpath(metadata["sequence_plan_source"]), os.path.realpath(plan_path))

    def test_cli_renders_without_ollama_and_defaults_to_first_option(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "_sequence_plan.json"
            transcript_path = tmp / "transcript.txt"
            xml_path = tmp / "source.xml"
            output_dir = tmp / "rendered"
            write_plan(plan_path)
            transcript_path.write_text(TRANSCRIPT_TEXT, encoding="utf-8")
            xml_path.write_text(XML_TEXT, encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "bitebuilder.py",
                    "--sequence-plan",
                    str(plan_path),
                    "--transcript",
                    str(transcript_path),
                    "--xml",
                    str(xml_path),
                    "--output",
                    str(output_dir),
                ],
                cwd=Path(__file__).resolve().parents[1],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn("Rendered sequence plan option: option-1", completed.stdout)
            self.assertTrue((output_dir / "Named_Plan.xml").exists())
            self.assertTrue((output_dir / "_sequence_plan_render.json").exists())

    def test_option_name_falls_back_to_option_id_for_filename(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "_sequence_plan.json"
            write_plan(plan_path, option_id="option-fallback", option_name=None)
            result = render_sequence_plan(
                sequence_plan_text=plan_path.read_text(encoding="utf-8"),
                transcript_text=TRANSCRIPT_TEXT,
                xml_text=XML_TEXT,
                output_dir=str(tmp / "rendered"),
            )
            self.assertEqual(Path(result["output_path"]).name, "option-fallback.xml")

    def test_unknown_option_id_fails_before_writing_xml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "_sequence_plan.json"
            output_dir = tmp / "rendered"
            write_plan(plan_path)

            transcript_path = tmp / "transcript.txt"
            xml_path = tmp / "source.xml"
            transcript_path.write_text(TRANSCRIPT_TEXT, encoding="utf-8")
            xml_path.write_text(XML_TEXT, encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "bitebuilder.py",
                    "--sequence-plan",
                    str(plan_path),
                    "--transcript",
                    str(transcript_path),
                    "--xml",
                    str(xml_path),
                    "--output",
                    str(output_dir),
                    "--option-id",
                    "missing-option",
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("SEQUENCE-PLAN-INVALID", completed.stderr)
            self.assertFalse(output_dir.exists())

    def test_invalid_timecode_mismatch_fails_before_writing_xml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "_sequence_plan.json"
            output_dir = tmp / "rendered"
            plan = write_plan(plan_path)
            plan["options"][0]["bites"][0]["tc_out"] = "00:00:03:00"
            plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

            with self.assertRaises(BiteBuilderError):
                render_sequence_plan(
                    sequence_plan_text=plan_path.read_text(encoding="utf-8"),
                    transcript_text=TRANSCRIPT_TEXT,
                    xml_text=XML_TEXT,
                    output_dir=str(output_dir),
                )
            self.assertFalse(output_dir.exists())


if __name__ == "__main__":
    unittest.main()
