# Premiere Pro XML Sequence Generation from Transcript Data

## Technical Reference for CEP Extension / Tool Development

**Author:** Claude (AI-assisted reverse engineering)
**Date:** March 20, 2026
**Tested With:** Adobe Premiere Pro (XMEML v4 import)
**Source Format:** 1920x1080, 23.976fps, Apple ProRes 422, Stereo Audio (48kHz/16-bit)

---

## Overview

This document describes how to programmatically generate Premiere Pro-importable XML sequences from transcript timecodes. The workflow is:

1. Parse a transcript with timecoded dialogue
2. Select "bites" (in/out points) from the transcript
3. Generate an XMEML v4 XML file with those bites as sequential clips on a timeline
4. Import the XML into Premiere Pro via `File > Import`

Premiere treats the imported XML as a native sequence with linked video and audio clips referencing the original source media.

---

## The XMEML v4 Format

Premiere Pro uses **XMEML (XML Media Exchange Markup Language) version 4** for XML interchange. This is the same format used by Final Cut Pro 7 and is the most widely supported interchange format across NLEs.

### Document Structure

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
    <sequence>
        <!-- Sequence metadata -->
        <!-- Media container -->
            <!-- Video tracks -->
            <!-- Audio tracks -->
    </sequence>
</xmeml>
```

### Key Concepts

| Concept | Description |
|---------|-------------|
| `<sequence>` | The top-level timeline container |
| `<clipitem>` | A single clip on the timeline |
| `<file>` | A reference to a source media file (defined once, referenced by ID thereafter) |
| `<masterclipid>` | Groups video and audio from the same source |
| `start` / `end` | Timeline position (in frames) |
| `in` / `out` | Source media position (in frames) |
| `pproTicksIn` / `pproTicksOut` | High-precision source position (Premiere internal ticks) |
| `<link>` | Connects video clipitems to their corresponding audio clipitems |

---

## Frame and Timing Math

### Frame Rate: 23.976fps (NTSC)

This is represented in XMEML as:
```xml
<rate>
    <timebase>24</timebase>
    <ntsc>TRUE</ntsc>
</rate>
```

When `ntsc=TRUE`, the actual framerate is `timebase * 1000/1001`:
- `timebase=24, ntsc=TRUE` ƒ+' 23.976fps
- `timebase=30, ntsc=TRUE` ƒ+' 29.97fps
- `timebase=60, ntsc=TRUE` ƒ+' 59.94fps

When `ntsc=FALSE`, the framerate equals the timebase exactly.

### Timecode to Frame Conversion (Non-Drop Frame)

For NDF timecode at any timebase:

```
frame = (HH * 3600 * timebase) + (MM * 60 * timebase) + (SS * timebase) + FF
```

Simplified for timebase=24:

```
frame = (HH * 86400) + (MM * 1440) + (SS * 24) + FF
```

**Example:** `00:15:12:11` ƒ+' `(0 * 86400) + (15 * 1440) + (12 * 24) + 11` = `21600 + 288 + 11` = `21899`

### Premiere Pro Ticks (pproTicks)

Premiere uses an internal high-precision tick system for sub-frame accuracy. The tick rate is **254,016,000,000 ticks per second**, which is constant regardless of frame rate.

**Ticks per frame** = `254016000000 / actual_fps`

| Timebase | NTSC | Actual FPS | Ticks per Frame |
|----------|------|------------|-----------------|
| 24 | TRUE | 23.976 | **10,594,584,000** |
| 24 | FALSE | 24.000 | 10,584,000,000 |
| 30 | TRUE | 29.97 | 8,475,667,200 |
| 30 | FALSE | 30.00 | 8,467,200,000 |
| 60 | TRUE | 59.94 | 4,237,833,600 |
| 60 | FALSE | 60.00 | 4,233,600,000 |

**Formula for NTSC rates:**
```
ticks_per_frame = 254016000000 * 1001 / (timebase * 1000)
```

For 23.976fps: `254016000000 * 1001 / 24000` = `10,594,584,000`

**Converting frame to pproTicks:**
```
pproTicks = frame_number * ticks_per_frame
```

### Complete Conversion Pipeline

```
Timecode String ƒ+' Frame Number ƒ+' pproTicks
"00:15:12:11"   ƒ+' 21899        ƒ+' 231,914,950,116,000
```

```javascript
// JavaScript implementation
function tcToFrames(tc, timebase = 24) {
    const [hh, mm, ss, ff] = tc.split(":").map(Number);
    return (hh * 3600 * timebase) + (mm * 60 * timebase) + (ss * timebase) + ff;
}

