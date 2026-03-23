"""
XMEML v4 sequence generator for Premiere Pro.

Generates importable XML sequences from a list of cuts (timecode in/out pairs)
and source media metadata. Produces linked video + stereo audio tracks.

Validated against Premiere Pro import — structure reverse-engineered from
actual Premiere XML exports.
"""

import uuid as _uuid
from .timecode import tc_to_frames, frames_to_ticks
from parser.premiere_xml import SourceMetadata


def generate_sequence(
    name: str,
    cuts: list[dict],
    source: SourceMetadata,
    seq_uuid: str = None,
) -> str:
    """
    Generate a complete XMEML v4 sequence XML string.

    Args:
        name: Sequence name (appears in Premiere project panel)
        cuts: List of dicts with at minimum 'tc_in' and 'tc_out' keys.
              Timecodes must be in "HH:MM:SS:FF" format.
        source: SourceMetadata from premiere_xml parser
        seq_uuid: Optional UUID for the sequence. Auto-generated if None.

    Returns:
        Complete XMEML v4 XML string ready for Premiere import
    """
    if not cuts:
        raise ValueError("cuts list cannot be empty")

    if seq_uuid is None:
        seq_uuid = str(_uuid.uuid4())

    num_cuts = len(cuts)
    tb = source.timebase
    ntsc_str = "TRUE" if source.ntsc else "FALSE"

    # Calculate frame positions for all cuts
    clip_data = []
    tl_pos = 0
    for cut in cuts:
        src_in = tc_to_frames(cut['tc_in'], tb)
        src_out = tc_to_frames(cut['tc_out'], tb)
        duration = src_out - src_in
        if duration <= 0:
            raise ValueError(
                f"Invalid cut: tc_in={cut['tc_in']} tc_out={cut['tc_out']} "
                f"(duration={duration} frames)"
            )
        clip_data.append({
            'src_in': src_in,
            'src_out': src_out,
            'tl_start': tl_pos,
            'tl_end': tl_pos + duration,
        })
        tl_pos += duration

    total_duration = tl_pos

    # ID scheme: video 1..N, audio_L N+1..2N, audio_R 2N+1..3N
    vid_ids = list(range(1, num_cuts + 1))
    al_ids = list(range(num_cuts + 1, 2 * num_cuts + 1))
    ar_ids = list(range(2 * num_cuts + 1, 3 * num_cuts + 1))

    # Build video clipitems
    video_clips = []
    for i, cd in enumerate(clip_data):
        file_block = _file_ref(source) if i == 0 else '<file id="file-1"/>'
        video_clips.append(_video_clipitem(
            clip_id=vid_ids[i], clip_index=i + 1,
            src_in=cd['src_in'], src_out=cd['src_out'],
            tl_start=cd['tl_start'], tl_end=cd['tl_end'],
            al_id=al_ids[i], ar_id=ar_ids[i],
            file_block=file_block, source=source,
        ))

    # Build audio clipitems (track 1 = Left, track 2 = Right)
    audio_l_clips = []
    audio_r_clips = []
    for i, cd in enumerate(clip_data):
        for track_idx, clip_list, self_ids, partner_ids in [
            (1, audio_l_clips, al_ids, ar_ids),
            (2, audio_r_clips, ar_ids, al_ids),
        ]:
            clip_list.append(_audio_clipitem(
                clip_id=self_ids[i], clip_index=i + 1,
                src_in=cd['src_in'], src_out=cd['src_out'],
                tl_start=cd['tl_start'], tl_end=cd['tl_end'],
                vid_id=vid_ids[i], partner_id=partner_ids[i],
                track_index=track_idx, source=source,
            ))

    # Assemble full XML
    edit_line_ticks = frames_to_ticks(total_duration, tb, source.ntsc)

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
\t<sequence id="sequence-1" TL.SQAudioVisibleBase="0" TL.SQVideoVisibleBase="0" TL.SQVisibleBaseTime="0" TL.SQAVDividerPosition="0.5" TL.SQHideShyTracks="0" TL.SQHeaderWidth="204" Monitor.ProgramZoomOut="{edit_line_ticks}" Monitor.ProgramZoomIn="0" TL.SQTimePerPixel="0.5" MZ.EditLine="{edit_line_ticks}" MZ.Sequence.PreviewFrameSizeHeight="{source.height}" MZ.Sequence.PreviewFrameSizeWidth="{source.width}" MZ.Sequence.AudioTimeDisplayFormat="200" MZ.Sequence.PreviewRenderingClassID="1061109567" MZ.Sequence.PreviewRenderingPresetCodec="1634755443" MZ.Sequence.PreviewRenderingPresetPath="EncoderPresets\\SequencePreview\\9678af98-a7b7-4bdb-b477-7ac9c8df4a4e\\QuickTime.epr" MZ.Sequence.PreviewUseMaxRenderQuality="false" MZ.Sequence.PreviewUseMaxBitDepth="false" MZ.Sequence.EditingModeGUID="9678af98-a7b7-4bdb-b477-7ac9c8df4a4e" MZ.Sequence.VideoTimeDisplayFormat="110" MZ.WorkOutPoint="{edit_line_ticks}" MZ.WorkInPoint="0" explodedTracks="true">
\t\t<uuid>{seq_uuid}</uuid>
\t\t<duration>{total_duration}</duration>
\t\t<rate>
\t\t\t<timebase>{tb}</timebase>
\t\t\t<ntsc>{ntsc_str}</ntsc>
\t\t</rate>
\t\t<name>{_xml_escape(name)}</name>
\t\t<media>
\t\t\t<video>
\t\t\t\t<format>
\t\t\t\t\t<samplecharacteristics>
\t\t\t\t\t\t<rate>
\t\t\t\t\t\t\t<timebase>{tb}</timebase>
\t\t\t\t\t\t\t<ntsc>{ntsc_str}</ntsc>
\t\t\t\t\t\t</rate>
\t\t\t\t\t\t<codec>
\t\t\t\t\t\t\t<name>Apple ProRes 422</name>
\t\t\t\t\t\t\t<appspecificdata>
\t\t\t\t\t\t\t\t<appname>Final Cut Pro</appname>
\t\t\t\t\t\t\t\t<appmanufacturer>Apple Inc.</appmanufacturer>
\t\t\t\t\t\t\t\t<appversion>7.0</appversion>
\t\t\t\t\t\t\t\t<data>
\t\t\t\t\t\t\t\t\t<qtcodec>
\t\t\t\t\t\t\t\t\t\t<codecname>Apple ProRes 422</codecname>
\t\t\t\t\t\t\t\t\t\t<codectypename>Apple ProRes 422</codectypename>
\t\t\t\t\t\t\t\t\t\t<codectypecode>apcn</codectypecode>
\t\t\t\t\t\t\t\t\t\t<codecvendorcode>appl</codecvendorcode>
\t\t\t\t\t\t\t\t\t\t<spatialquality>1024</spatialquality>
\t\t\t\t\t\t\t\t\t\t<temporalquality>0</temporalquality>
\t\t\t\t\t\t\t\t\t\t<keyframerate>0</keyframerate>
\t\t\t\t\t\t\t\t\t\t<datarate>0</datarate>
\t\t\t\t\t\t\t\t\t</qtcodec>
\t\t\t\t\t\t\t\t</data>
\t\t\t\t\t\t\t</appspecificdata>
\t\t\t\t\t\t</codec>
\t\t\t\t\t\t<width>{source.width}</width>
\t\t\t\t\t\t<height>{source.height}</height>
\t\t\t\t\t\t<anamorphic>FALSE</anamorphic>
\t\t\t\t\t\t<pixelaspectratio>square</pixelaspectratio>
\t\t\t\t\t\t<fielddominance>none</fielddominance>
\t\t\t\t\t\t<colordepth>24</colordepth>
\t\t\t\t\t</samplecharacteristics>
\t\t\t\t</format>
\t\t\t\t<track TL.SQTrackShy="0" TL.SQTrackExpandedHeight="71" TL.SQTrackExpanded="0" MZ.TrackTargeted="1">
{chr(10).join(video_clips)}
\t\t\t\t</track>
\t\t\t</video>
\t\t\t<audio>
\t\t\t\t<numOutputChannels>1</numOutputChannels>
\t\t\t\t<format>
\t\t\t\t\t<samplecharacteristics>
\t\t\t\t\t\t<depth>{source.audio_depth}</depth>
\t\t\t\t\t\t<samplerate>{source.audio_samplerate}</samplerate>
\t\t\t\t\t</samplecharacteristics>
\t\t\t\t</format>
\t\t\t\t<outputs>
\t\t\t\t\t<group>
\t\t\t\t\t\t<index>1</index>
\t\t\t\t\t\t<numchannels>1</numchannels>
\t\t\t\t\t\t<downmix>0</downmix>
\t\t\t\t\t\t<channel><index>1</index></channel>
\t\t\t\t\t</group>
\t\t\t\t\t<group>
\t\t\t\t\t\t<index>2</index>
\t\t\t\t\t\t<numchannels>1</numchannels>
\t\t\t\t\t\t<downmix>0</downmix>
\t\t\t\t\t\t<channel><index>2</index></channel>
\t\t\t\t\t</group>
\t\t\t\t</outputs>
\t\t\t\t<track TL.SQTrackAudioKeyframeStyle="0" TL.SQTrackShy="0" TL.SQTrackExpandedHeight="182" TL.SQTrackExpanded="0" MZ.TrackTargeted="1" PannerCurrentValue="0.5" PannerIsInverted="true" PannerStartKeyframe="-91445760000000000,0.5,0,0,0,0,0,0" PannerName="Balance" currentExplodedTrackIndex="0" totalExplodedTrackCount="2" premiereTrackType="Mono">
{chr(10).join(audio_l_clips)}
\t\t\t\t</track>
\t\t\t\t<track TL.SQTrackAudioKeyframeStyle="0" TL.SQTrackShy="0" TL.SQTrackExpandedHeight="182" TL.SQTrackExpanded="0" MZ.TrackTargeted="0" PannerCurrentValue="0.5" PannerIsInverted="true" PannerStartKeyframe="-91445760000000000,0.5,0,0,0,0,0,0" PannerName="Balance" currentExplodedTrackIndex="1" totalExplodedTrackCount="2" premiereTrackType="Mono">
{chr(10).join(audio_r_clips)}
\t\t\t\t</track>
\t\t\t</audio>
\t\t</media>
\t</sequence>
</xmeml>'''


# ─── Internal helpers ───────────────────────────────────────────────


def _xml_escape(text: str) -> str:
    """Escape special XML characters."""
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;'))


def _file_ref(source: SourceMetadata) -> str:
    """Generate the full <file> element (used on first clipitem only)."""
    ntsc_str = "TRUE" if source.ntsc else "FALSE"
    return f'''<file id="file-1">
