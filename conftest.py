"""
Root conftest: mock hardware-dependent modules before any project code is
imported. Running first ensures test isolation regardless of collection order.
"""
import sys
from unittest.mock import MagicMock

# ---- sounddevice: prevent PortAudio / audio hardware access ----
_sd = MagicMock()
_sd.OutputStream = MagicMock  # class used with 'with' / constructor call
sys.modules.setdefault("sounddevice", _sd)

# ---- webview: prevent GUI window creation ----
_webview = MagicMock()
sys.modules.setdefault("webview", _webview)
