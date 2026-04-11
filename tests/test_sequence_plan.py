import json
import unittest

from generator.sequence_plan import (
    REMOVED_STATUS,
    SCHEMA_VERSION,
    SELECTED_STATUS,
    SequencePlan,
    SequencePlanBite,
    SequencePlanValidationError,
    build_sequence_plan,
)
from parser.transcript import TranscriptSegment


SEGMENTS = [
    TranscriptSegment(
        tc_in="00:00:00:00",
        tc_out="00:00:03:00",
        speaker="Speaker 1",
        text="Opening idea about the company.",
    ),
    TranscriptSegment(
        tc_in="00:00:03:00",
        tc_out="00:00:07:12",
        speaker="Speaker 2",
        text="Follow-up that provides context.",
    ),
    TranscriptSegment(
        tc_in="00:00:07:12",
        tc_out="00:00:11:00",
        speaker="Speaker 1",
        text="Closing insight with a strong takeaway.",
    ),
]


class SequencePlanTests(unittest.TestCase):
    def _build_valid_plan(self):
        return build_sequence_plan(
            project_context="Interview footage about a solar panel company.",
            goal="Create an insightful narrative.",
            speaker_names={"Speaker 1": "CEO"},
            source={
                "transcript": {"sha256": "abc", "segment_count": len(SEGMENTS)},
                "premiere_xml": {"sha256": "def", "source_name": "interview.mov"},
            },
            revision_log=[{"revision": 1, "action": "llm_first_pass"}],
            transcript_segments=SEGMENTS,
            options=[
                {
                    "option_id": "option-1",
                    "name": "CEO narrative",
                    "estimated_duration_seconds": 7,
                    "bites": [
                        {
                            "segment_index": 0,
                            "tc_in": "00:00:00:00",
                            "tc_out": "00:00:03:00",
                            "speaker": "Speaker 1",
                            "text": "Opening idea about the company.",
                            "purpose": "opening hook",
                            "confidence": 0.91,
                            "rationale": "Starts with a clear premise.",
                            "source_action": "llm_first_pass",
                        },
                        {
                            "bite_id": "custom-bite-id",
                            "segment_index": 1,
                            "tc_in": "00:00:03:00",
                            "tc_out": "00:00:07:12",
                            "speaker": "Speaker 2",
                            "dialogue_summary": "Context setup.",
                            "purpose": "context",
                            "status": REMOVED_STATUS,
                        },
                        {
                            "segment_index": 2,
                            "tc_in": "00:00:07:12",
                            "tc_out": "00:00:11:00",
                            "speaker": "Speaker 1",
                            "text": "Closing insight with a strong takeaway.",
                            "status": SELECTED_STATUS,
                            "replaces_bite_id": "custom-bite-id",
                        },
                    ],
                }
            ],
        )

    def test_valid_plan_constructs_with_zero_based_segment_references(self):
        plan = self._build_valid_plan()

        self.assertEqual(plan.schema_version, SCHEMA_VERSION)
        self.assertEqual(plan.options[0].bites[0].segment_index, 0)
        self.assertEqual(plan.options[0].bites[0].bite_id, "bite-001")
        self.assertEqual(plan.options[0].bites[1].bite_id, "custom-bite-id")
        self.assertEqual(plan.options[0].bites[2].bite_id, "bite-003")
        self.assertEqual(plan.options[0].bites[2].replaces_bite_id, "custom-bite-id")

    def test_invalid_segment_index_is_rejected(self):
        with self.assertRaisesRegex(SequencePlanValidationError, "outside transcript bounds"):
            build_sequence_plan(
                transcript_segments=SEGMENTS,
                options=[{"bites": [{"segment_index": 3, "tc_in": "00:00:11:00", "tc_out": "00:00:12:00"}]}],
            )

    def test_mismatched_timecode_pair_is_rejected(self):
        with self.assertRaisesRegex(SequencePlanValidationError, "do not match"):
            build_sequence_plan(
                transcript_segments=SEGMENTS,
                options=[{"bites": [{"segment_index": 1, "tc_in": "00:00:03:00", "tc_out": "00:00:08:00"}]}],
            )

    def test_unknown_bite_status_is_rejected(self):
        with self.assertRaisesRegex(SequencePlanValidationError, "Unknown bite status"):
            SequencePlanBite(
                bite_id="bite-001",
                segment_index=0,
                tc_in="00:00:00:00",
                tc_out="00:00:03:00",
                status="candidate",
            )

    def test_removed_bites_are_filtered_from_xmeml_ready_cuts(self):
        plan = self._build_valid_plan()

        self.assertEqual(
            plan.to_cuts(),
            [
                {"tc_in": "00:00:00:00", "tc_out": "00:00:03:00"},
                {"tc_in": "00:00:07:12", "tc_out": "00:00:11:00"},
            ],
        )

    def test_selected_order_is_preserved(self):
        plan = self._build_valid_plan()

        self.assertEqual(
            [bite.segment_index for bite in plan.options[0].selected_bites()],
            [0, 2],
        )

    def test_dict_round_trip_is_json_safe(self):
        plan = self._build_valid_plan()
        payload = plan.to_dict()

        json_text = json.dumps(payload, sort_keys=True)
        reloaded = SequencePlan.from_dict(json.loads(json_text), transcript_segments=SEGMENTS)

        self.assertEqual(reloaded.to_dict(), payload)
        self.assertEqual(reloaded.to_cuts(), plan.to_cuts())

    def test_from_dict_validates_zero_based_transcript_references_when_given_segments(self):
        payload = self._build_valid_plan().to_dict()
        payload["options"][0]["bites"][0]["segment_index"] = 1

        with self.assertRaisesRegex(SequencePlanValidationError, "do not match"):
            SequencePlan.from_dict(payload, transcript_segments=SEGMENTS)


if __name__ == "__main__":
    unittest.main()
