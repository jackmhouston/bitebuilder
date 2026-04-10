import unittest

from generator.timecode import (
    COMMON_RATES,
    estimate_duration_seconds,
    frames_to_tc,
    frames_to_ticks,
    normalize_timecode,
    tc_to_frames,
    ticks_per_frame,
)


class TimecodeConversionTests(unittest.TestCase):
    def test_tc_to_frames_standard_offsets(self):
        self.assertEqual(tc_to_frames("00:00:00:00", timebase=24), 0)
        self.assertEqual(tc_to_frames("00:00:01:00", timebase=24), 24)
        self.assertEqual(tc_to_frames("00:01:00:00", timebase=30), 1800)
        self.assertEqual(tc_to_frames("01:00:00:00", timebase=24), 86400)

    def test_frames_to_tc_standard_offsets(self):
        self.assertEqual(frames_to_tc(0, timebase=24), "00:00:00:00")
        self.assertEqual(frames_to_tc(24, timebase=24), "00:00:01:00")
        self.assertEqual(frames_to_tc(1800, timebase=30), "00:01:00:00")
        self.assertEqual(frames_to_tc(86400, timebase=24), "01:00:00:00")

    def test_frames_to_tc_rejects_negative_frames(self):
        with self.assertRaisesRegex(ValueError, "negative"):
            frames_to_tc(-1, timebase=24)

    def test_normalize_timecode_round_trips_valid_input(self):
        self.assertEqual(normalize_timecode("00:01:02:03", timebase=24), "00:01:02:03")

    def test_tc_to_frames_rejects_malformed_timecode(self):
        with self.assertRaisesRegex(ValueError, "Invalid timecode format"):
            tc_to_frames("00:00:00", timebase=24)

    def test_tc_to_frames_rejects_frame_at_or_above_timebase(self):
        with self.assertRaisesRegex(ValueError, "exceeds timebase"):
            tc_to_frames("00:00:00:24", timebase=24)

    def test_tc_to_frames_rejects_invalid_second_or_minute_values(self):
        with self.assertRaisesRegex(ValueError, "Invalid timecode values"):
            tc_to_frames("00:00:60:00", timebase=24)
        with self.assertRaisesRegex(ValueError, "Invalid timecode values"):
            tc_to_frames("00:60:00:00", timebase=24)


class PremiereTickTests(unittest.TestCase):
    def test_common_rate_tick_values_are_locked(self):
        for (timebase, ntsc), expected_ticks in COMMON_RATES.items():
            with self.subTest(timebase=timebase, ntsc=ntsc):
                self.assertEqual(ticks_per_frame(timebase, ntsc), expected_ticks)

    def test_frames_to_ticks_multiplies_by_rate_specific_ticks(self):
        self.assertEqual(
            frames_to_ticks(10, timebase=30, ntsc=False),
            10 * COMMON_RATES[(30, False)],
        )
        self.assertEqual(frames_to_ticks(10, timebase=30, ntsc=True), 10 * COMMON_RATES[(30, True)])


class DurationEstimateTests(unittest.TestCase):
    def test_estimates_non_ntsc_duration_seconds(self):
        self.assertEqual(
            estimate_duration_seconds("00:00:00:00", "00:00:01:00", timebase=24, ntsc=False),
            1.0,
        )

    def test_estimates_ntsc_duration_seconds(self):
        self.assertAlmostEqual(
            estimate_duration_seconds("00:00:00:00", "00:00:01:00", timebase=30, ntsc=True),
            1.001,
            places=6,
        )

    def test_rejects_reversed_ranges(self):
        with self.assertRaisesRegex(ValueError, "before tc_in"):
            estimate_duration_seconds("00:00:02:00", "00:00:01:00", timebase=24, ntsc=False)


if __name__ == "__main__":
    unittest.main()
