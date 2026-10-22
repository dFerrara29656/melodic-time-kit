"""Core mapping between wall-clock seconds and musical position.

Design decisions (stated plainly so callers know exactly what they get):

* Time anchors are *beat* boundaries, not measure boundaries.  An anchor at
  beat 3 of measure 7 with a 4/4 signature means the wall clock was at
  ``anchor_seconds`` when beat 0 of measure 7 had elapsed by 2 beats.  This
  keeps the math a single division and avoids per-measure lookup tables, which
  matters when the caller is doing this in a real-time audio thread.

* ``beats_per_minute`` may be any positive float.  Groove grids with fractional
  tempos (e.g. 87.3 BPM for a tape-slow-down effect) are common; clamping to
  integers would silently mangle them.

* Negative anchors or negative tempos are rejected outright.  Time can be
  negative in some runtimes (pre-roll), but allowing it here would make the
  modulo arithmetic branch in ways the caller almost never wants.  If you need
  pre-roll, shift the anchor forward by the pre-roll amount.

* Positions are immutable so callers can cache the current position without
  worrying about aliasing.
"""

from dataclasses import dataclass
from typing import Callable


def _validate_positive(name: str, value: float) -> float:
    """Reject NaN and non-positive values early.

    NaN is contagious: once it enters the beat calculation every downstream
    field becomes NaN, and a *test* that checks ``position.beat`` would pass
    on ``math.isnan`` but a real consumer would get garbage.  Fail fast
    instead.
    """
    # ``value != value`` is the canonical NaN check that does not require the
    # math module and works on any float-like.
    if value != value:  # NaN
        raise ValueError(f"{name} must be a number, got {value!r}")
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value!r}")
    return float(value)


@dataclass(frozen=True)
class Position:
    """Immutable musical position derived from a wall-clock instant.

    ``absolute_beat`` is the continuous, zero-based beat count since the
    anchor.  ``measure``, ``beat_in_measure`` (1-based), and
    ``fraction_of_beat`` are the broken-out forms callers usually want.

    ``beat_in_measure`` is 1-based because musicians count "beat 1, beat 2",
    not "beat 0".  Every other field is 0-based to keep arithmetic simple.
    """
    seconds_per_beat: float
    absolute_beat: float
    measure: int
    beat_in_measure: int
    fraction_of_beat: float

    @property
    def phase(self) -> float:
        """Position within the current beat as a 0..1 float.

        Convenient for LFO phase locking: multiply by ``2 * math.pi`` to get
        a sine phase.  Kept as a property rather than a field so it cannot
        drift out of sync with ``fraction_of_beat``.
        """
        return self.fraction_of_beat


class MusicalClock:
    """Maps wall-clock seconds to musical tempo and measure positions.

    Parameters
    ----------
    beats_per_minute:
        Tempo.  Must be positive.  Floats welcome.
    beats_per_measure:
        Numerator of the time signature (e.g. 4 for 4/4, 3 for 3/4, 7 for
        7/8).  Must be a positive integer.
    anchor_seconds:
        Wall-clock value, in seconds, at which ``beat 0 of measure 0`` was
        true.  Defaults to 0.0 (i.e. the epoch is the downbeat).
    now:
        Callable returning the current wall-clock seconds as a float.
        Injecting the clock makes the class deterministic and testable
        without sleeping.
    """

    def __init__(
        self,
        beats_per_minute: float,
        beats_per_measure: int = 4,
        *,
        anchor_seconds: float = 0.0,
        now: Callable[[], float] | None = None,
    ) -> None:
        self.beats_per_minute = _validate_positive(
            "beats_per_minute", beats_per_minute
        )
        if beats_per_measure <= 0:
            raise ValueError(
                f"beats_per_measure must be positive, got {beats_per_measure!r}"
            )
        self.beats_per_measure = int(beats_per_measure)

        # Anchor can be 0 or positive.  Negative anchors are rejected (see
        # module docstring) but we still need the NaN guard for 0.0, which is
        # a valid default.
        if anchor_seconds != anchor_seconds:
            raise ValueError(
                f"anchor_seconds must be a number, got {anchor_seconds!r}"
            )
        self.anchor_seconds = float(anchor_seconds)

        # seconds_per_beat = 60 / BPM.  Storing the reciprocal avoids a
        # division on every ``position()`` call, which can be hot in a DAW.
        self.seconds_per_beat = 60.0 / self.beats_per_minute

        # ``time.monotonic`` is the right default: it is immune to wall-clock
        # adjustments (NTP slews, manual changes) and always increases.
        # Callers who want the Unix epoch can pass ``time.time``.
        import time

        self._now = now if now is not None else time.monotonic

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------
    def position_at(self, seconds: float) -> Position:
        """Return the musical position for a specific wall-clock value."""
        if seconds != seconds:
            raise ValueError(f"seconds must be a number, got {seconds!r}")

        elapsed = seconds - self.anchor_seconds
        # Elapsed can be negative (we are before the anchor downbeat).  That is
        # a legitimate musical state — a count-off — so we do not reject it.
        # The floor and modulo math below handles negatives correctly.
        absolute_beat = elapsed / self.seconds_per_beat

        full_beats = int(absolute_beat)  # floor for negatives too
        fraction = absolute_beat - full_beats
        # Guarantee fraction is in [0, 1) even after float wobble.
        if fraction < 0.0:
            fraction += 1.0
            full_beats -= 1
        elif fraction >= 1.0:
            fraction -= 1.0
            full_beats += 1

        measure = full_beats // self.beats_per_measure
        beat_in_measure = full_beats - measure * self.beats_per_measure

        return Position(
            seconds_per_beat=self.seconds_per_beat,
            absolute_beat=absolute_beat,
            measure=measure,
            beat_in_measure=beat_in_measure + 1,  # 1-based for musicians
            fraction_of_beat=fraction,
        )

    def position(self) -> Position:
        """Return the musical position for the current wall-clock instant."""
        return self.position_at(self._now())

    def beat_duration_seconds(self) -> float:
        """Seconds per beat.  Exposed for scheduling."""
        return self.seconds_per_beat

    def measure_duration_seconds(self) -> float:
        """Seconds per measure = seconds_per_beat * beats_per_measure."""
        return self.seconds_per_beat * self.beats_per_measure
