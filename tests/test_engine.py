"""
Tests for MetronomeEngine (metronome/engine.py).

Strategy:
- State/setter tests: inspect private attrs (no thread needed).
- Beat-pattern tests: spin the real thread at BPM 300 and collect callbacks
  via threading.Event, then assert on the (beat_index, is_accent, is_sub)
  sequence.
- Timing test: verify approximate interval consistency at max BPM.
"""

import threading
import time

import pytest

from metronome.engine import MetronomeEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect(n: int, *, bpm: float = 300, beats: int = 4, sub: int = 1,
             timeout: float = 5.0) -> list[tuple[int, bool, bool]]:
    """Run engine and return the first *n* callback invocations."""
    calls: list[tuple[int, bool, bool]] = []
    done = threading.Event()

    def cb(beat_index: int, is_accent: bool, is_sub: bool) -> None:
        if len(calls) < n:  # guard: ignore surplus callbacks after done
            calls.append((beat_index, is_accent, is_sub))
        if len(calls) >= n:
            done.set()

    engine = MetronomeEngine(cb)
    engine.set_bpm(bpm)
    engine.set_time_signature(beats, 4)
    engine.set_subdivision(sub)
    engine.start()
    done.wait(timeout=timeout)
    engine.stop()
    return calls


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestInit:
    def test_not_running_initially(self):
        e = MetronomeEngine(lambda *_: None)
        assert not e.is_running

    def test_default_bpm(self):
        e = MetronomeEngine(lambda *_: None)
        assert e._bpm == 120.0

    def test_default_beats_per_measure(self):
        e = MetronomeEngine(lambda *_: None)
        assert e._beats_per_measure == 4

    def test_default_subdivision(self):
        e = MetronomeEngine(lambda *_: None)
        assert e._subdivision == 1

    def test_no_reset_pending_initially(self):
        e = MetronomeEngine(lambda *_: None)
        assert e._reset_pending is False

    def test_callback_stored(self):
        cb = lambda *_: None
        e = MetronomeEngine(cb)
        assert e._callback is cb


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:
    def test_start_sets_running(self):
        e = MetronomeEngine(lambda *_: None)
        e.start()
        try:
            assert e.is_running
        finally:
            e.stop()

    def test_stop_clears_running(self):
        e = MetronomeEngine(lambda *_: None)
        e.start()
        e.stop()
        assert not e.is_running

    def test_stop_when_never_started_is_safe(self):
        e = MetronomeEngine(lambda *_: None)
        e.stop()  # must not raise
        assert not e.is_running

    def test_double_start_is_idempotent(self):
        """Second start() while already running must not spawn a new thread."""
        e = MetronomeEngine(lambda *_: None)
        e.start()
        first = e._thread
        e.start()
        try:
            assert e._thread is first
        finally:
            e.stop()

    def test_restart_after_stop(self):
        e = MetronomeEngine(lambda *_: None)
        e.start()
        e.stop()
        e.start()
        try:
            assert e.is_running
        finally:
            e.stop()

    def test_thread_is_daemon(self):
        """Daemon thread must not prevent process exit."""
        e = MetronomeEngine(lambda *_: None)
        e.start()
        try:
            assert e._thread.daemon is True
        finally:
            e.stop()

    def test_thread_is_none_after_stop(self):
        e = MetronomeEngine(lambda *_: None)
        e.start()
        e.stop()
        assert e._thread is None


# ---------------------------------------------------------------------------
# set_bpm
# ---------------------------------------------------------------------------

class TestSetBpm:
    def test_set_valid_bpm(self):
        e = MetronomeEngine(lambda *_: None)
        e.set_bpm(150.0)
        assert e._bpm == 150.0

    def test_clamp_below_minimum(self):
        e = MetronomeEngine(lambda *_: None)
        e.set_bpm(1.0)
        assert e._bpm == 30.0

    def test_clamp_above_maximum(self):
        e = MetronomeEngine(lambda *_: None)
        e.set_bpm(999.0)
        assert e._bpm == 300.0

    def test_boundary_minimum(self):
        e = MetronomeEngine(lambda *_: None)
        e.set_bpm(30.0)
        assert e._bpm == 30.0

    def test_boundary_maximum(self):
        e = MetronomeEngine(lambda *_: None)
        e.set_bpm(300.0)
        assert e._bpm == 300.0

    def test_float_value_preserved(self):
        e = MetronomeEngine(lambda *_: None)
        e.set_bpm(142.857)
        assert e._bpm == pytest.approx(142.857)


