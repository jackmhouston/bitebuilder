import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from bitebuilder.models import PremiereProject, SelectionCandidate, SourceClip
from bitebuilder.xmeml_generator import render_xmeml_sequence


class XmemlGeneratorTests(unittest.TestCase):
    def test_renders_sequence_with_clipitems(self) -> None:
        project = PremiereProject(
            source_path=Path("/tmp/source.xml"),
            sequence_name="Source",
            fps=30,
            clips=[
                SourceClip(
                    clip_id="clipitem-1",
                    name="Interview A",
                    file_id="file-1",
                    file_name="interview.mov",
                    path_url="file://localhost/interview.mov",
                    in_frame=100,
                )
            ],
        )
        selections = [
            SelectionCandidate(
                transcript_index=1,
                quote="This is the line.",
                reason="Strong opener.",
                source_clip_id="clipitem-1",
                duration_seconds=3.5,
            )
        ]

        xml_text = render_xmeml_sequence("Test Sequence", project, selections)
        root = ET.fromstring(xml_text.split("\n", 1)[1])

        self.assertEqual(root.tag, "xmeml")
        self.assertEqual(root.findtext("./sequence/name"), "Test Sequence")
        self.assertEqual(root.findtext(".//clipitem/name"), "Interview A")


if __name__ == "__main__":
    unittest.main()
