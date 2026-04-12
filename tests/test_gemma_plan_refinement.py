import copy
import json
import unittest

from generator.sequence_plan import build_sequence_plan
from llm.sequence_plan_refinement import (
    SequencePlanRefinementError,
    build_sequence_plan_refinement_prompt,
    validate_refined_sequence_plan,
)
from parser.transcript import TranscriptSegment


SEGMENTS = [
    TranscriptSegment("00:00:00:00", "00:00:10:00", "Speaker 1", "A long setup about the company."),
    TranscriptSegment("00:00:10:00", "00:00:13:00", "Speaker 1", "A shorter hook."),
    TranscriptSegment("00:00:13:00", "00:00:17:00", "Speaker 2", "A concise proof point."),
]


def base_plan():
    return build_sequence_plan(
        transcript_segments=SEGMENTS,
        project_context="Interview about a solar company.",
        goal="Make a concise positive narrative.",
        options=[
            {
                "option_id": "option-1",
                "name": "Primary",
                "bites": [
                    {"bite_id": "bite-001", "segment_index": 0, "tc_in": "00:00:00:00", "tc_out": "00:00:10:00"},
                ],
            },
            {
                "option_id": "option-2",
                "name": "Alternate",
                "bites": [
                    {"bite_id": "bite-002", "segment_index": 2, "tc_in": "00:00:13:00", "tc_out": "00:00:17:00"},
                ],
            },
        ],
    ).to_dict()


def refined_shorter_plan():
    plan = base_plan()
    plan["options"][0]["bites"] = [
        {
            "bite_id": "bite-003",
            "segment_index": 1,
            "tc_in": "00:00:10:00",
            "tc_out": "00:00:13:00",
            "status": "selected",
            "purpose": "shorter hook",
            "replaces_bite_id": "bite-001",
        }
    ]
    plan["revision_log"] = [
        {
            "revision": 2,
            "action": "gemma_refinement",
            "instruction": "make bites shorter",
            "summary": "Replaced the long setup with a shorter complete segment.",
        }
    ]
    return plan


class GemmaPlanRefinementTests(unittest.TestCase):
    def test_prompt_contains_instruction_plan_segments_and_strict_rules(self):
        prompt = build_sequence_plan_refinement_prompt(
            current_plan=base_plan(),
            transcript_segments=SEGMENTS,
            instruction="make bites shorter",
            target_option_id="option-1",
        )

        self.assertIn("make bites shorter", prompt)
        self.assertIn("option-1", prompt)
        self.assertIn('"schema_version": "sequence_plan.v1"', prompt)
        self.assertIn("Return ONLY valid JSON", prompt)
        self.assertIn("Do not return Markdown fences", prompt)
        self.assertIn("Do not trim, split, or alter timecodes", prompt)
        self.assertIn("replace long bites with shorter complete transcript segments", prompt)
        self.assertIn("[0] 00:00:00:00 - 00:00:10:00", prompt)

    def test_valid_mocked_refinement_validates_and_preserves_unrelated_option(self):
        plan = validate_refined_sequence_plan(refined_shorter_plan(), transcript_segments=SEGMENTS)

        self.assertEqual(plan.to_cuts("option-1"), [{"tc_in": "00:00:10:00", "tc_out": "00:00:13:00"}])
        self.assertEqual(plan.to_cuts("option-2"), [{"tc_in": "00:00:13:00", "tc_out": "00:00:17:00"}])
        self.assertEqual(plan.options[0].bites[0].replaces_bite_id, "bite-001")

    def test_raw_json_refinement_validates(self):
        plan = validate_refined_sequence_plan(json.dumps(refined_shorter_plan()), transcript_segments=SEGMENTS)
        self.assertEqual(plan.options[0].option_id, "option-1")

    def test_invented_timecode_is_rejected(self):
        plan = refined_shorter_plan()
        plan["options"][0]["bites"][0]["tc_out"] = "00:00:12:12"

        with self.assertRaises(SequencePlanRefinementError):
            validate_refined_sequence_plan(plan, transcript_segments=SEGMENTS)

    def test_unknown_status_is_rejected(self):
        plan = refined_shorter_plan()
        plan["options"][0]["bites"][0]["status"] = "candidate"

        with self.assertRaises(SequencePlanRefinementError):
            validate_refined_sequence_plan(plan, transcript_segments=SEGMENTS)

    def test_missing_or_wrong_schema_version_is_rejected(self):
        plan = refined_shorter_plan()
        plan.pop("schema_version")
        with self.assertRaises(SequencePlanRefinementError):
            validate_refined_sequence_plan(plan, transcript_segments=SEGMENTS)

        plan = refined_shorter_plan()
        plan["schema_version"] = "sequence_plan.v0"
        with self.assertRaises(SequencePlanRefinementError):
            validate_refined_sequence_plan(plan, transcript_segments=SEGMENTS)

    def test_non_object_empty_options_and_markdown_wrapped_output_are_rejected(self):
        with self.assertRaises(SequencePlanRefinementError):
            validate_refined_sequence_plan("[]", transcript_segments=SEGMENTS)
        with self.assertRaises(SequencePlanRefinementError):
            validate_refined_sequence_plan({"schema_version": "sequence_plan.v1", "options": []}, transcript_segments=SEGMENTS)
        with self.assertRaises(SequencePlanRefinementError):
            validate_refined_sequence_plan("```json\n{}\n```", transcript_segments=SEGMENTS)

    def test_input_plan_dict_is_not_mutated(self):
        plan = refined_shorter_plan()
        original = copy.deepcopy(plan)

        validate_refined_sequence_plan(plan, transcript_segments=SEGMENTS)

        self.assertEqual(plan, original)


if __name__ == "__main__":
    unittest.main()
