import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import bitebuilder
from bitebuilder_tui import TuiSession, _fit_line, _wrap_panel_lines
from tests.test_pipeline import TRANSCRIPT_TEXT, XML_TEXT
from tests.test_plan_to_xmeml import write_plan


def args(**overrides):
    data = {
        "transcript": None,
        "xml": None,
        "sequence_plan": None,
        "output": "./output",
        "model": "gemma3:4b",
        "host": "http://127.0.0.1:11434",
        "timeout": 1,
        "thinking_mode": "auto",
        "option_id": None,
        "max_bite_duration": None,
        "max_total_duration": None,
        "require_changed_cuts": False,
        "refinement_retries": 1,
        "brief": None,
    }
    data.update(overrides)
    return Namespace(**data)


class TuiSessionTests(unittest.TestCase):
    def test_load_existing_plan_and_render_direct_move_without_ollama(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            transcript_path = tmp / "transcript.txt"
            xml_path = tmp / "source.xml"
            plan_path = tmp / "_sequence_plan.json"
            output_dir = tmp / "out"
            transcript_path.write_text(TRANSCRIPT_TEXT, encoding="utf-8")
            xml_path.write_text(XML_TEXT, encoding="utf-8")
            write_plan(plan_path)

            session = TuiSession.from_args(
                args(
                    transcript=str(transcript_path),
                    xml=str(xml_path),
                    sequence_plan=str(plan_path),
                    output=str(output_dir),
                ),
                api=bitebuilder,
            )

            session.load_plan()
            self.assertIn("Hello there.", session.summary_text())

            session.add_segment(1)
            self.assertTrue(Path(session.current_render["output_path"]).exists())
            self.assertTrue(Path(session.plan_path).exists())
            self.assertEqual(
                [bite.segment_index for bite in session.current_plan().options[0].selected_bites()],
                [0, 1],
            )

            session.move_selected(2, 1)
            self.assertEqual(
                [bite.segment_index for bite in session.current_plan().options[0].selected_bites()],
                [1, 0],
            )

            session.delete_selected(2)
            self.assertEqual(
                [bite.segment_index for bite in session.current_plan().options[0].selected_bites()],
                [1],
            )
            self.assertIn("Deleted selected bite 2.", session.message)

    def test_transcript_search_uses_loaded_segments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            transcript_path = tmp / "transcript.txt"
            xml_path = tmp / "source.xml"
            plan_path = tmp / "_sequence_plan.json"
            transcript_path.write_text(TRANSCRIPT_TEXT, encoding="utf-8")
            xml_path.write_text(XML_TEXT, encoding="utf-8")
            write_plan(plan_path)
            session = TuiSession.from_args(
                args(transcript=str(transcript_path), xml=str(xml_path), sequence_plan=str(plan_path)),
                api=bitebuilder,
            )
            session.load_plan()

            self.assertIn("General Kenobi.", session.transcript_text_for_view(query="Kenobi"))

    def test_panel_text_wraps_instead_of_silent_truncation(self):
        text = "Spoken text: " + ("This is a long transcript line that should remain readable. " * 3)

        wrapped = _wrap_panel_lines(text, 32)

        self.assertGreater(len(wrapped), 3)
        self.assertTrue(all(len(line) <= 32 for line in wrapped))
        self.assertIn("transcript", " ".join(wrapped))

    def test_fit_line_uses_visible_middle_ellipsis_for_paths(self):
        fitted = _fit_line("/Volumes/Two Jackson/001_Transcode/transcripts/CEO Interview.txt", 30)

        self.assertLessEqual(len(fitted), 30)
        self.assertIn("...", fitted)
        self.assertTrue(fitted.endswith("Interview.txt"))


if __name__ == "__main__":
    unittest.main()
