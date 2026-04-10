import unittest

from parser.transcript import TranscriptValidationError, parse_transcript


VALID_TRANSCRIPT = """00:00:00:00 - 00:00:02:00
Speaker 1
Hello there.

00:00:02:00 - 00:00:04:00
Speaker 2
General Kenobi.
"""


class TranscriptParserTests(unittest.TestCase):
    def test_parses_valid_transcript(self):
        segments = parse_transcript(VALID_TRANSCRIPT, strict=True)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].speaker, "Speaker 1")
        self.assertEqual(segments[1].text, "General Kenobi.")

    def test_rejects_malformed_timecode_line(self):
        text = """00:00:00:00 - 00:00:02
Speaker 1
Hello there.
"""
        with self.assertRaises(TranscriptValidationError) as ctx:
            parse_transcript(text, strict=True)
        self.assertIn("Invalid timecode pair line format", str(ctx.exception))

    def test_rejects_overlap(self):
        text = """00:00:00:00 - 00:00:03:00
Speaker 1
Hello there.

00:00:02:00 - 00:00:04:00
Speaker 2
General Kenobi.
"""
        with self.assertRaises(TranscriptValidationError) as ctx:
            parse_transcript(text, strict=True)
        messages = [error["message"] for error in ctx.exception.errors]
        self.assertTrue(any("Impossible transition" in message for message in messages))

    def test_rejects_empty_dialogue_block(self):
        text = """00:00:00:00 - 00:00:02:00
Speaker 1

"""
        with self.assertRaises(TranscriptValidationError) as ctx:
            parse_transcript(text, strict=True)
        messages = [error["message"] for error in ctx.exception.errors]
        self.assertTrue(any("has no dialogue text" in message for message in messages))

    def test_rejects_frame_exceeding_timebase(self):
        text = """00:00:00:30 - 00:00:02:00
Speaker 1
Hello there.
"""
        with self.assertRaises(TranscriptValidationError) as ctx:
            parse_transcript(text, strict=True, timebase=30)
        messages = [error["message"] for error in ctx.exception.errors]
        self.assertTrue(any("exceeds timebase" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
