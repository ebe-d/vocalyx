import os, sys, types

# Restrict package search path to this local directory so /kaggle/input is never probed
__path__ = [os.path.dirname(os.path.abspath(__file__))]

# Directly load and bind tts_engine submodule so any 'from backend import tts_engine' is guaranteed to have synthesize and prewarm_engine
_tts_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_engine.py")
if not os.path.exists(_tts_file):
    _tts_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tts_engine.py")

if os.path.exists(_tts_file):
    try:
        with open(_tts_file, "r") as _f:
            _code = _f.read()
        _mod = types.ModuleType("backend.tts_engine")
        _mod.__file__ = _tts_file
        exec(_code, _mod.__dict__)
        sys.modules["backend.tts_engine"] = _mod
        sys.modules["tts_engine"] = _mod
        tts_engine = _mod
    except Exception as _e:
        print(f"[backend/__init__.py Warning] Failed to bind tts_engine: {_e}")
