"""
Parse Premiere Pro XML exports to extract source media metadata.

Extracts file path, frame rate, duration, resolution, and audio specs
from XMEML v4 format XML files.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from urllib.parse import unquote


@dataclass
class SourceMetadata:
    """Metadata about the source media file, extracted from Premiere XML."""
    source_name: str
    source_path: str        # Original file path (decoded from pathurl)
    pathurl: str            # Raw pathurl for XML generation
    timebase: int           # Nominal frame rate (e.g. 24, 30)
    ntsc: bool              # True = NTSC pulldown (23.976, 29.97, etc.)
    duration: int           # Total duration in frames
    width: int
    height: int
    audio_depth: int        # Bit depth (e.g. 16)
    audio_samplerate: int   # Sample rate (e.g. 48000)
    audio_channels: int     # Channel count (e.g. 2 for stereo)

    @property
    def actual_fps(self) -> float:
        if self.ntsc:
            return self.timebase * 1000 / 1001
        return float(self.timebase)

    @property
    def duration_seconds(self) -> float:
        return self.duration / self.actual_fps

    def to_dict(self) -> dict:
        d = asdict(self)
        d['actual_fps'] = self.actual_fps
        d['duration_seconds'] = self.duration_seconds
        return d


def _decode_pathurl(pathurl: str) -> str:
    """
    Decode a file:// URL to a filesystem path.

    file://localhost/F%3a/Video/My%20Project/file.mov
    → F:/Video/My Project/file.mov
    """
    path = pathurl
    if path.startswith('file://localhost/'):
        path = path[len('file://localhost/'):]
    elif path.startswith('file:///'):
        path = path[len('file:///'):]
    return unquote(path)


def parse_premiere_xml(filepath: str) -> SourceMetadata:
    """
    Parse a Premiere Pro XML export and extract source media metadata.

    Looks for the first <file> element with a <pathurl> to identify
    the source media, then extracts all relevant properties.

    Args:
        filepath: Path to the Premiere XML export file

    Returns:
        SourceMetadata dataclass with all extracted properties

    Raises:
        ValueError: If required elements are missing from the XML
    """
    tree = ET.parse(filepath)
    return _parse_premiere_root(tree.getroot())


def parse_premiere_xml_string(xml_text: str) -> SourceMetadata:
    """
    Parse a Premiere XML document from a raw string.
    """
    root = ET.fromstring(xml_text)
    return _parse_premiere_root(root)


def _parse_premiere_root(root) -> SourceMetadata:
    """
    Parse source metadata from an XML root element.
    """

    # Find the first file element with a pathurl (this is the source media)
    file_elem = None
    for f in root.iter('file'):
        pathurl_elem = f.find('pathurl')
        if pathurl_elem is not None and pathurl_elem.text:
            file_elem = f
            break

    if file_elem is None:
        raise ValueError("No <file> element with <pathurl> found in XML")

    # Source name and path
    source_name = _get_text(file_elem, 'name', 'Unknown')
    pathurl = _get_text(file_elem, 'pathurl')
    source_path = _decode_pathurl(pathurl)

    # Frame rate from file's rate element
    rate_elem = file_elem.find('rate')
    if rate_elem is None:
        # Fall back to sequence rate
        rate_elem = root.find('.//sequence/rate')
    timebase = int(_get_text(rate_elem, 'timebase', '24'))
    ntsc = _get_text(rate_elem, 'ntsc', 'FALSE').upper() == 'TRUE'

    # Duration
    duration = int(_get_text(file_elem, 'duration', '0'))

    # Video characteristics
    video_chars = file_elem.find('.//video/samplecharacteristics')
    if video_chars is None:
        # Fall back to sequence video format
        video_chars = root.find('.//sequence/media/video/format/samplecharacteristics')

    width = int(_get_text(video_chars, 'width', '1920'))
    height = int(_get_text(video_chars, 'height', '1080'))

    # Audio characteristics
    audio_chars = file_elem.find('.//audio/samplecharacteristics')
    if audio_chars is None:
        audio_chars = root.find('.//sequence/media/audio/format/samplecharacteristics')

    audio_depth = int(_get_text(audio_chars, 'depth', '16'))
    audio_samplerate = int(_get_text(audio_chars, 'samplerate', '48000'))

    audio_channels_elem = file_elem.find('.//audio/channelcount')
    audio_channels = int(audio_channels_elem.text) if audio_channels_elem is not None else 2

    return SourceMetadata(
        source_name=source_name,
        source_path=source_path,
        pathurl=pathurl,
        timebase=timebase,
        ntsc=ntsc,
        duration=duration,
        width=width,
        height=height,
        audio_depth=audio_depth,
        audio_samplerate=audio_samplerate,
        audio_channels=audio_channels,
    )


def _get_text(parent, tag: str, default: str = None) -> str:
    """Safely get text content of a child element."""
    if parent is None:
        if default is not None:
            return default
        raise ValueError(f"Parent element is None when looking for <{tag}>")
    elem = parent.find(tag)
    if elem is None or elem.text is None:
        if default is not None:
            return default
        raise ValueError(f"Required element <{tag}> not found")
    return elem.text.strip()
