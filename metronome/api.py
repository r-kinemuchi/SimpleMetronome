import threading
import time
from typing import Any

import webview

from .audio import AudioEngine
from .engine import MetronomeEngine

_TIME_SIGS = {
    '2/4': (2, 4),
    '3/4': (3, 4),
    '4/4': (4, 4),
    '6/8': (6, 8),
}


class MetronomeAPI:
    def __init__(self):
        self._audio = AudioEngine()
        self._audio.preload()

        self._window: webview.Window | None = None
        self._lock = threading.Lock()

        self._bpm: float = 120.0
        self._time_signature: str = '4/4'
        self._subdivision: int = 1
        self._sound: str = 'click'
        self._volume: float = 0.7
        self._is_playing: bool = False

        self._tap_times: list[float] = []
        self._tap_lock = threading.Lock()

        self._engine = MetronomeEngine(beat_callback=self._on_beat)

    def set_window(self, window: webview.Window) -> None:
        self._window = window

    # ---- JS-callable public methods ----

    def get_state(self) -> dict:
        with self._lock:
            return {
                'bpm': self._bpm,
                'time_signature': self._time_signature,
                'beats': _TIME_SIGS[self._time_signature][0],
                'subdivision': self._subdivision,
                'sound': self._sound,
                'volume': self._volume,
                'is_playing': self._is_playing,
            }

    def toggle_play(self) -> dict:
        with self._lock:
            playing = not self._is_playing
            self._is_playing = playing

        if playing:
            self._engine.start()
        else:
            self._engine.stop()
            if self._window:
                self._window.evaluate_js('window.onBeat(-1, false, false)')

        return {'is_playing': playing}

    def set_bpm(self, bpm: Any) -> dict:
        bpm = max(30.0, min(300.0, float(bpm)))
        with self._lock:
            self._bpm = bpm
        self._engine.set_bpm(bpm)
        return {'bpm': bpm}

    def set_time_signature(self, sig: str) -> dict:
        if sig not in _TIME_SIGS:
            sig = '4/4'
        num, den = _TIME_SIGS[sig]
        with self._lock:
            self._time_signature = sig
        self._engine.set_time_signature(num, den)
        return {'time_signature': sig, 'beats': num}

    def set_subdivision(self, subdivision: Any) -> dict:
        sub = int(subdivision)
        if sub not in (1, 2, 3, 4):
            sub = 1
        with self._lock:
            self._subdivision = sub
        self._engine.set_subdivision(sub)
        return {'subdivision': sub}

    def set_sound(self, sound: str) -> dict:
        if sound not in ('beep', 'click', 'wood'):
            sound = 'click'
        with self._lock:
            self._sound = sound
        return {'sound': sound}

    def set_volume(self, volume: Any) -> dict:
        vol = max(0.0, min(1.0, float(volume)))
        with self._lock:
            self._volume = vol
        return {'volume': vol}

    def tap_tempo(self) -> dict:
        now = time.monotonic()
        with self._tap_lock:
            if self._tap_times and (now - self._tap_times[-1]) > 2.0:
                self._tap_times.clear()
            self._tap_times.append(now)
            if len(self._tap_times) > 9:
                self._tap_times = self._tap_times[-9:]
            if len(self._tap_times) < 2:
                with self._lock:
                    return {'bpm': self._bpm}
            intervals = [self._tap_times[i] - self._tap_times[i - 1]
                         for i in range(1, len(self._tap_times))]
            avg = sum(intervals) / len(intervals)
            bpm = max(30.0, min(300.0, 60.0 / avg))

        result = self.set_bpm(bpm)
        return result

    # ---- Private ----

    def _on_beat(self, beat_index: int, is_accent: bool, is_sub: bool) -> None:
        with self._lock:
            sound = self._sound
            volume = self._volume

        beat_type = 'accent' if is_accent else ('sub' if is_sub else 'beat')
        self._audio.play(beat_type, sound, volume)

        if self._window:
            self._window.evaluate_js(
                f'window.onBeat({beat_index}, {str(is_accent).lower()}, {str(is_sub).lower()})'
            )
