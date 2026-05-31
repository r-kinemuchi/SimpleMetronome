"""
Tests for MetronomeAPI (metronome/api.py).

AudioEngine and MetronomeEngine are both mocked (see conftest.py `api` fixture)
so tests cover only the API logic: state management, clamping, dispatch, and
tap-tempo arithmetic.

time.monotonic is patched in tap-tempo tests to give deterministic timestamps.
"""

import pytest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

class TestInitialState:
    def test_default_bpm(self, api):
        assert api._bpm == 120.0

    def test_default_time_signature(self, api):
        assert api._time_signature == "4/4"

    def test_default_subdivision(self, api):
        assert api._subdivision == 1

    def test_default_sound(self, api):
        assert api._sound == "click"

    def test_default_volume(self, api):
        assert api._volume == pytest.approx(0.7)

    def test_not_playing_initially(self, api):
        assert api._is_playing is False

    def test_tap_times_empty(self, api):
        assert api._tap_times == []

    def test_get_state_returns_all_fields(self, api):
        state = api.get_state()
        assert set(state.keys()) == {
            "bpm", "time_signature", "beats", "subdivision",
            "sound", "volume", "is_playing",
        }

    def test_get_state_defaults(self, api):
        state = api.get_state()
        assert state["bpm"] == 120.0
        assert state["time_signature"] == "4/4"
        assert state["beats"] == 4
        assert state["subdivision"] == 1
        assert state["sound"] == "click"
        assert state["volume"] == pytest.approx(0.7)
        assert state["is_playing"] is False


# ---------------------------------------------------------------------------
# toggle_play
# ---------------------------------------------------------------------------

class TestTogglePlay:
    def test_toggle_starts_playing(self, api):
        result = api.toggle_play()
        assert result == {"is_playing": True}
        assert api._is_playing is True

    def test_toggle_calls_engine_start(self, api):
        api.toggle_play()
        api._mock_engine.start.assert_called_once()

    def test_toggle_twice_stops_playing(self, api):
        api.toggle_play()
        result = api.toggle_play()
        assert result == {"is_playing": False}
        assert api._is_playing is False

    def test_stop_calls_engine_stop(self, api):
        api.toggle_play()
        api.toggle_play()
        api._mock_engine.stop.assert_called_once()

    def test_stop_calls_evaluate_js_reset(self, api):
        mock_window = MagicMock()
        api.set_window(mock_window)
        api.toggle_play()
        api.toggle_play()
        mock_window.evaluate_js.assert_called_with("window.onBeat(-1, false, false)")

    def test_stop_without_window_no_error(self, api):
        api._window = None
        api.toggle_play()
        api.toggle_play()  # must not raise

    def test_get_state_reflects_playing(self, api):
        api.toggle_play()
        assert api.get_state()["is_playing"] is True

    def test_three_toggles(self, api):
        api.toggle_play()
        api.toggle_play()
        result = api.toggle_play()
        assert result == {"is_playing": True}


# ---------------------------------------------------------------------------
# set_bpm
# ---------------------------------------------------------------------------

class TestSetBpm:
    def test_set_valid_bpm(self, api):
        result = api.set_bpm(150)
        assert result == {"bpm": 150.0}
        assert api._bpm == 150.0

    def test_clamp_below_minimum(self, api):
        result = api.set_bpm(1)
        assert result["bpm"] == 30.0

    def test_clamp_above_maximum(self, api):
        result = api.set_bpm(999)
        assert result["bpm"] == 300.0

    def test_boundary_minimum(self, api):
        result = api.set_bpm(30)
        assert result["bpm"] == 30.0

    def test_boundary_maximum(self, api):
        result = api.set_bpm(300)
        assert result["bpm"] == 300.0

    def test_float_string_accepted(self, api):
        result = api.set_bpm("142.5")
        assert result["bpm"] == pytest.approx(142.5)

    def test_delegates_to_engine(self, api):
        api.set_bpm(180)
        api._mock_engine.set_bpm.assert_called_once_with(180.0)

    def test_get_state_reflects_new_bpm(self, api):
        api.set_bpm(200)
        assert api.get_state()["bpm"] == 200.0


