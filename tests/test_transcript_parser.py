import tempfile
import unittest
from pathlib import Path

from bitebuilder.transcript_parser import parse_transcript


class TranscriptParserTests(unittest.TestCase):
    def test_parses_bracketed_timecodes(self) -> None:
        content = "[00:00:02-00:00:06] First line\nPlain line\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "transcript.txt"
            path.write_text(content, encoding="utf-8")
            document = parse_transcript(path)

        self.assertEqual(len(document.segments), 2)
        self.assertEqual(document.segments[0].start_seconds, 2.0)
        self.assertEqual(document.segments[0].end_seconds, 6.0)
        self.assertEqual(document.segments[1].text, "Plain line")


if __name__ == "__main__":
    unittest.main()

