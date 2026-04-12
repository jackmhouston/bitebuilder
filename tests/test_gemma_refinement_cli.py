import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bitebuilder
from tests.test_pipeline import TRANSCRIPT_TEXT, XML_TEXT
from tests.test_plan_to_xmeml import write_plan


class GemmaRefinementCliTests(unittest.TestCase):
    def _revised_plan(self, plan_path: Path) -> dict:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["options"][0]["bites"] = [
            {
                "bite_id": "bite-002",
                "segment_index": 1,
                "tc_in": "00:00:02:00",
                "tc_out": "00:00:04:00",
                "status": "selected",
                "replaces_bite_id": "bite-001",
            }
        ]
        plan["revision_log"] = [
            {"revision": 2, "action": "gemma_refinement", "instruction": "make it shorter"}
        ]
        return plan

    def _write_two_option_plan(self, plan_path: Path) -> dict:
        plan = write_plan(plan_path)
        second_option = json.loads(json.dumps(plan["options"][0]))
        second_option["option_id"] = "option-2"
        second_option["name"] = "Second Option"
        second_option["bites"] = [
            {
                "bite_id": "bite-101",
                "segment_index": 1,
                "tc_in": "00:00:02:00",
                "tc_out": "00:00:04:00",
                "status": "selected",
            }
        ]
        plan["options"].append(second_option)
        plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        return plan

    def test_refine_sequence_plan_writes_revision_and_renders_xml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "_sequence_plan.json"
            output_dir = tmp / "refined"
            original_plan = write_plan(plan_path)
            revised = self._revised_plan(plan_path)

            with patch.object(bitebuilder, "ollama_generate", return_value=revised) as generate:
                result = bitebuilder.refine_sequence_plan(
                    sequence_plan_text=plan_path.read_text(encoding="utf-8"),
                    transcript_text=TRANSCRIPT_TEXT,
                    xml_text=XML_TEXT,
                    output_dir=str(output_dir),
                    instruction="make it shorter",
                    sequence_plan_path=str(plan_path),
                    model="gemma3:4b",
                )

            generate.assert_called_once()
            self.assertEqual(json.loads(plan_path.read_text(encoding="utf-8")), original_plan)
            revision_path = Path(result["revision_path"])
            self.assertTrue(revision_path.exists())
            self.assertEqual(revision_path.name, "_sequence_plan_revision_2.json")
            self.assertTrue(Path(result["output_path"]).exists())
            self.assertTrue(Path(result["metadata_path"]).exists())
            self.assertEqual(result["cuts"], [{"tc_in": "00:00:02:00", "tc_out": "00:00:04:00"}])

    def test_refine_sequence_plan_rejects_invalid_model_output_before_rendering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "_sequence_plan.json"
            output_dir = tmp / "refined"
            write_plan(plan_path)
            revised = self._revised_plan(plan_path)
            revised["options"][0]["bites"][0]["tc_out"] = "00:00:05:00"

            with patch.object(bitebuilder, "ollama_generate", return_value=revised):
                with self.assertRaises(bitebuilder.BiteBuilderError):
                    bitebuilder.refine_sequence_plan(
                        sequence_plan_text=plan_path.read_text(encoding="utf-8"),
                        transcript_text=TRANSCRIPT_TEXT,
                        xml_text=XML_TEXT,
                        output_dir=str(output_dir),
                        instruction="make it shorter",
                    )

            self.assertFalse(output_dir.exists())

    def test_unknown_option_id_fails_before_model_call_or_writes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "_sequence_plan.json"
            output_dir = tmp / "refined"
            write_plan(plan_path)

            with patch.object(bitebuilder, "ollama_generate") as generate:
                with self.assertRaises(bitebuilder.BiteBuilderError):
                    bitebuilder.refine_sequence_plan(
                        sequence_plan_text=plan_path.read_text(encoding="utf-8"),
                        transcript_text=TRANSCRIPT_TEXT,
                        xml_text=XML_TEXT,
                        output_dir=str(output_dir),
                        instruction="make it shorter",
                        option_id="missing-option",
                    )

            generate.assert_not_called()
            self.assertFalse(output_dir.exists())

    def test_refined_output_missing_target_option_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "_sequence_plan.json"
            output_dir = tmp / "refined"
            self._write_two_option_plan(plan_path)
            revised = self._revised_plan(plan_path)
            revised["options"] = [revised["options"][0]]

            with patch.object(bitebuilder, "ollama_generate", return_value=revised):
                with self.assertRaises(bitebuilder.BiteBuilderError):
                    bitebuilder.refine_sequence_plan(
                        sequence_plan_text=plan_path.read_text(encoding="utf-8"),
                        transcript_text=TRANSCRIPT_TEXT,
                        xml_text=XML_TEXT,
                        output_dir=str(output_dir),
                        instruction="make option two shorter",
                        option_id="option-2",
                    )

            self.assertFalse(output_dir.exists())

    def test_refined_target_option_with_no_selected_bites_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "_sequence_plan.json"
            output_dir = tmp / "refined"
            write_plan(plan_path)
            revised = self._revised_plan(plan_path)
            revised["options"][0]["bites"][0]["status"] = "removed"

            with patch.object(bitebuilder, "ollama_generate", return_value=revised):
                with self.assertRaises(bitebuilder.BiteBuilderError):
                    bitebuilder.refine_sequence_plan(
                        sequence_plan_text=plan_path.read_text(encoding="utf-8"),
                        transcript_text=TRANSCRIPT_TEXT,
                        xml_text=XML_TEXT,
                        output_dir=str(output_dir),
                        instruction="remove everything",
                    )

            self.assertFalse(output_dir.exists())

    def test_cli_refine_mode_is_wired_to_helper(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "_sequence_plan.json"
            transcript_path = tmp / "transcript.txt"
            xml_path = tmp / "source.xml"
            output_dir = tmp / "refined"
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
                    "--refine-instruction",
                    "make it shorter",
                    "--timeout",
                    "1",
                    "--model",
                    "missing-model-for-test",
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("SEQUENCE-PLAN-REFINE-FAILED", completed.stderr)
            self.assertFalse(output_dir.exists())


    def test_constraint_retry_succeeds_after_unchanged_first_response(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "_sequence_plan.json"
            output_dir = tmp / "refined"
            write_plan(plan_path)
            unchanged = json.loads(plan_path.read_text(encoding="utf-8"))
            revised = self._revised_plan(plan_path)

            with patch.object(bitebuilder, "ollama_generate", side_effect=[unchanged, revised]) as generate:
                result = bitebuilder.refine_sequence_plan(
                    sequence_plan_text=plan_path.read_text(encoding="utf-8"),
                    transcript_text=TRANSCRIPT_TEXT,
                    xml_text=XML_TEXT,
                    output_dir=str(output_dir),
                    instruction="make it shorter",
                    require_changed_selected_cuts=True,
                    refinement_retries=1,
                )

            self.assertEqual(generate.call_count, 2)
            retry_prompt = generate.call_args_list[1].kwargs["user_prompt"]
            self.assertIn("selected_cuts_unchanged", retry_prompt)
            self.assertTrue(Path(result["revision_path"]).exists())
            self.assertTrue(Path(result["output_path"]).exists())

    def test_constraint_failure_with_no_retries_writes_nothing_and_reports_details(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "_sequence_plan.json"
            output_dir = tmp / "refined"
            write_plan(plan_path)
            unchanged = json.loads(plan_path.read_text(encoding="utf-8"))

            with patch.object(bitebuilder, "ollama_generate", return_value=unchanged):
                with self.assertRaises(bitebuilder.BiteBuilderError) as ctx:
                    bitebuilder.refine_sequence_plan(
                        sequence_plan_text=plan_path.read_text(encoding="utf-8"),
                        transcript_text=TRANSCRIPT_TEXT,
                        xml_text=XML_TEXT,
                        output_dir=str(output_dir),
                        instruction="make it shorter",
                        require_changed_selected_cuts=True,
                        refinement_retries=0,
                    )

            self.assertEqual(ctx.exception.error["code"], "SEQUENCE-PLAN-REFINE-CONSTRAINTS-FAILED")
            self.assertIn("selected_cuts_unchanged", json.dumps(ctx.exception.error["details"]))
            self.assertFalse(output_dir.exists())

    def test_no_constraints_do_not_trigger_editorial_retry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "_sequence_plan.json"
            output_dir = tmp / "refined"
            write_plan(plan_path)
            unchanged = json.loads(plan_path.read_text(encoding="utf-8"))

            with patch.object(bitebuilder, "ollama_generate", return_value=unchanged) as generate:
                result = bitebuilder.refine_sequence_plan(
                    sequence_plan_text=plan_path.read_text(encoding="utf-8"),
                    transcript_text=TRANSCRIPT_TEXT,
                    xml_text=XML_TEXT,
                    output_dir=str(output_dir),
                    instruction="make it shorter",
                )

            self.assertEqual(generate.call_count, 1)
            self.assertTrue(Path(result["output_path"]).exists())

    def test_overlong_bite_constraint_uses_source_timing_and_fails_before_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "_sequence_plan.json"
            output_dir = tmp / "refined"
            write_plan(plan_path)
            unchanged = json.loads(plan_path.read_text(encoding="utf-8"))

            with patch.object(bitebuilder, "ollama_generate", return_value=unchanged):
                with self.assertRaises(bitebuilder.BiteBuilderError) as ctx:
                    bitebuilder.refine_sequence_plan(
                        sequence_plan_text=plan_path.read_text(encoding="utf-8"),
                        transcript_text=TRANSCRIPT_TEXT,
                        xml_text=XML_TEXT,
                        output_dir=str(output_dir),
                        instruction="make it shorter",
                        max_bite_duration_seconds=1,
                        refinement_retries=0,
                    )

            self.assertIn("bite_duration_exceeds_max", json.dumps(ctx.exception.error["details"]))
            self.assertFalse(output_dir.exists())


if __name__ == "__main__":
    unittest.main()