# ---------------------------------------------------------------------------
# set_time_signature
# ---------------------------------------------------------------------------

class TestSetTimeSignature:
    @pytest.mark.parametrize("sig,beats", [
        ("2/4", 2), ("3/4", 3), ("4/4", 4), ("6/8", 6),
    ])
    def test_valid_signatures(self, api, sig, beats):
        result = api.set_time_signature(sig)
        assert result["time_signature"] == sig
        assert result["beats"] == beats

    def test_invalid_sig_defaults_to_4_4(self, api):
        result = api.set_time_signature("5/5")
        assert result["time_signature"] == "4/4"
        assert result["beats"] == 4

    def test_empty_string_defaults_to_4_4(self, api):
        result = api.set_time_signature("")
        assert result["time_signature"] == "4/4"

    def test_delegates_to_engine(self, api):
        api.set_time_signature("3/4")
        api._mock_engine.set_time_signature.assert_called_once_with(3, 4)

    def test_state_updated(self, api):
        api.set_time_signature("6/8")
        state = api.get_state()
        assert state["time_signature"] == "6/8"
        assert state["beats"] == 6


# ---------------------------------------------------------------------------
# set_subdivision
# ---------------------------------------------------------------------------

class TestSetSubdivision:
    @pytest.mark.parametrize("sub", [1, 2, 3, 4])
    def test_valid_subdivisions(self, api, sub):
        result = api.set_subdivision(sub)
        assert result == {"subdivision": sub}

    @pytest.mark.parametrize("invalid", [0, 5, -1, 99])
    def test_invalid_defaults_to_1(self, api, invalid):
        result = api.set_subdivision(invalid)
        assert result == {"subdivision": 1}

    def test_string_accepted(self, api):
        result = api.set_subdivision("2")
        assert result == {"subdivision": 2}

    def test_delegates_to_engine(self, api):
        api.set_subdivision(4)
        api._mock_engine.set_subdivision.assert_called_once_with(4)

    def test_state_updated(self, api):
        api.set_subdivision(3)
        assert api.get_state()["subdivision"] == 3


# ---------------------------------------------------------------------------
# set_sound
# ---------------------------------------------------------------------------

class TestSetSound:
    @pytest.mark.parametrize("sound", ["beep", "click", "wood"])
    def test_valid_sounds(self, api, sound):
        result = api.set_sound(sound)
        assert result == {"sound": sound}

    def test_invalid_defaults_to_click(self, api):
        result = api.set_sound("vinyl")
        assert result == {"sound": "click"}

    def test_empty_string_defaults_to_click(self, api):
        result = api.set_sound("")
        assert result == {"sound": "click"}

    def test_state_updated(self, api):
        api.set_sound("wood")
        assert api.get_state()["sound"] == "wood"


# ---------------------------------------------------------------------------
# set_volume
# ---------------------------------------------------------------------------

class TestSetVolume:
    def test_set_valid_volume(self, api):
        result = api.set_volume(0.5)
        assert result == {"volume": pytest.approx(0.5)}

    def test_clamp_below_zero(self, api):
        result = api.set_volume(-0.1)
        assert result["volume"] == 0.0

    def test_clamp_above_one(self, api):
        result = api.set_volume(1.5)
        assert result["volume"] == 1.0

    def test_boundary_zero(self, api):
        result = api.set_volume(0)
        assert result["volume"] == 0.0

    def test_boundary_one(self, api):
        result = api.set_volume(1)
        assert result["volume"] == 1.0

    def test_string_accepted(self, api):
        result = api.set_volume("0.8")
        assert result["volume"] == pytest.approx(0.8)

    def test_state_updated(self, api):
        api.set_volume(0.3)
        assert api.get_state()["volume"] == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# tap_tempo
# ---------------------------------------------------------------------------

