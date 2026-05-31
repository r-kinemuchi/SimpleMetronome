"""
Tests for AudioEngine (metronome/audio.py).

sounddevice is mocked in root conftest.py so no audio hardware is needed.
AudioEngine._start_stream() is additionally patched where tests care only
about buffer generation, not stream lifecycle.
"""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from metronome.audio import AudioEngine, SAMPLE_RATE, BLOCK_SIZE


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_engine_no_stream() -> AudioEngine:
    """Return an AudioEngine whose _start_stream is a no-op."""
    e = AudioEngine()
    e._stream = MagicMock()  # pretend stream already exists
    return e


def _preloaded_engine() -> AudioEngine:
    with patch.object(AudioEngine, "_start_stream"):
        e = AudioEngine()
        e.preload()
    return e


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_sample_rate(self):
        assert SAMPLE_RATE == 44100

    def test_block_size(self):
        assert BLOCK_SIZE == 256


# ---------------------------------------------------------------------------
# Waveform generators — pure numpy math, no hardware
# ---------------------------------------------------------------------------

class TestSine:
    def test_returns_float32(self):
        e = _make_engine_no_stream()
        buf = e._sine(440, 0.05)
        assert buf.dtype == np.float32

    def test_correct_length(self):
        e = _make_engine_no_stream()
        buf = e._sine(440, 0.05)
        assert len(buf) == int(SAMPLE_RATE * 0.05)

    def test_amplitude_within_range(self):
        e = _make_engine_no_stream()
        buf = e._sine(440, 0.05)
        assert buf.max() <= 1.0
        assert buf.min() >= -1.0

    def test_amplitude_scale(self):
        e = _make_engine_no_stream()
        loud = e._sine(440, 0.05, amplitude=1.0)
        quiet = e._sine(440, 0.05, amplitude=0.5)
        # quiet peak should be ≈ half of loud peak
        assert quiet.max() < loud.max() * 0.9

    def test_different_frequencies_differ(self):
        e = _make_engine_no_stream()
        b440 = e._sine(440, 0.1)
        b880 = e._sine(880, 0.1)
        assert not np.allclose(b440, b880)

    def test_envelope_decays(self):
        """Due to exp(-t*40) envelope, end should be quieter than start."""
        e = _make_engine_no_stream()
        buf = e._sine(440, 0.1)
        # compare RMS of first 10% vs last 10%
        n = len(buf)
        start_rms = float(np.sqrt(np.mean(buf[:n // 10] ** 2)))
        end_rms = float(np.sqrt(np.mean(buf[-n // 10:] ** 2)))
        assert end_rms < start_rms


class TestClick:
    def test_returns_float32(self):
        e = _make_engine_no_stream()
        buf = e._click(900, 0.035)
        assert buf.dtype == np.float32

    def test_correct_length(self):
        e = _make_engine_no_stream()
        buf = e._click(900, 0.035)
        assert len(buf) == int(SAMPLE_RATE * 0.035)

    def test_amplitude_within_range(self):
        e = _make_engine_no_stream()
        buf = e._click(900, 0.035)
        assert buf.max() <= 1.05  # brief transients may exceed 1 before _window clips
        assert buf.min() >= -1.05

    def test_amplitude_scale(self):
        e = _make_engine_no_stream()
        loud = e._click(900, 0.035, amplitude=1.0)
        quiet = e._click(900, 0.035, amplitude=0.45)
        assert quiet.max() < loud.max()


class TestWood:
    def test_returns_float32(self):
        e = _make_engine_no_stream()
        buf = e._wood(350, 0.035)
        assert buf.dtype == np.float32

    def test_correct_length(self):
        e = _make_engine_no_stream()
        buf = e._wood(350, 0.035)
        assert len(buf) == int(SAMPLE_RATE * 0.035)

    def test_amplitude_within_range(self):
        # wave = sin(f) + 0.5*sin(2f) so theoretical peak is 1.5; before
        # _window the extremes can reach ±1.5 briefly.
        e = _make_engine_no_stream()
        buf = e._wood(350, 0.035)
        assert buf.max() <= 1.6
        assert buf.min() >= -1.6

    def test_different_from_sine(self):
        """Wood adds a 2nd harmonic so its spectrum differs from pure sine."""
        e = _make_engine_no_stream()
        n = int(SAMPLE_RATE * 0.05)
        sine = e._sine(350, 0.05)
        wood = e._wood(350, 0.05)
        assert not np.allclose(sine, wood, atol=0.05)


# ---------------------------------------------------------------------------
# Window (fade in / fade out)
# ---------------------------------------------------------------------------

class TestWindow:
    def test_first_sample_near_zero(self):
        e = _make_engine_no_stream()
        buf = np.ones(200, dtype=np.float32)
        result = e._window(buf.copy())
        assert result[0] < 0.05

    def test_last_sample_near_zero(self):
        e = _make_engine_no_stream()
        buf = np.ones(200, dtype=np.float32)
        result = e._window(buf.copy())
        assert result[-1] < 0.05

    def test_middle_sample_near_one(self):
        e = _make_engine_no_stream()
        buf = np.ones(400, dtype=np.float32)
        result = e._window(buf.copy())
        assert result[200] > 0.95

    def test_modifies_buffer_in_place(self):
        e = _make_engine_no_stream()
        buf = np.ones(200, dtype=np.float32)
        result = e._window(buf)
        assert result is buf

    def test_short_buffer_uses_smaller_fade(self):
        """For very short buffers, fade = len(buf)//4, not 64."""
        e = _make_engine_no_stream()
        buf = np.ones(40, dtype=np.float32)
        result = e._window(buf.copy())
        assert result[0] < 0.1
        assert result[-1] < 0.1


# ---------------------------------------------------------------------------
# preload: buffer structure
# ---------------------------------------------------------------------------

class TestPreload:
    def test_all_presets_created(self):
        e = _preloaded_engine()
        assert set(e._buffers.keys()) == {"beep", "click", "wood"}

    def test_all_beat_types_per_preset(self):
        e = _preloaded_engine()
        for preset in ("beep", "click", "wood"):
            assert set(e._buffers[preset].keys()) == {"accent", "beat", "sub"}

    def test_buffers_are_float32(self):
        e = _preloaded_engine()
        for preset in e._buffers.values():
            for buf in preset.values():
                assert buf.dtype == np.float32

    def test_accent_longer_than_sub(self):
        """Accent duration > sub duration per spec."""
        e = _preloaded_engine()
        for preset_name, preset in e._buffers.items():
            assert len(preset["accent"]) > len(preset["sub"]), preset_name

    def test_accent_louder_than_sub(self):
        """Accent amplitude > sub amplitude (by peak or RMS)."""
        e = _preloaded_engine()
        for preset_name, preset in e._buffers.items():
            assert preset["accent"].max() > preset["sub"].max(), preset_name


# ---------------------------------------------------------------------------
# play(): queue management
# ---------------------------------------------------------------------------

class TestPlay:
    def test_play_adds_to_active(self):
        e = _preloaded_engine()
        assert len(e._active) == 0
        e.play("beat", "click", 1.0)
        assert len(e._active) == 1

    def test_play_stores_position_zero(self):
        e = _preloaded_engine()
        e.play("beat", "click", 1.0)
        _, pos = e._active[0]
        assert pos == 0

    def test_play_volume_scales_buffer(self):
        e = _preloaded_engine()
        e.play("beat", "click", 0.5)
        buf, _ = e._active[0]
        # original buffer peak is at most 1.0; scaled peak ≤ 0.5
        assert buf.max() <= 0.5 + 1e-6

    def test_play_unknown_preset_falls_back_to_click(self):
        e = _preloaded_engine()
        e.play("beat", "nonexistent", 1.0)
        assert len(e._active) == 1  # did not raise

    def test_play_multiple_buffers_accumulate(self):
        e = _preloaded_engine()
        e.play("accent", "click", 1.0)
        e.play("beat", "click", 1.0)
        assert len(e._active) == 2

    def test_play_is_thread_safe(self):
        """Concurrent play() calls must not corrupt the active list."""
        import threading
        e = _preloaded_engine()
        errors: list[Exception] = []

        def worker():
            try:
                for _ in range(20):
                    e.play("beat", "click", 0.5)
            except Exception as ex:
                errors.append(ex)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(e._active) == 80


# ---------------------------------------------------------------------------
# _audio_callback: mixing and buffer management
# ---------------------------------------------------------------------------

def _run_callback(engine: AudioEngine, frames: int) -> np.ndarray:
    """Run one audio callback iteration; return the outdata array."""
    outdata = np.zeros((frames, 1), dtype=np.float32)
    engine._audio_callback(outdata, frames, None, None)
    return outdata


class TestAudioCallback:
    def test_silence_when_nothing_active(self):
        e = _make_engine_no_stream()
        out = _run_callback(e, 256)
        np.testing.assert_array_equal(out, 0.0)

    def test_single_buffer_copied_to_output(self):
        e = _make_engine_no_stream()
        n = 100
        buf = np.full(n, 0.3, dtype=np.float32)
        e._active = [[buf.copy(), 0]]
        out = _run_callback(e, n)
        np.testing.assert_allclose(out[:, 0], 0.3, atol=1e-6)

    def test_two_buffers_mixed(self):
        e = _make_engine_no_stream()
        n = 100
        e._active = [
            [np.full(n, 0.3, dtype=np.float32), 0],
            [np.full(n, 0.4, dtype=np.float32), 0],
        ]
        out = _run_callback(e, n)
        np.testing.assert_allclose(out[:, 0], 0.7, atol=1e-6)

    def test_output_clipped_to_plus_one(self):
        e = _make_engine_no_stream()
        n = 100
        e._active = [
            [np.full(n, 0.8, dtype=np.float32), 0],
            [np.full(n, 0.8, dtype=np.float32), 0],
        ]
        out = _run_callback(e, n)
        assert out.max() <= 1.0

    def test_output_clipped_to_minus_one(self):
        e = _make_engine_no_stream()
        n = 100
        e._active = [
            [np.full(n, -0.8, dtype=np.float32), 0],
            [np.full(n, -0.8, dtype=np.float32), 0],
        ]
        out = _run_callback(e, n)
        assert out.min() >= -1.0

    def test_finished_buffer_removed(self):
        e = _make_engine_no_stream()
        n = 50
        buf = np.ones(n, dtype=np.float32)
        e._active = [[buf, 0]]
        _run_callback(e, n)
        assert len(e._active) == 0

    def test_partial_buffer_advances_position(self):
        """frames=50, buffer length=100 → position becomes 50, buffer stays."""
        e = _make_engine_no_stream()
        buf = np.ones(100, dtype=np.float32) * 0.5
        e._active = [[buf, 0]]
        _run_callback(e, 50)
        assert len(e._active) == 1
        _, pos = e._active[0]
        assert pos == 50

    def test_resume_from_mid_buffer(self):
        """Buffer already at position 50; frames=50 should exhaust it."""
        e = _make_engine_no_stream()
        buf = np.ones(100, dtype=np.float32) * 0.5
        e._active = [[buf, 50]]
        out = _run_callback(e, 50)
        assert len(e._active) == 0
        np.testing.assert_allclose(out[:50, 0], 0.5, atol=1e-6)

    def test_short_buffer_within_larger_frame(self):
        """Buffer length=30, frames=100 → first 30 samples filled, rest 0."""
        e = _make_engine_no_stream()
        buf = np.ones(30, dtype=np.float32) * 0.6
        e._active = [[buf, 0]]
        out = _run_callback(e, 100)
        np.testing.assert_allclose(out[:30, 0], 0.6, atol=1e-6)
        np.testing.assert_array_equal(out[30:, 0], 0.0)
        assert len(e._active) == 0

    def test_multiple_buffers_finish_at_different_times(self):
        """Two buffers of different lengths; both should be removed eventually."""
        e = _make_engine_no_stream()
        e._active = [
            [np.ones(80, dtype=np.float32), 0],
            [np.ones(200, dtype=np.float32), 0],
        ]
        _run_callback(e, 100)  # 80-sample buf exhausted; 200-sample has 100 left
        assert len(e._active) == 1
        _, pos = e._active[0]
        assert pos == 100

    def test_output_shape_preserved(self):
        e = _make_engine_no_stream()
        out = _run_callback(e, 256)
        assert out.shape == (256, 1)


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------

class TestClose:
    def test_close_calls_stream_stop_and_close(self):
        e = _make_engine_no_stream()
        mock_stream = e._stream
        e.close()
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()

    def test_close_sets_stream_to_none(self):
        e = _make_engine_no_stream()
        e.close()
        assert e._stream is None

    def test_close_when_no_stream_is_safe(self):
        e = AudioEngine()
        e._stream = None
        e.close()  # must not raise