# ---------------------------------------------------------------------------
# set_time_signature
# ---------------------------------------------------------------------------

class TestSetTimeSignature:
    def test_numerator_stored(self):
        e = MetronomeEngine(lambda *_: None)
        e.set_time_signature(3, 4)
        assert e._beats_per_measure == 3

    def test_6_8_numerator(self):
        e = MetronomeEngine(lambda *_: None)
        e.set_time_signature(6, 8)
        assert e._beats_per_measure == 6

    def test_sets_reset_pending(self):
        e = MetronomeEngine(lambda *_: None)
        e._reset_pending = False
        e.set_time_signature(2, 4)
        assert e._reset_pending is True

    def test_denominator_not_stored_separately(self):
        """Engine only uses the numerator for beat cycling."""
        e = MetronomeEngine(lambda *_: None)
        e.set_time_signature(5, 8)
        assert e._beats_per_measure == 5


# ---------------------------------------------------------------------------
# set_subdivision
# ---------------------------------------------------------------------------

class TestSetSubdivision:
    @pytest.mark.parametrize("sub", [1, 2, 3, 4])
    def test_stores_subdivision(self, sub):
        e = MetronomeEngine(lambda *_: None)
        e.set_subdivision(sub)
        assert e._subdivision == sub


# ---------------------------------------------------------------------------
# Beat-pattern correctness
# ---------------------------------------------------------------------------

class TestBeatPattern:
    def test_callbacks_are_called(self):
        calls = _collect(4)
        assert len(calls) == 4

    def test_first_callback_is_accent_on_beat_0(self):
        calls = _collect(1)
        beat_index, is_accent, is_sub = calls[0]
        assert beat_index == 0
        assert is_accent is True
        assert is_sub is False

    # ---- beat_index cycling ----

    @pytest.mark.parametrize("beats", [2, 3, 4, 6])
    def test_beat_index_never_exceeds_beats_minus_1(self, beats):
        calls = _collect(beats * 3, beats=beats)
        for idx, _, _ in calls:
            assert idx < beats

    @pytest.mark.parametrize("beats", [2, 3, 4, 6])
    def test_beat_index_starts_at_zero(self, beats):
        calls = _collect(beats * 3, beats=beats)
        assert calls[0][0] == 0

    def test_4_4_index_sequence(self):
        calls = _collect(8, beats=4, sub=1)
        indices = [c[0] for c in calls]
        # first full measure must be 0,1,2,3 in order
        assert indices[:4] == [0, 1, 2, 3]
        assert indices[4:8] == [0, 1, 2, 3]

    def test_3_4_index_sequence(self):
        calls = _collect(6, beats=3, sub=1)
        assert [c[0] for c in calls] == [0, 1, 2, 0, 1, 2]

    def test_2_4_index_sequence(self):
        calls = _collect(4, beats=2, sub=1)
        assert [c[0] for c in calls] == [0, 1, 0, 1]

    # ---- is_accent ----

    def test_only_beat_0_is_accent_quarter_notes(self):
        calls = _collect(8, beats=4, sub=1)
        for beat_index, is_accent, _ in calls:
            assert is_accent == (beat_index == 0)

    def test_accent_only_on_downbeat_sixteenth(self):
        # sub=4: accent must coincide with beat_index==0 AND sub_count%4==0
        calls = _collect(16, beats=4, sub=4)
        for beat_index, is_accent, is_sub in calls:
            if is_accent:
                assert beat_index == 0
                assert is_sub is False

    # ---- is_sub ----

    def test_no_subs_in_quarter_note_mode(self):
        calls = _collect(8, beats=4, sub=1)
        assert all(not is_sub for _, _, is_sub in calls)

    def test_eighth_note_alternates_beat_sub(self):
        """sub=2: even positions are beats, odd are subs."""
        calls = _collect(8, beats=4, sub=2)
        for i, (_, _, is_sub) in enumerate(calls):
            assert is_sub == (i % 2 == 1), f"position {i}: is_sub={is_sub}"

    def test_triplet_pattern(self):
        """sub=3: positions 0,3,6 are beats; 1,2,4,5,7,8 are subs."""
        calls = _collect(9, beats=4, sub=3)
        for i, (_, _, is_sub) in enumerate(calls):
            assert is_sub == (i % 3 != 0), f"position {i}: is_sub={is_sub}"

    def test_sixteenth_note_pattern(self):
        """sub=4: positions 0,4,8 are beats; others are subs."""
        calls = _collect(12, beats=4, sub=4)
        for i, (_, _, is_sub) in enumerate(calls):
            assert is_sub == (i % 4 != 0), f"position {i}: is_sub={is_sub}"

    def test_beat_and_sub_flags_mutually_exclusive(self):
        """A callback cannot simultaneously be is_sub and is_accent."""
        calls = _collect(16, beats=4, sub=4)
        for _, is_accent, is_sub in calls:
            assert not (is_accent and is_sub)

    # ---- time-signature reset ----

    def test_time_sig_change_resets_to_beat_0(self):
        """
        After set_time_signature() while running, the very next beat must be
        beat_index=0 (is_accent=True), because _reset_pending clears sub_count.
        """
        phase = [1]  # 1=waiting for non-zero beat, 2=change sent, 3=done
        post_change: list[tuple] = []
        done = threading.Event()

        def cb(beat_index, is_accent, is_sub):
            if phase[0] == 1 and beat_index > 0:
                phase[0] = 2
                engine.set_time_signature(3, 4)
            elif phase[0] == 2:
                post_change.append((beat_index, is_accent))
                phase[0] = 3
                done.set()

        engine = MetronomeEngine(cb)
        engine.set_bpm(300)
        engine.start()
        assert done.wait(timeout=4.0), "reset not observed within timeout"
        engine.stop()

        assert post_change, "no beat received after time-sig change"
        beat_index, is_accent = post_change[0]
        assert beat_index == 0, f"expected beat 0 after reset, got {beat_index}"
        assert is_accent is True