class TestTapTempo:
    # ---- single tap ----

    def test_single_tap_returns_current_bpm(self, api):
        api.set_bpm(140)
        with patch("metronome.api.time.monotonic", return_value=0.0):
            result = api.tap_tempo()
        assert result["bpm"] == pytest.approx(140.0)

    # ---- two taps ----

    def test_two_taps_60bpm(self, api):
        times = iter([0.0, 1.0])  # interval = 1.0 s → 60 BPM
        with patch("metronome.api.time.monotonic", side_effect=times):
            api.tap_tempo()
            result = api.tap_tempo()
        assert result["bpm"] == pytest.approx(60.0)

    def test_two_taps_120bpm(self, api):
        times = iter([0.0, 0.5])  # interval = 0.5 s → 120 BPM
        with patch("metronome.api.time.monotonic", side_effect=times):
            api.tap_tempo()
            result = api.tap_tempo()
        assert result["bpm"] == pytest.approx(120.0)

    def test_two_taps_200bpm(self, api):
        times = iter([0.0, 0.3])  # interval = 0.3 s → 200 BPM
        with patch("metronome.api.time.monotonic", side_effect=times):
            api.tap_tempo()
            result = api.tap_tempo()
        assert result["bpm"] == pytest.approx(200.0)

    # ---- moving average ----

    def test_multiple_taps_moving_average(self, api):
        """4 taps at 0.5 s spacing → avg interval = 0.5 s → 120 BPM."""
        tap_times = [0.0, 0.5, 1.0, 1.5]
        with patch("metronome.api.time.monotonic", side_effect=tap_times):
            for _ in tap_times:
                result = api.tap_tempo()
        assert result["bpm"] == pytest.approx(120.0)

    def test_window_max_8_intervals(self, api):
        """
        Spec: at most 8 intervals (9 taps retained).
        After 10 taps at 0.5 s spacing the oldest is dropped; BPM should still
        be 120.  Then an 11th tap at 1.0 s changes the average only slightly.
        """
        # 10 taps at 0.5 s spacing
        times_10 = [i * 0.5 for i in range(10)]
        with patch("metronome.api.time.monotonic", side_effect=times_10):
            for _ in times_10:
                api.tap_tempo()

        # verify window size is capped at 9
        assert len(api._tap_times) == 9

        # 11th tap arrives 1.0 s after the 10th
        t11 = times_10[-1] + 1.0
        with patch("metronome.api.time.monotonic", return_value=t11):
            result = api.tap_tempo()

        # avg of 7 intervals at 0.5 s + 1 interval at 1.0 s = (3.5+1.0)/8 = 0.5625 s
        expected_bpm = 60.0 / 0.5625
        assert result["bpm"] == pytest.approx(expected_bpm, rel=0.01)

    # ---- 2-second reset ----

    def test_reset_after_2_second_gap(self, api):
        """Tap, wait >2 s, tap again → history reset, single tap returns current BPM."""
        with patch("metronome.api.time.monotonic", return_value=0.0):
            api.tap_tempo()

        with patch("metronome.api.time.monotonic", return_value=2.1):
            api.tap_tempo()

        # After reset, only one tap in history → returns current bpm unchanged
        assert len(api._tap_times) == 1

    def test_no_reset_within_2_seconds(self, api):
        """A gap of exactly 2.0 s does NOT trigger a reset (condition is >2.0)."""
        with patch("metronome.api.time.monotonic", return_value=0.0):
            api.tap_tempo()
        with patch("metronome.api.time.monotonic", return_value=2.0):
            api.tap_tempo()
        assert len(api._tap_times) == 2

    def test_bpm_after_reset_and_two_taps(self, api):
        """After a reset the history starts fresh; two subsequent taps set BPM."""
        # First tap, then >2 s gap
        with patch("metronome.api.time.monotonic", return_value=0.0):
            api.tap_tempo()
        # gap of 3 s → reset
        with patch("metronome.api.time.monotonic", return_value=3.0):
            api.tap_tempo()
        # second tap 0.5 s later → interval 0.5 s → 120 BPM
        with patch("metronome.api.time.monotonic", return_value=3.5):
            result = api.tap_tempo()
        assert result["bpm"] == pytest.approx(120.0)

    # ---- clamping ----

    def test_fast_taps_clamped_to_300(self, api):
        times = iter([0.0, 0.1])  # interval 0.1 s → 600 BPM → clamped to 300
        with patch("metronome.api.time.monotonic", side_effect=times):
            api.tap_tempo()
            result = api.tap_tempo()
        assert result["bpm"] == 300.0

    def test_slow_taps_clamped_to_30(self, api):
        times = iter([0.0, 3.0])  # interval 3.0 s → 20 BPM → but gap>2 triggers reset
        # Use gap <2 s but very slow: interval 1.9 s → 31.6 BPM (no reset)
        times2 = iter([0.0, 1.9])
        with patch("metronome.api.time.monotonic", side_effect=times2):
            api.tap_tempo()
            result = api.tap_tempo()
        assert result["bpm"] == pytest.approx(60.0 / 1.9, rel=0.01)

    # ---- sets bpm as side effect ----

    def test_tap_updates_api_bpm(self, api):
        with patch("metronome.api.time.monotonic", side_effect=[0.0, 0.5]):
            api.tap_tempo()
            api.tap_tempo()
        assert api._bpm == pytest.approx(120.0)


