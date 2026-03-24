"""
Timecode, frame, and Premiere Pro tick conversion utilities.

Supports NDF timecode at any standard timebase.
Premiere Pro internal tick rate: 254,016,000,000 ticks/second.
"""

PREMIERE_TICK_RATE = 254016000000  # ticks per second, constant across all framerates


def tc_to_frames(tc: str, timebase: int = 24) -> int:
    """
    Convert NDF timecode string to frame number.

    Args:
        tc: Timecode string in "HH:MM:SS:FF" format
        timebase: Frames per second (before NTSC pulldown). E.g. 24, 30, 60.

    Returns:
        Frame number (0-indexed)
    """
    parts = tc.strip().split(":")
    if len(parts) != 4:
        raise ValueError(f"Invalid timecode format '{tc}', expected HH:MM:SS:FF")

    hh, mm, ss, ff = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])

    if ff >= timebase:
        raise ValueError(f"Frame value {ff} exceeds timebase {timebase} in TC '{tc}'")
    if ss >= 60 or mm >= 60:
        raise ValueError(f"Invalid timecode values in '{tc}'")

    return (hh * 3600 * timebase) + (mm * 60 * timebase) + (ss * timebase) + ff


def frames_to_tc(frames: int, timebase: int = 24) -> str:
    """
    Convert frame number to NDF timecode string.

    Args:
        frames: Frame number (0-indexed)
        timebase: Frames per second (before NTSC pulldown)

    Returns:
        Timecode string in "HH:MM:SS:FF" format
    """
    if frames < 0:
        raise ValueError(f"Frame number cannot be negative: {frames}")

    ff = frames % timebase
    total_seconds = frames // timebase
    ss = total_seconds % 60
    total_minutes = total_seconds // 60
    mm = total_minutes % 60
    hh = total_minutes // 60

    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def normalize_timecode(tc: str, timebase: int = 24) -> str:
    """
    Normalize a timecode by converting to frames and back.

    Useful for deterministic fixtures where round-trip consistency is required.
    """
    return frames_to_tc(tc_to_frames(tc, timebase), timebase)


def ticks_per_frame(timebase: int = 24, ntsc: bool = True) -> int:
    """
    Calculate Premiere Pro ticks per frame for a given rate.

    Args:
        timebase: Nominal frame rate (24, 30, 60, etc.)
        ntsc: If True, actual fps = timebase * 1000/1001

    Returns:
        Integer ticks per frame
    """
    if ntsc:
        # ticks_per_frame = tick_rate * 1001 / (timebase * 1000)
        return (PREMIERE_TICK_RATE * 1001) // (timebase * 1000)
    else:
        return PREMIERE_TICK_RATE // timebase


def frames_to_ticks(frames: int, timebase: int = 24, ntsc: bool = True) -> int:
    """
    Convert frame number to Premiere Pro ticks.

    Args:
        frames: Frame number
        timebase: Nominal frame rate
        ntsc: NTSC pulldown flag

    Returns:
        pproTicks value
    """
    return frames * ticks_per_frame(timebase, ntsc)


def estimate_duration_seconds(tc_in: str, tc_out: str,
                               timebase: int = 24, ntsc: bool = True) -> float:
    """
    Estimate real-time duration between two timecodes in seconds.

    Args:
        tc_in: Start timecode
        tc_out: End timecode
        timebase: Nominal frame rate
        ntsc: NTSC pulldown flag

    Returns:
        Duration in seconds (float)
    """
    frame_in = tc_to_frames(tc_in, timebase)
    frame_out = tc_to_frames(tc_out, timebase)
    frame_count = frame_out - frame_in

    if frame_count < 0:
        raise ValueError(f"tc_out ({tc_out}) is before tc_in ({tc_in})")

    if ntsc:
        actual_fps = timebase * 1000 / 1001
    else:
        actual_fps = float(timebase)

    return frame_count / actual_fps


# Quick reference: common ticks-per-frame values
COMMON_RATES = {
    (24, True):  10594584000,   # 23.976fps - film/narrative
    (24, False): 10584000000,   # 24fps - true 24p
    (25, False): 10160640000,   # 25fps - PAL
    (30, True):  8475667200,    # 29.97fps - NTSC broadcast
    (30, False): 8467200000,    # 30fps - web
    (60, True):  4237833600,    # 59.94fps - NTSC HFR
    (60, False): 4233600000,    # 60fps - web HFR
}
