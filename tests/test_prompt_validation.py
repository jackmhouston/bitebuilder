import unittest
from types import SimpleNamespace

from llm.prompts import validate_llm_response


SEGMENTS = [
    SimpleNamespace(tc_in="00:00:00:00", tc_out="00:00:02:00"),
    SimpleNamespace(tc_in="00:00:02:00", tc_out="00:00:04:00"),
]
VALID_TIMECODES = {"00:00:00:00", "00:00:02:00", "00:00:04:00"}
VALID_CANDIDATES = {
    ("00:00:00:00", "00:00:02:00"),
    ("00:00:02:00", "00:00:04:00"),
}


class PromptValidationTests(unittest.TestCase):
    def test_accepts_valid_ok_response(self):
        response = {
            "selection_status": "ok",
            "options": [
                {
                    "name": "Option 1",
                    "cuts": [
                        {
                            "segment_index": 0,
                            "tc_in": "00:00:00:00",
                            "tc_out": "00:00:02:00",
                            "confidence": 0.8,
                            "purpose": "hook",
                        }
                    ],
                }
            ],
        }
        errors = validate_llm_response(
            response,
            valid_timecodes=VALID_TIMECODES,
            valid_candidate_timecodes=VALID_CANDIDATES,
            expected_options=1,
            transcript_segments=SEGMENTS,
        )
        self.assertEqual(errors, [])

    def test_accepts_no_candidates_contract(self):
        response = {
            "selection_status": "no_candidates",
            "options": [],
            "no_candidate_reason": "Nothing fit the brief.",
        }
        errors = validate_llm_response(response, valid_timecodes=VALID_TIMECODES)
        self.assertEqual(errors, [])

    def test_rejects_missing_options(self):
        response = {"selection_status": "ok"}
        errors = validate_llm_response(response, valid_timecodes=VALID_TIMECODES)
        self.assertIn("Missing 'options' key in response", errors)

    def test_rejects_invalid_segment_index_mapping(self):
        response = {
            "selection_status": "ok",
            "options": [
                {
                    "name": "Option 1",
                    "cuts": [
                        {
                            "segment_index": 1,
                            "tc_in": "00:00:00:00",
                            "tc_out": "00:00:02:00",
                            "confidence": 0.5,
                            "purpose": "hook",
                        }
                    ],
                }
            ],
        }
        errors = validate_llm_response(
            response,
            valid_timecodes=VALID_TIMECODES,
            valid_candidate_timecodes=VALID_CANDIDATES,
            expected_options=1,
            transcript_segments=SEGMENTS,
        )
        self.assertTrue(any("does not match a transcript segment definition" in item for item in errors))

    def test_rejects_candidate_mismatch(self):
        response = {
            "selection_status": "ok",
            "options": [
                {
                    "name": "Option 1",
                    "cuts": [
                        {
                            "segment_index": 0,
                            "tc_in": "00:00:00:00",
                            "tc_out": "00:00:04:00",
                            "confidence": 0.5,
                            "purpose": "hook",
                        }
                    ],
                }
            ],
        }
        errors = validate_llm_response(
            response,
            valid_timecodes=VALID_TIMECODES,
            valid_candidate_timecodes=VALID_CANDIDATES,
            expected_options=1,
            transcript_segments=SEGMENTS,
        )
        self.assertTrue(any("must match a candidate segment" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
