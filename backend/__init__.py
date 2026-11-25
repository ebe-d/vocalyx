import os, sys, types

# Restrict package search path to this local directory so /kaggle/input is never probed
__path__ = [os.path.dirname(os.path.abspath(__file__))]

# Directly load and bind tts_engine submodule once so any 'from backend import tts_engine'
# and sys.modules["backend.tts_engine"] always reference the exact same singleton module instance.
def _bind_tts_engine():
    existing = sys.modules.get("backend.tts_engine") or sys.modules.get("tts_engine")
    if existing is not None and hasattr(existing, "synthesize"):
        existing.__package__ = "backend"
        sys.modules["backend.tts_engine"] = existing
        sys.modules["tts_engine"] = existing
        return existing

    tts_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_engine.py")
    if not os.path.exists(tts_file):
        tts_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tts_engine.py")
    if not os.path.exists(tts_file):
        return None

    with open(tts_file, "r") as _f:
        _code = _f.read()
    _mod = types.ModuleType("backend.tts_engine")
    _mod.__file__ = tts_file
    _mod.__package__ = "backend"
    exec(_code, _mod.__dict__)
    sys.modules["backend.tts_engine"] = _mod
    sys.modules["tts_engine"] = _mod
    return _mod


try:
    _bound_tts = _bind_tts_engine()
    if _bound_tts is not None:
        tts_engine = _bound_tts
except Exception as _e:
    print(f"[backend/__init__.py Warning] Failed to bind tts_engine: {_e}")