function framesToTicks(frames, timebase = 24, ntsc = true) {
    const ticksPerFrame = ntsc
        ? (254016000000 * 1001) / (timebase * 1000)
        : 254016000000 / timebase;
    return Math.round(frames * ticksPerFrame);
}
```

---

## XML Structure Deep Dive

### Sequence Element

The `<sequence>` element carries a lot of metadata as attributes. Most are optional for import, but including them ensures Premiere renders the sequence correctly.

```xml
<sequence id="sequence-1"
    TL.SQAudioVisibleBase="0"
    TL.SQVideoVisibleBase="0"
    TL.SQVisibleBaseTime="0"
    TL.SQAVDividerPosition="0.5"
    TL.SQHideShyTracks="0"
    TL.SQHeaderWidth="204"
    Monitor.ProgramZoomOut="{total_duration_ticks}"
    Monitor.ProgramZoomIn="0"
    TL.SQTimePerPixel="0.5"
    MZ.EditLine="{total_duration_ticks}"
    MZ.Sequence.PreviewFrameSizeHeight="1080"
    MZ.Sequence.PreviewFrameSizeWidth="1920"
    MZ.Sequence.AudioTimeDisplayFormat="200"
    MZ.Sequence.PreviewRenderingClassID="1061109567"
    MZ.Sequence.PreviewRenderingPresetCodec="1634755443"
    MZ.Sequence.PreviewRenderingPresetPath="EncoderPresets\SequencePreview\9678af98-a7b7-4bdb-b477-7ac9c8df4a4e\QuickTime.epr"
    MZ.Sequence.PreviewUseMaxRenderQuality="false"
    MZ.Sequence.PreviewUseMaxBitDepth="false"
    MZ.Sequence.EditingModeGUID="9678af98-a7b7-4bdb-b477-7ac9c8df4a4e"
    MZ.Sequence.VideoTimeDisplayFormat="110"
    MZ.WorkOutPoint="{total_duration_ticks}"
    MZ.WorkInPoint="0"
    explodedTracks="true">
```

**Critical attributes:**
- `MZ.Sequence.PreviewFrameSizeHeight/Width` ƒ?" Determines sequence resolution
- `MZ.Sequence.EditingModeGUID` ƒ?" `9678af98-a7b7-4bdb-b477-7ac9c8df4a4e` is the standard custom editing mode
- `MZ.Sequence.VideoTimeDisplayFormat` ƒ?" `110` = NDF timecode display
- `explodedTracks="true"` ƒ?" Required for proper stereo audio track handling

### Sequence Children

```xml
<sequence>
    <uuid>{unique-uuid}</uuid>
    <duration>{total_frames}</duration>
    <rate>
        <timebase>24</timebase>
        <ntsc>TRUE</ntsc>
    </rate>
    <name>Sequence Name</name>
    <media>
        <video>...</video>
        <audio>...</audio>
    </media>
</sequence>
```

### Video Track Structure

```xml
<video>
    <format>
        <samplecharacteristics>
            <rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>
            <codec>
                <name>Apple ProRes 422</name>
                <appspecificdata>
                    <appname>Final Cut Pro</appname>
                    <appmanufacturer>Apple Inc.</appmanufacturer>
                    <appversion>7.0</appversion>
                    <data>
                        <qtcodec>
                            <codecname>Apple ProRes 422</codecname>
                            <codectypename>Apple ProRes 422</codectypename>
                            <codectypecode>apcn</codectypecode>
                            <codecvendorcode>appl</codecvendorcode>
                            <spatialquality>1024</spatialquality>
                            <temporalquality>0</temporalquality>
                            <keyframerate>0</keyframerate>
                            <datarate>0</datarate>
                        </qtcodec>
                    </data>
                </appspecificdata>
            </codec>
            <width>1920</width>
            <height>1080</height>
            <anamorphic>FALSE</anamorphic>
            <pixelaspectratio>square</pixelaspectratio>
            <fielddominance>none</fielddominance>
            <colordepth>24</colordepth>
        </samplecharacteristics>
    </format>
    <track>
        <!-- clipitems go here -->
    </track>
