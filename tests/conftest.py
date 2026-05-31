"""Shared fixtures for the test suite."""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def api():
    """MetronomeAPI with engine and audio mocked out (no threads, no hardware)."""
    with patch("metronome.api.AudioEngine") as mock_audio_cls, \
         patch("metronome.api.MetronomeEngine") as mock_engine_cls:
        from metronome.api import MetronomeAPI

        inst = MetronomeAPI()
        # expose mocked instances for assertions
        inst._mock_audio = mock_audio_cls.return_value
        inst._mock_engine = mock_engine_cls.return_value
        yield inst
