import unittest
import xml.etree.ElementTree as ET

from parser.premiere_xml import parse_premiere_xml_string


VALID_XML = """<?xml version="1.0" encoding="UTF-8"?>
<xmeml version="4">
  <sequence>
    <name>Example Sequence</name>
    <rate>
      <timebase>24</timebase>
      <ntsc>FALSE</ntsc>
    </rate>
    <media>
      <video>
        <format>
          <samplecharacteristics>
            <width>1920</width>
            <height>1080</height>
          </samplecharacteristics>
        </format>
      </video>
      <audio>
        <format>
          <samplecharacteristics>
            <depth>24</depth>
            <samplerate>48000</samplerate>
          </samplecharacteristics>
        </format>
      </audio>
    </media>
  </sequence>
  <file id="file-1">
    <name>clip.mov</name>
    <pathurl>file:///Volumes/Test/clip.mov</pathurl>
    <rate>
      <timebase>24</timebase>
      <ntsc>FALSE</ntsc>
    </rate>
    <duration>240</duration>
    <media>
      <video>
        <samplecharacteristics>
          <width>1920</width>
          <height>1080</height>
        </samplecharacteristics>
      </video>
      <audio>
        <samplecharacteristics>
          <depth>24</depth>
          <samplerate>48000</samplerate>
        </samplecharacteristics>
        <channelcount>2</channelcount>
      </audio>
    </media>
  </file>
</xmeml>
"""


class PremiereXmlParserTests(unittest.TestCase):
    def test_parses_valid_xml(self):
        source = parse_premiere_xml_string(VALID_XML)
        self.assertEqual(source.source_name, "clip.mov")
        self.assertEqual(source.width, 1920)
        self.assertEqual(source.audio_channels, 2)
        self.assertEqual(source.timebase, 24)

    def test_raises_on_malformed_xml(self):
        with self.assertRaises(ET.ParseError):
            parse_premiere_xml_string("<xmeml><sequence>")

    def test_raises_on_missing_pathurl(self):
        xml = """<xmeml version="4"><sequence><name>No Path</name></sequence></xmeml>"""
        with self.assertRaises(ValueError) as ctx:
            parse_premiere_xml_string(xml)
        self.assertIn("pathurl", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
