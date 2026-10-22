"""Unit tests for melodic-time-kit core.

The clock is injected so no test ever touches wall time.
"""

import math
import unittest

from melodic_time_kit import MusicalClock, Position


class _FakeClock:
    """Deterministic clock for tests."""

    def __init__(self, t=0.0):
        self.t = float(t)

    def __call__(self):
        return self.t


class TestConstruction(unittest.TestCase):
    def test_defaults(self):
        c = MusicalClock(120.0)
        self.assertEqual(c.beats_per_minute, 120.0)
        self.assertEqual(c.beats_per_measure, 4)
        self.assertEqual(c.anchor_seconds, 0.0)

    def test_explicit_fields(self):
        fake = _FakeClock()
        c = MusicalClock(90.0, beats_per_measure=7, anchor_seconds=10.0, now=fake)
        self.assertEqual(c.beats_per_measure, 7)
        self.assertEqual(c.anchor_seconds, 10.0)
        self.assertIs(c._now, fake)

    def test_bpm_must_be_positive(self):
        for bad in (0, -1, -0.001):
            with self.assertRaises(ValueError):
                MusicalClock(bad)

    def test_nan_bpm_rejected(self):
        with self.assertRaises(ValueError):
            MusicalClock(float("nan"))

    def test_beats_per_measure_must_be_positive(self):
        with self.assertRaises(ValueError):
            MusicalClock(120, beats_per_measure=0)

    def test_nan_anchor_rejected(self):
        with self.assertRaises(ValueError):
            MusicalClock(120, anchor_seconds=float("nan"))

    def test_fractional_bpm_allowed(self):
        c = MusicalClock(87.3)
        self.assertAlmostEqual(c.beat_duration_seconds(), 60.0 / 87.3, places=10)


class TestPositionAt(unittest.TestCase):
    def test_anchor_is_downbeat(self):
        c = MusicalClock(120, beats_per_measure=4, anchor_seconds=100.0)
        p = c.position_at(100.0)
        self.assertEqual(p.measure, 0)
        self.assertEqual(p.beat_in_measure, 1)
        self.assertEqual(p.absolute_beat, 0.0)
        self.assertEqual(p.fraction_of_beat, 0.0)

    def test_one_beat_later(self):
        c = MusicalClock(120, beats_per_measure=4, anchor_seconds=0.0)
        # 120 BPM => 0.5 s/beat
        p = c.position_at(0.5)
        self.assertEqual(p.measure, 0)
        self.assertEqual(p.beat_in_measure, 2)
        self.assertEqual(p.absolute_beat, 1.0)
        self.assertEqual(p.fraction_of_beat, 0.0)

    def test_crossing_measure_boundary(self):
        c = MusicalClock(120, beats_per_measure=4, anchor_seconds=0.0)
        # 2.0 s = 4 beats = exactly one measure
        p = c.position_at(2.0)
        self.assertEqual(p.measure, 1)
        self.assertEqual(p.beat_in_measure, 1)
        self.assertEqual(p.absolute_beat, 4.0)
        self.assertEqual(p.fraction_of_beat, 0.0)

    def test_fractional_beat(self):
        c = MusicalClock(120, beats_per_measure=4, anchor_seconds=0.0)
        # 0.75 s = 1.5 beats
        p = c.position_at(0.75)
        self.assertEqual(p.beat_in_measure, 2)
        self.assertAlmostEqual(p.fraction_of_beat, 0.5, places=10)
        self.assertEqual(p.phase, p.fraction_of_beat)

    def test_mid_measure_odd_time(self):
        c = MusicalClock(60, beats_per_measure=7, anchor_seconds=0.0)
        # 60 BPM => 1 s/beat. 8 s = beat 8 = beat 2 of measure 2 (0-indexed beat 7)
        p = c.position_at(8.0)
        self.assertEqual(p.measure, 1)
        self.assertEqual(p.beat_in_measure, 2)
        self.assertEqual(p.absolute_beat, 8.0)

    def test_before_anchor_is_negative_absolute_beat(self):
        c = MusicalClock(120, beats_per_measure=4, anchor_seconds=10.0)
        # 1 second before anchor => -2 beats => measure -1, beat 3 (1-based)
        p = c.position_at(9.0)
        self.assertEqual(p.absolute_beat, -2.0)
        self.assertEqual(p.measure, -1)
        self.assertEqual(p.beat_in_measure, 3)
        self.assertEqual(p.fraction_of_beat, 0.0)

    def test_nan_seconds_rejected(self):
        c = MusicalClock(120)
        with self.assertRaises(ValueError):
            c.position_at(float("nan"))

    def test_returns_position_type(self):
        c = MusicalClock(120)
        self.assertIsInstance(c.position_at(0.0), Position)


class TestNowInjection(unittest.TestCase):
    def test_position_uses_injected_clock(self):
        fake = _FakeClock(3.0)
        c = MusicalClock(120, beats_per_measure=4, anchor_seconds=0.0, now=fake)
        p = c.position()
        # 3.0 s @ 120 BPM = 6 beats = measure 1, beat 3 (1-based, since 4+2)
        self.assertEqual(p.measure, 1)
        self.assertEqual(p.beat_in_measure, 3)

    def test_advancing_clock_advances_position(self):
        fake = _FakeClock(0.0)
        c = MusicalClock(120, beats_per_measure=4, now=fake)
        self.assertEqual(c.position().absolute_beat, 0.0)
        fake.t = 1.5
        self.assertEqual(c.position().absolute_beat, 3.0)


class TestDurations(unittest.TestCase):
    def test_beat_duration(self):
        c = MusicalClock(120)
        self.assertAlmostEqual(c.beat_duration_seconds(), 0.5, places=10)

    def test_measure_duration(self):
        c = MusicalClock(120, beats_per_measure=4)
        self.assertAlmostEqual(c.measure_duration_seconds(), 2.0, places=10)


class TestImmutability(unittest.TestCase):
    def test_position_is_frozen(self):
        c = MusicalClock(120)
        p = c.position_at(1.0)
        with self.assertRaises(Exception):
            p.measure = 999  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