\t\t\t\t\t\t\t<name>{_xml_escape(source.source_name)}</name>
\t\t\t\t\t\t\t<pathurl>{source.pathurl}</pathurl>
\t\t\t\t\t\t\t<rate>
\t\t\t\t\t\t\t\t<timebase>{source.timebase}</timebase>
\t\t\t\t\t\t\t\t<ntsc>{ntsc_str}</ntsc>
\t\t\t\t\t\t\t</rate>
\t\t\t\t\t\t\t<duration>{source.duration}</duration>
\t\t\t\t\t\t\t<timecode>
\t\t\t\t\t\t\t\t<rate>
\t\t\t\t\t\t\t\t\t<timebase>{source.timebase}</timebase>
\t\t\t\t\t\t\t\t\t<ntsc>{ntsc_str}</ntsc>
\t\t\t\t\t\t\t\t</rate>
\t\t\t\t\t\t\t\t<string>00:00:00:00</string>
\t\t\t\t\t\t\t\t<frame>0</frame>
\t\t\t\t\t\t\t\t<displayformat>NDF</displayformat>
\t\t\t\t\t\t\t</timecode>
\t\t\t\t\t\t\t<media>
\t\t\t\t\t\t\t\t<video>
\t\t\t\t\t\t\t\t\t<samplecharacteristics>
\t\t\t\t\t\t\t\t\t\t<rate>
\t\t\t\t\t\t\t\t\t\t\t<timebase>{source.timebase}</timebase>
\t\t\t\t\t\t\t\t\t\t\t<ntsc>{ntsc_str}</ntsc>
\t\t\t\t\t\t\t\t\t\t</rate>
\t\t\t\t\t\t\t\t\t\t<width>{source.width}</width>
\t\t\t\t\t\t\t\t\t\t<height>{source.height}</height>
\t\t\t\t\t\t\t\t\t\t<anamorphic>FALSE</anamorphic>
\t\t\t\t\t\t\t\t\t\t<pixelaspectratio>square</pixelaspectratio>
\t\t\t\t\t\t\t\t\t\t<fielddominance>none</fielddominance>
\t\t\t\t\t\t\t\t\t</samplecharacteristics>
\t\t\t\t\t\t\t\t</video>
\t\t\t\t\t\t\t\t<audio>
\t\t\t\t\t\t\t\t\t<samplecharacteristics>
\t\t\t\t\t\t\t\t\t\t<depth>{source.audio_depth}</depth>
\t\t\t\t\t\t\t\t\t\t<samplerate>{source.audio_samplerate}</samplerate>
\t\t\t\t\t\t\t\t\t</samplecharacteristics>
\t\t\t\t\t\t\t\t\t<channelcount>{source.audio_channels}</channelcount>
\t\t\t\t\t\t\t\t</audio>
\t\t\t\t\t\t\t</media>
\t\t\t\t\t\t</file>'''


def _link_block(vid_id: int, al_id: int, ar_id: int, clip_index: int) -> str:
    """Generate the 3-way link block shared by video and audio clipitems."""
    return f'''\t\t\t\t\t\t<link>
