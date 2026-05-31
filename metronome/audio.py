import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 44100
BLOCK_SIZE = 256  # ~5.8ms per block


class AudioEngine:
    def __init__(self):
        self._buffers: dict[str, dict[str, np.ndarray]] = {}
        self._active: list[list] = []  # [[buf, pos], ...]
        self._lock = threading.Lock()
        self._stream: sd.OutputStream | None = None

    def preload(self) -> None:
        presets = {
            'beep': {
                'accent': self._sine(880, 0.05),
                'beat':   self._sine(660, 0.035),
                'sub':    self._sine(440, 0.025, amplitude=0.5),
            },
            'click': {
                'accent': self._click(1200, 0.05),
                'beat':   self._click(900,  0.035),
                'sub':    self._click(600,  0.025, amplitude=0.45),
            },
            'wood': {
                'accent': self._wood(500, 0.05),
                'beat':   self._wood(350, 0.035),
                'sub':    self._wood(250, 0.025, amplitude=0.45),
            },
        }
        self._buffers = presets
        self._start_stream()

    def _start_stream(self) -> None:
        self._stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='float32',
            blocksize=BLOCK_SIZE,
            callback=self._audio_callback,
        )
        self._stream.start()

    def _audio_callback(self, outdata: np.ndarray, frames: int, time_info, status) -> None:
        mixed = np.zeros(frames, dtype=np.float32)
        with self._lock:
            finished = []
            for i, item in enumerate(self._active):
                buf, pos = item
                n = min(frames, len(buf) - pos)
                if n <= 0:
                    finished.append(i)
                    continue
                mixed[:n] += buf[pos:pos + n]
                item[1] = pos + n
                if item[1] >= len(buf):
                    finished.append(i)
            for i in reversed(finished):
                self._active.pop(i)
        np.clip(mixed, -1.0, 1.0, out=mixed)
        outdata[:, 0] = mixed

    def play(self, beat_type: str, preset: str, volume: float) -> None:
        click = self._buffers.get('click', {})
        preset_bufs = self._buffers.get(preset, click)
        buf = preset_bufs.get(beat_type, click.get('beat'))
        if buf is None:
            return
        with self._lock:
            self._active.append([(buf * volume).astype(np.float32), 0])

    def close(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _window(self, buf: np.ndarray) -> np.ndarray:
        fade = min(64, len(buf) // 4)  # 64 samples ≈ 1.5ms
        if fade == 0:
            return buf
        buf[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
        buf[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
        return buf

    def _sine(self, freq: float, duration: float, amplitude: float = 1.0) -> np.ndarray:
        n = int(SAMPLE_RATE * duration)
        t = np.linspace(0, duration, n, endpoint=False)
        wave = np.sin(2 * np.pi * freq * t)
        env = np.exp(-t * 40)
        return self._window((wave * env * amplitude).astype(np.float32))

    def _click(self, freq: float, duration: float, amplitude: float = 1.0) -> np.ndarray:
        n = int(SAMPLE_RATE * duration)
        t = np.linspace(0, duration, n, endpoint=False)
        tone = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2 * t)
        click_noise = np.random.randn(n) * 0.06
        noise_env = np.exp(-t * 500)
        wave = tone + click_noise * noise_env
        env = np.exp(-t * 80)
        return self._window((wave * env * amplitude).astype(np.float32))

    def _wood(self, freq: float, duration: float, amplitude: float = 1.0) -> np.ndarray:
        n = int(SAMPLE_RATE * duration)
        t = np.linspace(0, duration, n, endpoint=False)
        wave = np.sin(2 * np.pi * freq * t) + 0.5 * np.sin(2 * np.pi * freq * 2 * t)
        env = np.exp(-t * 80)
        return self._window((wave * env * amplitude).astype(np.float32))
