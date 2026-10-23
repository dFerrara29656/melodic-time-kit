# melodic-time-kit

Maps clock time to musical tempo and measure positions. Given a tempo, time signature, and a wall-clock anchor, it tells you which measure and beat you are on, right now, plus the fractional position within that beat.

```python
from melodic_time_kit import MusicalClock
import time

clock = MusicalClock(
    beats_per_minute=120.0,
    beats_per_measure=4,
    anchor_seconds=time.monotonic(),  # treat "now" as the downbeat of measure 0
    now=time.monotonic,
)

pos = clock.position()
print(pos.measure)            # 0
print(pos.beat_in_measure)    # 1..4
print(pos.fraction_of_beat)   # 0.0..1.0
print(pos.phase)              # alias for fraction_of_beat
```

## Why this exists

Live audio software often needs to know "where in the score am I, given a wall-clock reading?" This library answers that one question and nothing else. It does not generate MIDI, it does not schedule notes, and it does not manage transport state. The trade-off is simplicity: the mapping is a single division plus a modulo, so it is cheap to call from a real-time callback. The cost is that it is stateless with respect to tempo changes mid-song — if your tempo ramps, you must re-anchor at each segment boundary and the library will not stitch the segments for you.

## The awkward edge

`beat_in_measure` is 1-based (musicians count "beat 1"), while `measure`, `absolute_beat`, and `fraction_of_beat` are 0-based. This is deliberate and consistent within the library, but it means you cannot mix `beat_in_measure` into arithmetic with the other fields without shifting by one. Negative positions (before the anchor) are supported and produce negative `absolute_beat` and `measure` values, so a count-off before the downbeat maps sensibly.