\t\t\t\t\t\t\t<linkclipref>clipitem-{vid_id}</linkclipref>
\t\t\t\t\t\t\t<mediatype>video</mediatype>
\t\t\t\t\t\t\t<trackindex>1</trackindex>
\t\t\t\t\t\t\t<clipindex>{clip_index}</clipindex>
\t\t\t\t\t\t</link>
\t\t\t\t\t\t<link>
\t\t\t\t\t\t\t<linkclipref>clipitem-{al_id}</linkclipref>
\t\t\t\t\t\t\t<mediatype>audio</mediatype>
\t\t\t\t\t\t\t<trackindex>1</trackindex>
\t\t\t\t\t\t\t<clipindex>{clip_index}</clipindex>
\t\t\t\t\t\t</link>
\t\t\t\t\t\t<link>
\t\t\t\t\t\t\t<linkclipref>clipitem-{ar_id}</linkclipref>
\t\t\t\t\t\t\t<mediatype>audio</mediatype>
\t\t\t\t\t\t\t<trackindex>2</trackindex>
\t\t\t\t\t\t\t<clipindex>{clip_index}</clipindex>
\t\t\t\t\t\t</link>'''


def _video_clipitem(clip_id, clip_index, src_in, src_out, tl_start, tl_end,
                    al_id, ar_id, file_block, source):
    tb = source.timebase
    ntsc_str = "TRUE" if source.ntsc else "FALSE"
    ticks_in = frames_to_ticks(src_in, tb, source.ntsc)
    ticks_out = frames_to_ticks(src_out, tb, source.ntsc)
    links = _link_block(clip_id, al_id, ar_id, clip_index)

    return f'''\t\t\t\t\t<clipitem id="clipitem-{clip_id}">