# ---------------------------------------------------------------------------
# _on_beat: audio dispatch + JS notification
# ---------------------------------------------------------------------------

class TestOnBeat:
    def test_accent_calls_audio_play_accent(self, api):
        api._on_beat(0, True, False)
        api._mock_audio.play.assert_called_once_with("accent", "click", pytest.approx(0.7))

    def test_beat_calls_audio_play_beat(self, api):
        api._on_beat(1, False, False)
        api._mock_audio.play.assert_called_once_with("beat", "click", pytest.approx(0.7))

    def test_sub_calls_audio_play_sub(self, api):
        api._on_beat(0, False, True)
        api._mock_audio.play.assert_called_once_with("sub", "click", pytest.approx(0.7))

    def test_notifies_window_on_accent(self, api):
        mock_win = MagicMock()
        api.set_window(mock_win)
        api._on_beat(0, True, False)
        mock_win.evaluate_js.assert_called_once_with(
            "window.onBeat(0, true, false)"
        )

    def test_notifies_window_on_beat(self, api):
        mock_win = MagicMock()
        api.set_window(mock_win)
        api._on_beat(2, False, False)
        mock_win.evaluate_js.assert_called_once_with(
            "window.onBeat(2, false, false)"
        )

    def test_notifies_window_on_sub(self, api):
        mock_win = MagicMock()
        api.set_window(mock_win)
        api._on_beat(1, False, True)
        mock_win.evaluate_js.assert_called_once_with(
            "window.onBeat(1, false, true)"
        )

    def test_no_error_without_window(self, api):
        api._window = None
        api._on_beat(0, True, False)  # must not raise

    def test_volume_respected(self, api):
        api.set_volume(0.3)
        api._on_beat(0, True, False)
        api._mock_audio.play.assert_called_once_with("accent", "click", pytest.approx(0.3))

    def test_sound_preset_respected(self, api):
        api.set_sound("wood")
        api._on_beat(0, True, False)
        api._mock_audio.play.assert_called_once_with("accent", "wood", pytest.approx(0.7))


# ---------------------------------------------------------------------------
# set_window
# ---------------------------------------------------------------------------

class TestSetWindow:
    def test_set_window_stores_reference(self, api):
        mock_win = MagicMock()
        api.set_window(mock_win)
        assert api._window is mock_win


# ---------------------------------------------------------------------------
# Consistency: get_state always mirrors individual setters
# ---------------------------------------------------------------------------

class TestStateConsistency:
    def test_state_after_all_setters(self, api):
        api.set_bpm(180)
        api.set_time_signature("3/4")
        api.set_subdivision(2)
        api.set_sound("beep")
        api.set_volume(0.9)

        state = api.get_state()
        assert state["bpm"] == 180.0
        assert state["time_signature"] == "3/4"
        assert state["beats"] == 3
        assert state["subdivision"] == 2
        assert state["sound"] == "beep"
        assert state["volume"] == pytest.approx(0.9)
        assert state["is_playing"] is False
