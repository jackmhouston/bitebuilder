import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from generator.timecode import estimate_duration_seconds, tc_to_frames
from generator.xmeml import build_deterministic_sequence_id, generate_sequence
from parser.premiere_xml import parse_premiere_xml_string
from parser.transcript import parse_transcript


FIXTURE_DIR = Path(__file__).parent / "src"
TRANSCRIPT_FIXTURE = FIXTURE_DIR / "Andy Graham Interview 1.txt"
XML_FIXTURE = FIXTURE_DIR / "Andy Graham Interview 1.xml"


@unittest.skipUnless(
    TRANSCRIPT_FIXTURE.exists() and XML_FIXTURE.exists(),
    "local Premiere transcript/XML fixtures are not present",
)
class LocalPremiereFixtureFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.transcript_text = TRANSCRIPT_FIXTURE.read_text(encoding="utf-8-sig")
        cls.xml_text = XML_FIXTURE.read_text(encoding="utf-8-sig")
        cls.source = parse_premiere_xml_string(cls.xml_text)
        cls.segments = parse_transcript(
            cls.transcript_text,
            strict=True,
            timebase=cls.source.timebase,
            ntsc=cls.source.ntsc,
        )

    def test_fixture_transcript_and_xml_parse_with_matching_timeline_bounds(self):
        self.assertEqual(len(self.segments), 51)
        self.assertEqual(self.source.timebase, 24)
        self.assertTrue(self.source.ntsc)
        self.assertEqual(self.source.width, 3840)
        self.assertEqual(self.source.height, 2160)
        self.assertEqual(self.source.audio_samplerate, 48000)

        last_segment = self.segments[-1]
        self.assertLessEqual(tc_to_frames(last_segment.tc_out, self.source.timebase), self.source.duration)

    def test_fixture_segments_generate_parseable_xmeml(self):
        selected_segments = self.segments[:3]
        cuts = [{"tc_in": segment.tc_in, "tc_out": segment.tc_out} for segment in selected_segments]
        xml = generate_sequence("Fixture Smoke Sequence", cuts, self.source)
        ET.fromstring(xml)

        self.assertEqual(xml.count("<clipitem id="), 9)
        self.assertEqual(
            build_deterministic_sequence_id("Fixture Smoke Sequence", cuts, self.source),
            build_deterministic_sequence_id("Fixture Smoke Sequence", cuts, self.source),
        )
        self.assertGreater(
            sum(
                estimate_duration_seconds(segment.tc_in, segment.tc_out, self.source.timebase, self.source.ntsc)
                for segment in selected_segments
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()