\t\t\t\t\t\t<masterclipid>masterclip-1</masterclipid>
\t\t\t\t\t\t<name>{_xml_escape(source.source_name)}</name>
\t\t\t\t\t\t<enabled>TRUE</enabled>
\t\t\t\t\t\t<duration>{source.duration}</duration>
\t\t\t\t\t\t<rate>
\t\t\t\t\t\t\t<timebase>{tb}</timebase>
\t\t\t\t\t\t\t<ntsc>{ntsc_str}</ntsc>
\t\t\t\t\t\t</rate>
\t\t\t\t\t\t<start>{tl_start}</start>
\t\t\t\t\t\t<end>{tl_end}</end>
\t\t\t\t\t\t<in>{src_in}</in>
\t\t\t\t\t\t<out>{src_out}</out>
\t\t\t\t\t\t<pproTicksIn>{ticks_in}</pproTicksIn>
\t\t\t\t\t\t<pproTicksOut>{ticks_out}</pproTicksOut>
\t\t\t\t\t\t<alphatype>none</alphatype>
\t\t\t\t\t\t<pixelaspectratio>square</pixelaspectratio>
\t\t\t\t\t\t<anamorphic>FALSE</anamorphic>
\t\t\t\t\t\t{file_block}
{links}
\t\t\t\t\t\t<labels>
\t\t\t\t\t\t\t<label2>Iris</label2>
\t\t\t\t\t\t</labels>
\t\t\t\t\t</clipitem>'''


def _audio_clipitem(clip_id, clip_index, src_in, src_out, tl_start, tl_end,
                    vid_id, partner_id, track_index, source):
    tb = source.timebase
    ntsc_str = "TRUE" if source.ntsc else "FALSE"
    ticks_in = frames_to_ticks(src_in, tb, source.ntsc)
    ticks_out = frames_to_ticks(src_out, tb, source.ntsc)

    # For audio, the link block order depends on which track we're on
    al_id = clip_id if track_index == 1 else partner_id
    ar_id = partner_id if track_index == 1 else clip_id
    links = _link_block(vid_id, al_id, ar_id, clip_index)

    return f'''\t\t\t\t\t<clipitem id="clipitem-{clip_id}" premiereChannelType="stereo">