</video>
```

**Note on codec:** The codec block describes the sequence's preview render format, not the source media codec. `apcn` (ProRes 422) is a safe universal default. Premiere will conform the source media regardless of its actual codec.

### Audio Track Structure

```xml
<audio>
    <numOutputChannels>1</numOutputChannels>
    <format>
        <samplecharacteristics>
            <depth>16</depth>
            <samplerate>48000</samplerate>
        </samplecharacteristics>
    </format>
    <outputs>
        <group>
            <index>1</index>
            <numchannels>1</numchannels>
            <downmix>0</downmix>
            <channel><index>1</index></channel>
        </group>
        <group>
            <index>2</index>
            <numchannels>1</numchannels>
            <downmix>0</downmix>
            <channel><index>2</index></channel>
        </group>
    </outputs>
    <!-- Track 1 (Left) -->
    <track premiereTrackType="Mono"
           currentExplodedTrackIndex="0"
           totalExplodedTrackCount="2">
        <!-- clipitems for audio channel 1 -->
    </track>
    <!-- Track 2 (Right) -->
    <track premiereTrackType="Mono"
           currentExplodedTrackIndex="1"
           totalExplodedTrackCount="2">
        <!-- clipitems for audio channel 2 -->
    </track>
</audio>
```

**Key details for stereo audio:**
- `explodedTracks="true"` on the sequence + `totalExplodedTrackCount="2"` on each track tells Premiere these are L/R channels of the same stereo pair
- `currentExplodedTrackIndex` is 0-based (0 = Left, 1 = Right)
- Each track gets its own set of clipitems mirroring the video clips
- `premiereTrackType="Mono"` ƒ?" Each track is a mono channel; together they form stereo

---

## Clipitem Structure

### Video Clipitem

```xml
<clipitem id="clipitem-{VIDEO_ID}">
    <masterclipid>masterclip-1</masterclipid>
    <name>Source Filename.mov</name>
    <enabled>TRUE</enabled>
    <duration>{SOURCE_TOTAL_DURATION_FRAMES}</duration>
    <rate>
        <timebase>24</timebase>
        <ntsc>TRUE</ntsc>
    </rate>
    <start>{TIMELINE_START_FRAME}</start>
    <end>{TIMELINE_END_FRAME}</end>
    <in>{SOURCE_IN_FRAME}</in>
    <out>{SOURCE_OUT_FRAME}</out>
    <pproTicksIn>{SOURCE_IN_TICKS}</pproTicksIn>
    <pproTicksOut>{SOURCE_OUT_TICKS}</pproTicksOut>
    <alphatype>none</alphatype>
    <pixelaspectratio>square</pixelaspectratio>
    <anamorphic>FALSE</anamorphic>
    <file id="file-1"/>  <!-- Reference to previously defined file -->
    <link>
        <linkclipref>clipitem-{VIDEO_ID}</linkclipref>
        <mediatype>video</mediatype>
        <trackindex>1</trackindex>
        <clipindex>{CLIP_NUMBER}</clipindex>
    </link>
    <link>
        <linkclipref>clipitem-{AUDIO1_ID}</linkclipref>
        <mediatype>audio</mediatype>
        <trackindex>1</trackindex>
        <clipindex>{CLIP_NUMBER}</clipindex>
    </link>
    <link>
        <linkclipref>clipitem-{AUDIO2_ID}</linkclipref>
        <mediatype>audio</mediatype>
        <trackindex>2</trackindex>
        <clipindex>{CLIP_NUMBER}</clipindex>
    </link>
    <labels>
        <label2>Iris</label2>
    </labels>
