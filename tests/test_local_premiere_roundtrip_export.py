import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "output" / "manual-import-smoke"
GENERATED_XML = FIXTURE_DIR / "bitebuilder_fixture_import_smoke.xml"
PREMIERE_EXPORT_XML = FIXTURE_DIR / "BiteBuilder Fixture Import Smoke.xml"


def clip_timing(root):
    return [
        (
            clip.get("id"),
            clip.findtext("start"),
            clip.findtext("end"),
            clip.findtext("in"),
            clip.findtext("out"),
        )
        for clip in root.iter("clipitem")
    ]


@unittest.skipUnless(
    GENERATED_XML.exists() and PREMIERE_EXPORT_XML.exists(),
    "local generated XML and Premiere re-export fixtures are not present",
)
class LocalPremiereRoundtripExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generated = ET.fromstring(GENERATED_XML.read_text(encoding="utf-8-sig"))
        cls.exported = ET.fromstring(PREMIERE_EXPORT_XML.read_text(encoding="utf-8-sig"))

    def test_premiere_reexport_preserves_sequence_identity_and_duration(self):
        self.assertEqual(
            self.generated.findtext(".//sequence/name"),
            self.exported.findtext(".//sequence/name"),
        )
        self.assertEqual(
            self.generated.findtext(".//sequence/duration"),
            self.exported.findtext(".//sequence/duration"),
        )

    def test_premiere_reexport_preserves_clip_timing(self):
        self.assertEqual(len(list(self.generated.iter("clipitem"))), 9)
        self.assertEqual(clip_timing(self.generated), clip_timing(self.exported))


if __name__ == "__main__":
    unittest.main()