\t\t\t\t\t\t<masterclipid>masterclip-1</masterclipid>
\t\t\t\t\t\t<name>{_xml_escape(source.source_name)}</name>
\t\t\t\t\t\t<enabled>TRUE</enabled>
\t\t\t\t\t\t<duration>{source.duration}</duration>
\t\t\t\t\t\t<rate>
\t\t\t\t\t\t\t<timebase>{tb}</timebase>
\t\t\t\t\t\t\t<ntsc>{ntsc_str}</ntsc>
\t\t\t\t\t\t</rate>
\t\t\t\t\t\t<start>{tl_start}</start>
\t\t\t\t\t\t<end>{tl_end}</end>
\t\t\t\t\t\t<in>{src_in}</in>
\t\t\t\t\t\t<out>{src_out}</out>
\t\t\t\t\t\t<pproTicksIn>{ticks_in}</pproTicksIn>
\t\t\t\t\t\t<pproTicksOut>{ticks_out}</pproTicksOut>
\t\t\t\t\t\t<file id="file-1"/>
\t\t\t\t\t\t<sourcetrack>
\t\t\t\t\t\t\t<mediatype>audio</mediatype>
\t\t\t\t\t\t\t<trackindex>{track_index}</trackindex>
\t\t\t\t\t\t</sourcetrack>
{links}
\t\t\t\t\t</clipitem>'''