</clipitem>
```

### Audio Clipitem

```xml
<clipitem id="clipitem-{AUDIO_ID}" premiereChannelType="stereo">
    <masterclipid>masterclip-1</masterclipid>
    <name>Source Filename.mov</name>
    <enabled>TRUE</enabled>
    <duration>{SOURCE_TOTAL_DURATION_FRAMES}</duration>
    <rate>
        <timebase>24</timebase>
        <ntsc>TRUE</ntsc>
    </rate>
    <start>{TIMELINE_START_FRAME}</start>
    <end>{TIMELINE_END_FRAME}</end>
    <in>{SOURCE_IN_FRAME}</in>
    <out>{SOURCE_OUT_FRAME}</out>
    <pproTicksIn>{SOURCE_IN_TICKS}</pproTicksIn>
    <pproTicksOut>{SOURCE_OUT_TICKS}</pproTicksOut>
    <file id="file-1"/>
    <sourcetrack>
        <mediatype>audio</mediatype>
        <trackindex>{1_OR_2}</trackindex>
    </sourcetrack>
    <link>
        <linkclipref>clipitem-{VIDEO_ID}</linkclipref>
        <mediatype>video</mediatype>
        <trackindex>1</trackindex>
        <clipindex>{CLIP_NUMBER}</clipindex>
    </link>
    <link>
        <linkclipref>clipitem-{AUDIO_ID}</linkclipref>
        <mediatype>audio</mediatype>
        <trackindex>{THIS_TRACK}</trackindex>
        <clipindex>{CLIP_NUMBER}</clipindex>
    </link>
    <link>
        <linkclipref>clipitem-{OTHER_AUDIO_ID}</linkclipref>
        <mediatype>audio</mediatype>
        <trackindex>{OTHER_TRACK}</trackindex>
        <clipindex>{CLIP_NUMBER}</clipindex>
    </link>
</clipitem>
```

### Key Differences Between Video and Audio Clipitems

| Property | Video | Audio |
|----------|-------|-------|
| `premiereChannelType` | Not present | `"stereo"` |
| `<sourcetrack>` | Not present | Required (specifies which audio channel) |
| `<alphatype>` | `none` | Not present |
| `<pixelaspectratio>` | `square` | Not present |
| Links | Self + both audio | Video + self + other audio |

---

## The File Element (Source Media Reference)

The `<file>` element is defined in full **only once** (on the first clipitem that uses it). All subsequent clipitems reference it by ID with an empty self-closing tag.

### First occurrence (full definition):

```xml
<file id="file-1">
    <name>Solar Project Cut Down 1.mov</name>
    <pathurl>file://localhost/F%3a/Video/2026DDowell_Solar/Solar%20Project%20Cut%20Down%201.mov</pathurl>
    <rate>
        <timebase>24</timebase>
        <ntsc>TRUE</ntsc>
    </rate>
    <duration>39633</duration>
    <timecode>
        <rate>
            <timebase>24</timebase>
            <ntsc>TRUE</ntsc>
        </rate>
        <string>00:00:00:00</string>
        <frame>0</frame>
        <displayformat>NDF</displayformat>
    </timecode>
    <media>
        <video>
            <samplecharacteristics>
                <rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>
                <width>1920</width>
                <height>1080</height>
                <anamorphic>FALSE</anamorphic>
                <pixelaspectratio>square</pixelaspectratio>
                <fielddominance>none</fielddominance>
            </samplecharacteristics>
        </video>
        <audio>
            <samplecharacteristics>
                <depth>16</depth>
                <samplerate>48000</samplerate>
            </samplecharacteristics>
            <channelcount>2</channelcount>
        </audio>
    </media>
</file>
```

### Subsequent occurrences (reference only):

```xml
<file id="file-1"/>
```

### Path URL Format

The `<pathurl>` uses the `file://localhost/` protocol with URL-encoded paths:

| Character | Encoded |
|-----------|---------|
| `:` | `%3a` |
| Space | `%20` |
| `\` | `/` (forward slashes always) |

**Windows example:** `F:\Video\My Project\file.mov`
ƒ+' `file://localhost/F%3a/Video/My%20Project/file.mov`

**Mac example:** `/Volumes/Media/Project/file.mov`
ƒ+' `file://localhost/Volumes/Media/Project/file.mov`

---

## The Linking System

Every clip in Premiere (video + audio) is a group of linked clipitems. Each clipitem contains `<link>` elements that reference every other clipitem in the group, **including itself**.

### ID Scheme

For N cuts from a single source, you need 3N clipitem IDs:

```
Video clips:  1 through N
Audio L clips: N+1 through 2N
Audio R clips: 2N+1 through 3N
```

### Link Matrix for a Single Cut

For cut #1 (clipindex=1) with IDs video=1, audioL=7, audioR=13:

**Video clipitem-1 links:**
```xml
<link><linkclipref>clipitem-1</linkclipref><mediatype>video</mediatype><trackindex>1</trackindex><clipindex>1</clipindex></link>
<link><linkclipref>clipitem-7</linkclipref><mediatype>audio</mediatype><trackindex>1</trackindex><clipindex>1</clipindex></link>
<link><linkclipref>clipitem-13</linkclipref><mediatype>audio</mediatype><trackindex>2</trackindex><clipindex>1</clipindex></link>
```

**Audio L clipitem-7 links:**
```xml
<link><linkclipref>clipitem-1</linkclipref><mediatype>video</mediatype><trackindex>1</trackindex><clipindex>1</clipindex></link>
<link><linkclipref>clipitem-7</linkclipref><mediatype>audio</mediatype><trackindex>1</trackindex><clipindex>1</clipindex></link>
<link><linkclipref>clipitem-13</linkclipref><mediatype>audio</mediatype><trackindex>2</trackindex><clipindex>1</clipindex></link>
```

**Audio R clipitem-13 links:**
```xml
<link><linkclipref>clipitem-1</linkclipref><mediatype>video</mediatype><trackindex>1</trackindex><clipindex>1</clipindex></link>
<link><linkclipref>clipitem-7</linkclipref><mediatype>audio</mediatype><trackindex>1</trackindex><clipindex>1</clipindex></link>
<link><linkclipref>clipitem-13</linkclipref><mediatype>audio</mediatype><trackindex>2</trackindex><clipindex>1</clipindex></link>
```

All three have **identical** link blocks. This is what makes them behave as a single linked clip in Premiere.

---

## Timeline Position vs Source Position

This is the most important concept for programmatic sequence generation.

```
SOURCE (the .mov file):
|================================================================|
0                                                             39633 frames

CUT 1: frames 21899-22362 (from source)
CUT 2: frames 20904-21158 (from source)
CUT 3: frames 3504-3838 (from source)

TIMELINE (the sequence):
|------CUT 1------|--CUT 2--|----CUT 3----|
0               463       717          1051

Each clipitem has:
  in/out = SOURCE position (where in the .mov)
  start/end = TIMELINE position (where on the sequence)
```

### Calculation

```javascript
let timelinePosition = 0;

for (const cut of cuts) {
    const srcIn = tcToFrames(cut.tcIn);
    const srcOut = tcToFrames(cut.tcOut);
    const duration = srcOut - srcIn;

    clipitem.in = srcIn;
    clipitem.out = srcOut;
    clipitem.start = timelinePosition;
    clipitem.end = timelinePosition + duration;
    clipitem.pproTicksIn = framesToTicks(srcIn);
    clipitem.pproTicksOut = framesToTicks(srcOut);

    timelinePosition += duration; // Next clip starts where this one ends
}
```

---

## CEP Extension Architecture (Recommended)

### Option 1: CEP Panel with ExtendScript Backend

