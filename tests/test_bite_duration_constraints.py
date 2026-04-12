import copy
import json
import unittest

from generator.sequence_plan import build_sequence_plan
from generator.sequence_plan_constraints import evaluate_sequence_plan_constraints
from llm.sequence_plan_refinement import build_sequence_plan_refinement_prompt
from parser.transcript import TranscriptSegment


SEGMENTS = [
    TranscriptSegment("00:00:00:00", "00:00:10:00", "Speaker 1", "A long setup."),
    TranscriptSegment("00:00:10:00", "00:00:13:00", "Speaker 1", "A shorter replacement."),
    TranscriptSegment("00:00:13:00", "00:00:17:00", "Speaker 2", "A concise proof point."),
]


def plan_with_segments(indexes):
    return build_sequence_plan(
        transcript_segments=SEGMENTS,
        options=[
            {
                "option_id": "option-1",
                "bites": [
                    {
                        "bite_id": f"bite-{pos:03d}",
                        "segment_index": index,
                        "tc_in": SEGMENTS[index].tc_in,
                        "tc_out": SEGMENTS[index].tc_out,
                        "status": "selected",
                    }
                    for pos, index in enumerate(indexes, start=1)
                ],
            }
        ],
    )


class BiteDurationConstraintTests(unittest.TestCase):
    def test_constraints_pass_under_bite_and_total_limits(self):
        result = evaluate_sequence_plan_constraints(
            current_plan=plan_with_segments([1, 2]),
            timebase=24,
            ntsc=False,
            max_bite_duration_seconds=5,
            max_total_duration_seconds=8,
        )

        self.assertTrue(result.passes)
        self.assertEqual(result.selected_bite_count, 2)
        self.assertEqual(result.total_duration_seconds, 7.0)
        self.assertEqual(result.to_dict()["violations"], [])

    def test_overlong_bite_and_total_duration_are_reported(self):
        result = evaluate_sequence_plan_constraints(
            current_plan=plan_with_segments([0, 2]),
            timebase=24,
            ntsc=False,
            max_bite_duration_seconds=5,
            max_total_duration_seconds=12,
        )

        self.assertFalse(result.passes)
        codes = [violation.code for violation in result.violations]
        self.assertIn("bite_duration_exceeds_max", codes)
        self.assertIn("total_duration_exceeds_max", codes)

    def test_unchanged_selected_cuts_are_detected_ignoring_metadata(self):
        previous = plan_with_segments([0]).to_dict()
        current = copy.deepcopy(previous)
        current["options"][0]["bites"][0]["purpose"] = "new metadata only"

        result = evaluate_sequence_plan_constraints(
            current_plan=current,
            previous_plan=previous,
            transcript_segments=SEGMENTS,
            timebase=24,
            ntsc=False,
            require_changed_selected_cuts=True,
        )

        self.assertFalse(result.passes)
        self.assertFalse(result.changed_selected_cuts)
        self.assertEqual(result.violations[0].code, "selected_cuts_unchanged")

    def test_replacement_complete_segment_counts_as_changed(self):
        result = evaluate_sequence_plan_constraints(
            current_plan=plan_with_segments([1]),
            previous_plan=plan_with_segments([0]),
            timebase=24,
            ntsc=False,
            require_changed_selected_cuts=True,
        )

        self.assertTrue(result.passes)
        self.assertTrue(result.changed_selected_cuts)

    def test_mapping_input_requires_transcript_segments(self):
        with self.assertRaises(Exception):
            evaluate_sequence_plan_constraints(current_plan=plan_with_segments([0]).to_dict())

    def test_result_is_json_serializable_and_does_not_mutate_inputs(self):
        current = plan_with_segments([1]).to_dict()
        original = copy.deepcopy(current)

        result = evaluate_sequence_plan_constraints(
            current_plan=current,
            transcript_segments=SEGMENTS,
            timebase=24,
            ntsc=False,
        )

        json.dumps(result.to_dict())
        self.assertEqual(current, original)

    def test_refinement_prompt_includes_optional_duration_constraints(self):
        prompt = build_sequence_plan_refinement_prompt(
            current_plan=plan_with_segments([0]).to_dict(),
            transcript_segments=SEGMENTS,
            instruction="make it shorter",
            max_bite_duration_seconds=5,
            max_total_duration_seconds=8,
            require_changed_selected_cuts=True,
        )

        self.assertIn("at or below 5 seconds", prompt)
        self.assertIn("at or below 8 seconds", prompt)
        self.assertIn("must differ from the current selected cuts", prompt)


if __name__ == "__main__":
    unittest.main()