# ---------------------------------------------------------------------------
# Callback robustness
# ---------------------------------------------------------------------------

class TestCallbackRobustness:
    def test_exception_in_callback_does_not_crash_engine(self):
        """Engine thread must survive a callback that always raises."""
        count = [0]
        done = threading.Event()

        def bad_cb(*_):
            count[0] += 1
            if count[0] >= 4:
                done.set()
            raise RuntimeError("boom")

        e = MetronomeEngine(bad_cb)
        e.set_bpm(300)
        e.start()
        assert done.wait(timeout=4.0), "engine stopped after callback exception"
        e.stop()
        assert count[0] >= 4


# ---------------------------------------------------------------------------
# Approximate timing accuracy
# ---------------------------------------------------------------------------

class TestTimingAccuracy:
    def test_ten_beats_arrive_within_expected_window(self):
        """At 300 BPM the first 10 beats span ≈ 1.8 s (9 × 0.2 s)."""
        times: list[float] = []
        done = threading.Event()

        def cb(*_):
            times.append(time.perf_counter())
            if len(times) >= 10:
                done.set()

        e = MetronomeEngine(cb)
        e.set_bpm(300)
        e.start()
        assert done.wait(timeout=6.0)
        e.stop()

        span = times[-1] - times[0]
        # 9 intervals × 0.2 s = 1.8 s; allow ±50 %
        assert 0.9 < span < 3.6, f"span={span:.3f}s unexpectedly out of range"

    def test_interval_variance_is_low(self):
        """Beat-to-beat jitter should be small relative to the interval."""
        times: list[float] = []
        done = threading.Event()

        def cb(*_):
            times.append(time.perf_counter())
            if len(times) >= 8:
                done.set()

        e = MetronomeEngine(cb)
        e.set_bpm(300)
        e.start()
        done.wait(timeout=5.0)
        e.stop()

        if len(times) < 4:
            pytest.skip("insufficient callbacks")

        intervals = [times[i] - times[i - 1] for i in range(1, len(times))]
        mean = sum(intervals) / len(intervals)
        std = (sum((x - mean) ** 2 for x in intervals) / len(intervals)) ** 0.5
        # std should be < 10 % of mean interval
        assert std < mean * 0.10, f"high jitter: mean={mean:.4f}, std={std:.4f}"