```
ƒ"Oƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?
ƒ",  CEP Panel (HTML/JS)            ƒ",
ƒ",  - Transcript viewer            ƒ",
ƒ",  - Bite selector UI             ƒ",
ƒ",  - Drag to reorder              ƒ",
ƒ",  - Generate XML button          ƒ",
ƒ",                                 ƒ",
ƒ",  ƒ"Oƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?  ƒ",
ƒ",  ƒ", ExtendScript Bridge       ƒ",  ƒ",
ƒ",  ƒ", - app.project.importFiles ƒ",  ƒ",
ƒ",  ƒ", - Get active sequence infoƒ",  ƒ",
ƒ",  ƒ", - Read project item props ƒ",  ƒ",
ƒ",  ƒ""ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"~  ƒ",
ƒ""ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"~
```

**ExtendScript can:**
- Import the generated XML directly: `app.project.importFiles([xmlPath])`
- Read source media properties (duration, framerate) from project items
- Get the file path of selected clips in the project panel
- Insert clips into an active sequence at the playhead

### Option 2: Standalone App + XML Import

```
ƒ"Oƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?     ƒ"Oƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?     ƒ"Oƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?
ƒ", Transcript Parser ƒ", ƒ"?ƒ"?ƒ+' ƒ", Bite Selector ƒ", ƒ"?ƒ"?ƒ+' ƒ", XML Generator ƒ",
ƒ", (SRT/VTT/TXT)    ƒ",     ƒ", (Web UI)      ƒ",     ƒ", (XMEML v4)    ƒ",
ƒ""ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"~     ƒ""ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"~     ƒ""ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"?ƒ"~
                                                       ƒ",
                                                       ƒ-¬
                                              File > Import in PPro
```

### Option 3: UXP Plugin (Modern ƒ?" Premiere Pro 2024+)

UXP (Unified Extensibility Platform) is Adobe's successor to CEP. If targeting newer Premiere versions, this is the recommended path. UXP plugins use modern JavaScript and have better API access.

---

## Handling Multiple Source Files

When working with multiple source media files, each gets its own `<file>` element with a unique ID:

```xml
<!-- First source -->
<file id="file-1">
    <name>Interview_A.mov</name>
    <pathurl>file://localhost/path/to/Interview_A.mov</pathurl>
    ...
</file>

<!-- Second source -->
<file id="file-2">
    <name>Interview_B.mov</name>
    <pathurl>file://localhost/path/to/Interview_B.mov</pathurl>
    ...
</file>
```

Each clipitem references its source via the file id and gets its own `masterclipid`:

```xml
<clipitem>
    <masterclipid>masterclip-1</masterclipid>  <!-- From Interview_A -->
    <file id="file-1"/>
    ...
</clipitem>
<clipitem>
    <masterclipid>masterclip-2</masterclipid>  <!-- From Interview_B -->
    <file id="file-2"/>
    ...
</clipitem>
```

---

## Common Frame Rates Quick Reference

| Format | Timebase | NTSC | Actual FPS | Ticks/Frame | Common Use |
|--------|----------|------|------------|-------------|------------|
| 23.976 | 24 | TRUE | 23.976 | 10,594,584,000 | Film, narrative |
| 24 | 24 | FALSE | 24.000 | 10,584,000,000 | True 24p |
| 25 | 25 | FALSE | 25.000 | 10,160,640,000 | PAL |
| 29.97 NDF | 30 | TRUE | 29.97 | 8,475,667,200 | NTSC broadcast |
| 30 | 30 | FALSE | 30.000 | 8,467,200,000 | Web |
| 59.94 | 60 | TRUE | 59.94 | 4,237,833,600 | NTSC HFR |
| 60 | 60 | FALSE | 60.000 | 4,233,600,000 | Web HFR |

---

## Transcript Parsing Notes

### Common Transcript Formats

**SRT:**
```
1
00:00:28:17 --> 00:00:55:17
You know, being in the early stages...
```

**Custom (as used in this project):**
```
00:00:28:17 - 00:00:55:17
Speaker 1
You know, being in the early stages...
```

**Whisper JSON:**
```json
{
  "segments": [
    { "start": 28.7, "end": 55.7, "text": "You know..." }
  ]
}
```

For any format, the parser needs to extract:
1. Start timecode
2. End timecode
3. Speaker label
4. Dialogue text

