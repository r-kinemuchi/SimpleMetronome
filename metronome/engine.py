import threading
import time
from typing import Callable


class MetronomeEngine:
    def __init__(self, beat_callback: Callable[[int, bool, bool], None]):
        self._callback = beat_callback
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self._bpm: float = 120.0
        self._beats_per_measure: int = 4
        self._subdivision: int = 1   # 1=quarter, 2=eighth, 3=triplet, 4=sixteenth
        self._reset_pending: bool = False

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            # If the thread is somehow still alive after the timeout, clear the
            # reference anyway so start() can spawn a fresh thread.  The zombie
            # thread will exit on its own once it next checks _stop_event.
            if self._thread.is_alive():
                import logging
                logging.warning("MetronomeEngine: thread did not stop within 2 s")
            self._thread = None

    def set_bpm(self, bpm: float) -> None:
        with self._lock:
            self._bpm = max(30.0, min(300.0, bpm))

    def set_time_signature(self, numerator: int, denominator: int) -> None:
        with self._lock:
            self._beats_per_measure = numerator
            self._reset_pending = True

    def set_subdivision(self, subdivision: int) -> None:
        with self._lock:
            self._subdivision = max(1, int(subdivision))
            self._reset_pending = True

    def _run(self) -> None:
        sub_count = 0
        next_time = time.perf_counter()

        while not self._stop_event.is_set():
            with self._lock:
                bpm = self._bpm
                beats = self._beats_per_measure
                sub = self._subdivision
                if self._reset_pending:
                    sub_count = 0
                    self._reset_pending = False
                    next_time = time.perf_counter()

            sub_interval = 60.0 / bpm / sub

            sleep_dur = next_time - time.perf_counter() - 0.001
            if sleep_dur > 0:
                self._stop_event.wait(sleep_dur)
            while time.perf_counter() < next_time:
                pass

            beat_index = (sub_count // sub) % beats
            is_accent = (beat_index == 0 and sub_count % sub == 0)
            is_sub = (sub_count % sub != 0)

            try:
                self._callback(beat_index, is_accent, is_sub)
            except Exception:
                pass

            sub_count += 1
            next_time += sub_interval
            # Prevent timing debt from accumulating; skip ahead if we've
            # fallen behind by more than one interval (e.g. after system load).
            if next_time < time.perf_counter():
                next_time = time.perf_counter()