### AI Integration Point

The transcript + dialogue text is where an LLM (like Claude) adds value:
- Identify the best soundbites from raw transcript
- Categorize bites by purpose (hook, technical, emotional, CTA)
- Suggest multiple edit structures
- Generate the cut list with timecodes

This could be integrated via API call within the CEP panel or as a preprocessing step.

---

## Validation Checklist

Before importing, verify:

- [ ] XML is well-formed (parseable by any XML parser)
- [ ] `<file>` `pathurl` points to a valid, accessible media file
- [ ] `duration` on the file element matches the actual source duration in frames
- [ ] `in` < `out` for every clipitem
- [ ] `out - in` == `end - start` for every clipitem (source duration matches timeline duration)
- [ ] Timeline positions are sequential (no gaps, no overlaps): clip N's `end` == clip N+1's `start`
- [ ] `pproTicksIn` == `in * ticks_per_frame` and `pproTicksOut` == `out * ticks_per_frame`
- [ ] Every video clipitem has matching audio clipitems with identical `in/out/start/end`
- [ ] All link blocks are complete (video links to both audio; each audio links to video and both audio)
- [ ] `clipindex` values are sequential within each track (1, 2, 3, ...)
- [ ] `clipitem id` values are unique across the entire document
- [ ] Audio tracks have `currentExplodedTrackIndex` of 0 and 1 respectively
- [ ] `<file>` is fully defined on first use, then referenced as `<file id="file-1"/>` thereafter

---

## Sample Minimal Sequence (Single Cut)

This is the absolute minimum XML to get a single clip onto a Premiere timeline:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
    <sequence id="sequence-1" explodedTracks="true">
        <uuid>00000000-0000-0000-0000-000000000001</uuid>
        <duration>240</duration>
        <rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>
        <name>Minimal Test</name>
        <media>
            <video>
                <format>
                    <samplecharacteristics>
                        <rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>
                        <width>1920</width>
                        <height>1080</height>
                        <anamorphic>FALSE</anamorphic>
                        <pixelaspectratio>square</pixelaspectratio>
                        <fielddominance>none</fielddominance>
                        <colordepth>24</colordepth>
                    </samplecharacteristics>
                </format>
                <track>
                    <clipitem id="clipitem-1">
                        <masterclipid>masterclip-1</masterclipid>
                        <name>source.mov</name>
                        <enabled>TRUE</enabled>
                        <duration>10000</duration>
                        <rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>
                        <start>0</start>
                        <end>240</end>
                        <in>0</in>
                        <out>240</out>
                        <pproTicksIn>0</pproTicksIn>
                        <pproTicksOut>2542700160000</pproTicksOut>
                        <file id="file-1">
                            <name>source.mov</name>
                            <pathurl>file://localhost/path/to/source.mov</pathurl>
                            <rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>
                            <duration>10000</duration>
                            <media>
                                <video>
                                    <samplecharacteristics>
                                        <rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>
                                        <width>1920</width>
                                        <height>1080</height>
                                    </samplecharacteristics>
                                </video>
                                <audio>
                                    <samplecharacteristics>
                                        <depth>16</depth>
                                        <samplerate>48000</samplerate>
                                    </samplecharacteristics>
                                    <channelcount>2</channelcount>
                                </audio>
                            </media>
                        </file>
                        <link>
                            <linkclipref>clipitem-1</linkclipref>
                            <mediatype>video</mediatype>
                            <trackindex>1</trackindex>
                            <clipindex>1</clipindex>
                        </link>
                        <link>
                            <linkclipref>clipitem-2</linkclipref>
                            <mediatype>audio</mediatype>
                            <trackindex>1</trackindex>
                            <clipindex>1</clipindex>
                        </link>
                        <link>
                            <linkclipref>clipitem-3</linkclipref>
                            <mediatype>audio</mediatype>
                            <trackindex>2</trackindex>
                            <clipindex>1</clipindex>
                        </link>
                    </clipitem>
                </track>
            </video>
            <audio>
                <numOutputChannels>1</numOutputChannels>
                <format>
                    <samplecharacteristics>
                        <depth>16</depth>
                        <samplerate>48000</samplerate>
                    </samplecharacteristics>
                </format>
                <outputs>
                    <group><index>1</index><numchannels>1</numchannels><downmix>0</downmix><channel><index>1</index></channel></group>
                    <group><index>2</index><numchannels>1</numchannels><downmix>0</downmix><channel><index>2</index></channel></group>
                </outputs>
                <track premiereTrackType="Mono" currentExplodedTrackIndex="0" totalExplodedTrackCount="2">
                    <clipitem id="clipitem-2" premiereChannelType="stereo">
                        <masterclipid>masterclip-1</masterclipid>
                        <name>source.mov</name>
                        <enabled>TRUE</enabled>
                        <duration>10000</duration>
                        <rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>
                        <start>0</start><end>240</end>
                        <in>0</in><out>240</out>
                        <pproTicksIn>0</pproTicksIn>
                        <pproTicksOut>2542700160000</pproTicksOut>
                        <file id="file-1"/>
                        <sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>
                        <link><linkclipref>clipitem-1</linkclipref><mediatype>video</mediatype><trackindex>1</trackindex><clipindex>1</clipindex></link>
                        <link><linkclipref>clipitem-2</linkclipref><mediatype>audio</mediatype><trackindex>1</trackindex><clipindex>1</clipindex></link>
                        <link><linkclipref>clipitem-3</linkclipref><mediatype>audio</mediatype><trackindex>2</trackindex><clipindex>1</clipindex></link>
                    </clipitem>
                </track>
                <track premiereTrackType="Mono" currentExplodedTrackIndex="1" totalExplodedTrackCount="2">
                    <clipitem id="clipitem-3" premiereChannelType="stereo">
                        <masterclipid>masterclip-1</masterclipid>
                        <name>source.mov</name>
                        <enabled>TRUE</enabled>
                        <duration>10000</duration>
                        <rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>
                        <start>0</start><end>240</end>
                        <in>0</in><out>240</out>
                        <pproTicksIn>0</pproTicksIn>
                        <pproTicksOut>2542700160000</pproTicksOut>
                        <file id="file-1"/>
                        <sourcetrack><mediatype>audio</mediatype><trackindex>2</trackindex></sourcetrack>
                        <link><linkclipref>clipitem-1</linkclipref><mediatype>video</mediatype><trackindex>1</trackindex><clipindex>1</clipindex></link>
                        <link><linkclipref>clipitem-2</linkclipref><mediatype>audio</mediatype><trackindex>1</trackindex><clipindex>1</clipindex></link>
                        <link><linkclipref>clipitem-3</linkclipref><mediatype>audio</mediatype><trackindex>2</trackindex><clipindex>1</clipindex></link>
                    </clipitem>
                </track>
            </audio>
        </media>
    </sequence>
</xmeml>
```

---

## Known Limitations and Gotchas

1. **Premiere may relink media** ƒ?" If the source file has moved, Premiere will prompt for relink on import. The `pathurl` must be accurate at import time.

2. **No transitions in XMEML v4** ƒ?" Cross-dissolves and other transitions cannot be reliably defined in the XML. Add them manually after import.

3. **No effects/color** ƒ?" LUTs, color corrections, and video effects are not portable via XMEML. These are Premiere-specific and must be applied after import.

4. **Markers are possible but fragile** ƒ?" Sequence markers can be added via `<marker>` elements but support is inconsistent across Premiere versions.

5. **Drop-frame timecode** ƒ?" If your source uses DF timecode (29.97 DF), the frame calculation changes. This document assumes NDF throughout.

6. **Multi-cam** ƒ?" XMEML v4 does not support multicam sequence definitions. Use Premiere's native multicam tools after import.

7. **Nested sequences** ƒ?" Theoretically possible by defining multiple `<sequence>` elements and referencing them, but not tested in this workflow.

8. **Maximum clip count** ƒ?" No hard limit found, but very large sequences (500+ clips) may slow down the import process.

