"""
Text-to-Speech engine supporting LuxTTS (ultra-fast 4-step diffusion, ~150x real-time)
and Chatterbox Turbo TTS with voice cloning support.
The model is loaded once at module import or first request (singleton pattern).
"""
import os
import sys
import time
import re
import torch
import torchaudio

# Base directory safe for both script imports and Jupyter notebook executions
_BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()

# Add potential LuxTTS repository directories to sys.path
for p in [
    "/kaggle/working/LuxTTS",
    "LuxTTS",
    os.path.join(_BASE_DIR, "..", "LuxTTS"),
    os.path.join(_BASE_DIR, "LuxTTS"),
]:
    if os.path.exists(p) and os.path.abspath(p) not in sys.path:
        sys.path.insert(0, os.path.abspath(p))

try:
    from backend import config
    from backend.config import CUDA_DEVICE, REFERENCE_AUDIO_PATH, TTS_OUTPUT_DIR, TTS_ENGINE
except ImportError:
    try:
        import config
        from config import CUDA_DEVICE, REFERENCE_AUDIO_PATH, TTS_OUTPUT_DIR, TTS_ENGINE
    except ImportError:
        config = None
        CUDA_DEVICE = "cuda"
        REFERENCE_AUDIO_PATH = "voice_clone.mp3"
        TTS_OUTPUT_DIR = "tts_output"
        TTS_ENGINE = "f5tts"

# ---------------------------------------------------------------------------
# Singleton instances & cache
# ---------------------------------------------------------------------------
lux_model = None
_cached_lux_prompt = None
chatterbox_model = None
_cached_chatterbox_ref = None
_device = None

if torch.cuda.is_available():
    torch.backends.cudnn.benchmark = True
    try:
        torch.set_float32_matmul_precision("high")
    except Exception:
        pass


def _resolve_reference_audio(reference_audio: str = None) -> str:
    """Finds the absolute path to the reference audio file."""
    import glob as _glob
    if reference_audio is None:
        reference_audio = getattr(config, "REFERENCE_AUDIO_PATH", None) if config else None
        if not reference_audio:
            reference_audio = REFERENCE_AUDIO_PATH

    candidates = [
        reference_audio,
        "voice_clone.mp3",
        os.path.join(_BASE_DIR, reference_audio),
        os.path.join(_BASE_DIR, "..", reference_audio),
        os.path.join(_BASE_DIR, "voice_clone.mp3"),
        os.path.join(_BASE_DIR, "..", "voice_clone.mp3"),
        "/kaggle/working/vocaly/voice_clone.mp3",
        "/kaggle/working/vocaly/backend/voice_clone.mp3",
        "/kaggle/working/vocalyx/voice_clone.mp3",
        "/kaggle/working/voice_clone.mp3",
    ]
    for c in candidates:
        if c and os.path.exists(c) and os.path.getsize(c) > 0:
            return os.path.abspath(c)

    # Search Kaggle input/working directories dynamically if default not at standard path
    if reference_audio == REFERENCE_AUDIO_PATH or os.path.basename(reference_audio) == "voice_clone.mp3":
        for found in _glob.glob("/kaggle/**/voice_clone.mp3", recursive=True):
            if os.path.getsize(found) > 0:
                return os.path.abspath(found)

    # Last-resort fallback to studio female reference if custom voice_clone.mp3 is absent
    for ref_fb in [
        os.path.join(_BASE_DIR, "default_voices", "female_reference.wav"),
        os.path.join(_BASE_DIR, "..", "default_voices", "female_reference.wav"),
        "/kaggle/working/vocaly/default_voices/female_reference.wav",
        "/kaggle/working/vocaly/backend/default_voices/female_reference.wav",
    ]:
        if os.path.exists(ref_fb) and os.path.getsize(ref_fb) > 0:
            print(f"[TTS WARNING] Reference audio '{reference_audio}' not found; using fallback '{ref_fb}'.")
            return os.path.abspath(ref_fb)

    return os.path.abspath(reference_audio) if reference_audio else "voice_clone.mp3"


# ---------------------------------------------------------------------------
# LuxTTS Engine (~150x real-time, ~0.15s - 0.25s latency)
# ---------------------------------------------------------------------------
def get_luxtts_model():
    """Lazily load LuxTTS model and pre-encode reference voice."""
    global lux_model, _cached_lux_prompt, _device
    if lux_model is not None:
        return lux_model

    for p in ["/kaggle/working/LuxTTS", "LuxTTS", os.path.join(_BASE_DIR, "..", "LuxTTS")]:
        if os.path.exists(p) and os.path.abspath(p) not in sys.path:
            sys.path.insert(0, os.path.abspath(p))

    from zipvoice.luxvoice import LuxTTS

    device_to_use = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[TTS] Initializing LuxTTS on {device_to_use}...")
    t0 = time.time()
    lux_model = LuxTTS(device=device_to_use)
    _device = device_to_use
    print(f"[TTS] ✓ LuxTTS model loaded into {device_to_use} in {time.time() - t0:.2f}s")

    # Locate reference voice audio
    ref_audio = _resolve_reference_audio()
    cached_prompt_file = os.path.join(TTS_OUTPUT_DIR, "voice_clone_lux_conds.pt")

    # Try loading cached prompt from disk (instant 0.01s)
    if os.path.exists(cached_prompt_file) and os.path.getsize(cached_prompt_file) > 1000:
        try:
            try:
                _cached_lux_prompt = torch.load(cached_prompt_file, map_location=device_to_use, weights_only=False)
            except TypeError:
                _cached_lux_prompt = torch.load(cached_prompt_file, map_location=device_to_use)
            if isinstance(_cached_lux_prompt, dict):
                for k, v in _cached_lux_prompt.items():
                    if isinstance(v, torch.Tensor):
                        _cached_lux_prompt[k] = v.to(lux_model.device)
                print(f"[TTS] ✓ Loaded pre-computed LuxTTS voice prompt from {cached_prompt_file} in 0.01s!")
                return lux_model
        except Exception as _cpe:
            print(f"[TTS] Prompt cache load note: {_cpe}")

    if ref_audio and os.path.exists(ref_audio):
        print(f"[TTS] Encoding reference voice '{ref_audio}' for LuxTTS...")
        t_enc = time.time()
        _cached_lux_prompt = lux_model.encode_prompt(ref_audio, duration=5, rms=0.01)
        print(f"[TTS] ✓ Reference voice prompt encoded in {time.time() - t_enc:.2f}s")
        try:
            os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)
            torch.save(_cached_lux_prompt, cached_prompt_file)
            print(f"[TTS] ✓ Cached LuxTTS voice prompt to {cached_prompt_file}")
        except Exception as _se:
            print(f"[TTS] Prompt cache save note: {_se}")

    return lux_model


def _standardize_and_save_audio(wav_raw, native_sr: int, output_path: str, target_sr: int = 48000) -> str:
    """
    Standardizes raw model output tensor/numpy array to 48,000 Hz 16-bit PCM WAV.
    Applies gentle peak normalization to 0.88 to avoid clipping and eliminate hiss amplification.
    Guarantees crisp, natural-pitch playback across Twilio telephony and browser.
    """
    import soundfile as sf
    import numpy as np

    if isinstance(wav_raw, torch.Tensor):
        wav_np = wav_raw.squeeze().detach().cpu().numpy()
    elif hasattr(wav_raw, "numpy"):
        wav_np = wav_raw.numpy().squeeze()
    else:
        wav_np = np.asarray(wav_raw).squeeze()

    if wav_np.ndim > 1:
        wav_np = wav_np.mean(axis=0)

    # Gentle peak normalization to 0.88 without amplifying quiet background hiss
    max_val = float(np.max(np.abs(wav_np)))
    if max_val > 0.005:
        wav_np = wav_np * (0.88 / max_val)

    # Standardize to 48000 Hz 16-bit PCM for universal telephony/browser playback
    native_sr = int(native_sr)
    if native_sr != target_sr:
        try:
            import torchaudio
            wav_t = torch.from_numpy(wav_np).unsqueeze(0)
            resampled_t = torchaudio.functional.resample(wav_t, orig_freq=native_sr, new_freq=target_sr)
            wav_np = resampled_t.squeeze(0).numpy()
            save_sr = target_sr
        except Exception as resample_err:
            print(f"[TTS Post-Process Warning] Resample {native_sr}->{target_sr} failed: {resample_err}")
            save_sr = native_sr
    else:
        save_sr = target_sr

    # Apply a subtle 8ms fade-in on leading edge, then prepend 450ms + append 200ms digital silence
    # so telephony <Play> jitter-buffer / browser audio wake-up never clips opening words on fast voices
    if wav_np.size > 0:
        ramp_len = min(wav_np.size, max(1, int(save_sr * 0.008)))
        wav_np = wav_np.copy()
        wav_np[:ramp_len] *= np.linspace(0.0, 1.0, ramp_len, dtype=wav_np.dtype)
    lead_silence = np.zeros(int(save_sr * 0.45), dtype=np.float32)
    tail_silence = np.zeros(int(save_sr * 0.20), dtype=np.float32)
    wav_padded = np.concatenate([lead_silence, wav_np.astype(np.float32), tail_silence])

    wav_int16 = (np.clip(wav_padded, -1.0, 1.0) * 32767.0).astype(np.int16)
    sf.write(output_path, wav_int16, save_sr, subtype='PCM_16')
    return output_path


def _synthesize_luxtts(text: str, reference_audio: str = None) -> str:
    """High-speed 6-step generation using LuxTTS (~150x real-time)."""
    global lux_model, _cached_lux_prompt

    model = get_luxtts_model()
    prompt_dict = _cached_lux_prompt

    if reference_audio:
        ref_path = _resolve_reference_audio(reference_audio)
        if prompt_dict is None or ref_path != _resolve_reference_audio():
            print(f"[TTS] Encoding custom reference audio '{ref_path}'...")
            prompt_dict = model.encode_prompt(ref_path, duration=5, rms=0.01)
    elif prompt_dict is None:
        ref_path = _resolve_reference_audio()
        if ref_path and os.path.exists(ref_path):
            print(f"[TTS] Encoding reference audio '{ref_path}' for LuxTTS...")
            prompt_dict = model.encode_prompt(ref_path, duration=5, rms=0.01)

    if prompt_dict is None:
        raise RuntimeError("No reference audio prompt available for LuxTTS voice cloning.")

    # Clone tensor dictionary to prevent prompt conditioning corruption across conversational turns
    prompt_to_pass = {}
    if isinstance(prompt_dict, dict):
        for k, v in prompt_dict.items():
            if isinstance(v, torch.Tensor):
                prompt_to_pass[k] = v.to(model.device).clone()
            else:
                prompt_to_pass[k] = v
    else:
        prompt_to_pass = prompt_dict

    # Clean text: preserve expressiveness (! and ?) while removing markdown/URLs
    clean_text = re.sub(r'[*_#`~\[\]()]', ' ', text)
    clean_text = re.sub(r'https?://\S+', '', clean_text)
    clean_text = re.sub(r'\.{2,}', '.', clean_text)
    clean_text = re.sub(r'!{2,}', '!', clean_text)
    clean_text = re.sub(r'\?{2,}', '?', clean_text)
    clean_text = re.sub(r'[—–]+', ', ', clean_text)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    if not clean_text:
        clean_text = text.strip() or "Hello!"

    t0 = time.time()
    final_wav = model.generate_speech(
        clean_text,
        prompt_to_pass,
        num_steps=6,
        t_shift=0.9,
        speed=1.0,
    )
    gen_duration = time.time() - t0
    print(f"[TTS LuxTTS] ⚡ Generated speech in {gen_duration:.3f}s for '{clean_text[:40]}...'")

    os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)
    timestamp = int(time.time() * 1000)
    output_path = os.path.join(TTS_OUTPUT_DIR, f"output_{timestamp}.wav")

    native_sr = int(getattr(model, "sample_rate", getattr(model, "sr", 48000)))
    return _standardize_and_save_audio(final_wav, native_sr=native_sr, output_path=output_path, target_sr=48000)


# ---------------------------------------------------------------------------
# Chatterbox Turbo Engine (Fallback)
# ---------------------------------------------------------------------------
# Patches for PyTorch / NumPy 2.x compatibility
try:
    import inspect
    import importlib
    import numpy as np

    try:
        import chatterbox.models.s3tokenizer.s3tokenizer as _s3_mod
        _s3_file = inspect.getfile(_s3_mod)
        if os.path.exists(_s3_file):
            with open(_s3_file, "r") as _f:
                _s3_code = _f.read()
            _s3_changed = False
            if "audio = audio.to(self.device)" in _s3_code:
                _s3_code = _s3_code.replace("audio = audio.to(self.device)", "audio = audio.float().to(self.device)")
                _s3_changed = True
            if "window=self.window.to(self.device)" in _s3_code:
                _s3_code = _s3_code.replace("window=self.window.to(self.device)", "window=self.window.float().to(self.device)")
                _s3_changed = True
            if "self._mel_filters.to(self.device) @ magnitudes" in _s3_code:
                _s3_code = _s3_code.replace("self._mel_filters.to(self.device) @ magnitudes", "torch.matmul(self._mel_filters.float().to(self.device), magnitudes.float())")
                _s3_changed = True
            if "self._mel_filters.float().to(self.device) @ magnitudes.float()" in _s3_code:
                _s3_code = _s3_code.replace("self._mel_filters.float().to(self.device) @ magnitudes.float()", "torch.matmul(self._mel_filters.float().to(self.device), magnitudes.float())")
                _s3_changed = True
            if _s3_changed:
                with open(_s3_file, "w") as _f:
                    _f.write(_s3_code)
                importlib.reload(_s3_mod)

        def _safe_log_mel(self, audio, padding: int = 0):
            if not torch.is_tensor(audio):
                audio = torch.from_numpy(np.asarray(audio, dtype=np.float32))
            audio = audio.to(device=self.device, dtype=torch.float32)
            if padding > 0:
                audio = torch.nn.functional.pad(audio, (0, padding))
            window = self.window.to(device=self.device, dtype=torch.float32)
            stft = torch.stft(audio, self.n_fft, 160, window=window, return_complex=True)
            magnitudes = stft[..., :-1].abs() ** 2
            magnitudes = magnitudes.to(device=self.device, dtype=torch.float32)
            filters = self._mel_filters.to(device=self.device, dtype=torch.float32)
            mel_spec = torch.matmul(filters, magnitudes)
            log_spec = torch.clamp(mel_spec, min=1e-10).log10()
            log_spec = torch.maximum(log_spec, log_spec.max() - 8.0)
            log_spec = (log_spec + 4.0) / 4.0
            return log_spec
        _s3_mod.S3Tokenizer.log_mel_spectrogram = _safe_log_mel
    except Exception:
        pass

    try:
        import chatterbox.models.voice_encoder.voice_encoder as _ve_mod
        _ve_file = inspect.getfile(_ve_mod)
        if os.path.exists(_ve_file):
            with open(_ve_file, "r") as _f:
                _ve_code = _f.read()
            _ve_changed = False
            if "self.lstm(mels)" in _ve_code:
                _ve_code = _ve_code.replace("self.lstm(mels)", "self.lstm(mels.float())")
                _ve_changed = True
            if "self.inference(mels.to(self.device)" in _ve_code:
                _ve_code = _ve_code.replace("self.inference(mels.to(self.device)", "self.inference(mels.float().to(self.device)")
                _ve_changed = True
            if _ve_changed:
                with open(_ve_file, "w") as _f:
                    _f.write(_ve_code)
                importlib.reload(_ve_mod)
    except Exception:
        pass

    try:
        import perth
        if getattr(perth, "PerthImplicitWatermarker", None) is None:
            perth.PerthImplicitWatermarker = perth.DummyWatermarker
    except Exception:
        pass

    try:
        import chatterbox.tts_turbo as _turbo_mod
        import torch.serialization
        if hasattr(torch.serialization, "add_safe_globals"):
            torch.serialization.add_safe_globals([_turbo_mod.Conditionals])

        _orig_turbo_prep = _turbo_mod.ChatterboxTurboTTS.prepare_conditionals
        def _safe_turbo_prep(self, wav_fpath, exaggeration=0.5, norm_loudness=True):
            cached_conds_file = os.path.join(TTS_OUTPUT_DIR, "voice_clone_conds.pt")
            if os.path.exists(cached_conds_file) and os.path.getsize(cached_conds_file) > 1000:
                try:
                    try:
                        self.conds = torch.load(cached_conds_file, map_location=self.device, weights_only=False)
                    except TypeError:
                        self.conds = torch.load(cached_conds_file, map_location=self.device)
                    print(f"[TTS] ✓ Loaded Chatterbox voice conditionals from {cached_conds_file} in 0.01s!")
                    return
                except Exception:
                    pass

            import librosa
            s3gen_ref_wav, _sr = librosa.load(wav_fpath, sr=24000)
            s3gen_ref_wav = np.asarray(s3gen_ref_wav, dtype=np.float32)
            if norm_loudness:
                s3gen_ref_wav = self.norm_loudness(s3gen_ref_wav, _sr)
                s3gen_ref_wav = np.asarray(s3gen_ref_wav, dtype=np.float32)
            ref_16k_wav = librosa.resample(s3gen_ref_wav, orig_sr=24000, target_sr=16000)
            ref_16k_wav = np.asarray(ref_16k_wav, dtype=np.float32)

            s3gen_ref_wav = s3gen_ref_wav[:self.DEC_COND_LEN]
            s3gen_ref_dict = self.s3gen.embed_ref(s3gen_ref_wav, 24000, device=self.device)

            if plen := self.t3.hp.speech_cond_prompt_len:
                s3_tokzr = self.s3gen.tokenizer
                t3_cond_prompt_tokens, _ = s3_tokzr.forward([ref_16k_wav[:self.ENC_COND_LEN]], max_len=plen)
                t3_cond_prompt_tokens = torch.atleast_2d(t3_cond_prompt_tokens).to(self.device)

            ve_embed = torch.from_numpy(self.ve.embeds_from_wavs([ref_16k_wav], sample_rate=16000))
            ve_embed = ve_embed.float().mean(axis=0, keepdim=True).to(self.device)

            from chatterbox.models.t3.modules.cond_enc import T3Cond
            from chatterbox.tts_turbo import Conditionals
            t3_cond = T3Cond(
                speaker_emb=ve_embed,
                cond_prompt_speech_tokens=t3_cond_prompt_tokens,
                emotion_adv=exaggeration * torch.ones(1, 1, 1, device=self.device, dtype=torch.float32),
            ).to(device=self.device)
            self.conds = Conditionals(t3_cond, s3gen_ref_dict)
            try:
                os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)
                torch.save(self.conds, cached_conds_file)
            except Exception:
                pass

        _turbo_mod.ChatterboxTurboTTS.prepare_conditionals = _safe_turbo_prep
    except Exception:
        pass
except Exception:
    pass


def get_chatterbox_model():
    """Lazily load ChatterboxTurboTTS inside active GPU context."""
    global chatterbox_model, _device, _cached_chatterbox_ref
    if chatterbox_model is not None:
        return chatterbox_model

    device_to_use = "cuda" if torch.cuda.is_available() else "cpu"
    try:
        from chatterbox.tts_turbo import ChatterboxTurboTTS  # type: ignore
        chatterbox_model = ChatterboxTurboTTS.from_pretrained(device=device_to_use)
        _device = device_to_use
        print(f"[TTS] ChatterboxTurboTTS lazily loaded on {device_to_use}")

        ref_cand = _resolve_reference_audio()
        if ref_cand and os.path.exists(ref_cand):
            try:
                chatterbox_model.prepare_conditionals(os.path.abspath(ref_cand))
                _cached_chatterbox_ref = os.path.abspath(ref_cand)
                print(f"[TTS] Pre-computed Chatterbox voice conditionals from {ref_cand}")
            except Exception as _ce:
                print(f"[TTS] Voice condition cache note: {_ce}")
        return chatterbox_model
    except Exception as _turbo_err:
        raise RuntimeError(f"ChatterboxTurboTTS load failed: {_turbo_err}") from _turbo_err


def _synthesize_chatterbox(text: str, reference_audio: str = None, exaggeration: float = 0.5, cfg_weight: float = 0.0) -> str:
    """Chatterbox Turbo synthesis."""
    global chatterbox_model, _cached_chatterbox_ref
    if chatterbox_model is None:
        chatterbox_model = get_chatterbox_model()

    ref_audio = _resolve_reference_audio(reference_audio)
    prompt_to_pass = ref_audio
    if getattr(chatterbox_model, "conds", None) is not None and _cached_chatterbox_ref == ref_audio:
        prompt_to_pass = None
    else:
        _cached_chatterbox_ref = ref_audio

    os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)
    timestamp = int(time.time() * 1000)
    output_path = os.path.join(TTS_OUTPUT_DIR, f"output_{timestamp}.wav")

    clean_text = re.sub(r'[*_#`~\[\]()]', ' ', text)
    clean_text = re.sub(r'https?://\S+', '', clean_text)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    if not clean_text:
        clean_text = text.strip() or "Hello"

    try:
        wav = chatterbox_model.generate(clean_text, audio_prompt_path=prompt_to_pass)
    except TypeError:
        wav = chatterbox_model.generate(clean_text, audio_prompt_path=prompt_to_pass, exaggeration=exaggeration, cfg_weight=cfg_weight)

    # Chatterbox Turbo generates at 24,000 Hz; resample to 48,000 Hz PCM for telephony standard
    native_sr = int(getattr(chatterbox_model, "sr", 24000))
    return _standardize_and_save_audio(wav, native_sr=native_sr, output_path=output_path, target_sr=48000)


# ---------------------------------------------------------------------------
# F5-TTS Engine (Flow-Matching Non-Autoregressive - Option A)
# ---------------------------------------------------------------------------
f5_model = None


def prewarm_model(engine: str = None, reference_audio: str = None) -> None:
    """
    Pre-load the active TTS model (F5-TTS / LuxTTS) and warm the default
    reference transcript cache in a background daemon thread at server startup.
    Prevents the first live call from waiting 15-30s for model + Whisper load.
    """
    import threading

    cfg_engine = getattr(config, "TWILIO_VOICE_ENGINE", None) if config else None
    target = (engine or cfg_engine or os.getenv("TTS_ENGINE", "f5tts")).lower()

    def _load():
        try:
            t0 = time.time()
            if target in ("f5tts", "f5-tts", "f5"):
                model = get_f5_model()
                try:
                    resolved = _resolve_reference_audio(reference_audio)
                    clean_ref = _prepare_clean_f5_reference(resolved)
                    _ensure_f5_ref_transcript(model, clean_ref)
                except Exception as _re:
                    print(f"[TTS Prewarm] Reference transcript cache note: {_re}")
                print(f"[TTS Prewarm] ✓ F5-TTS model & ref cache pre-loaded in {time.time()-t0:.1f}s — first call will NOT cold-start.")
            elif target in ("luxtts", "lux"):
                get_luxtts_model()
                print(f"[TTS Prewarm] ✓ LuxTTS model pre-loaded in {time.time()-t0:.1f}s.")
            else:
                print(f"[TTS Prewarm] Engine '{target}' needs no model pre-load.")
        except Exception as _e:
            print(f"[TTS Prewarm] Model load note (non-fatal): {_e}")

    threading.Thread(target=_load, daemon=True, name="tts-prewarm").start()


def get_f5_model():
    """Lazily load F5-TTS model inside active GPU context."""
    global f5_model
    if f5_model is not None:
        return f5_model

    device_to_use = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[TTS F5-TTS] Initializing F5-TTS on {device_to_use}...")
    t0 = time.time()
    try:
        from f5_tts.api import F5TTS
    except ImportError:
        print("[TTS F5-TTS] ⚡ f5-tts package missing from environment, auto-installing now...")
        import subprocess
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "f5-tts"])
            from f5_tts.api import F5TTS
        except Exception as _install_err:
            raise RuntimeError(f"F5-TTS auto-install failed: {_install_err}") from _install_err

    try:
        f5_model = F5TTS(model="F5TTS_v1_Base", device=device_to_use)
        print(f"[TTS F5-TTS] ✓ F5-TTS model loaded in {time.time() - t0:.2f}s")
        return f5_model
    except Exception as _f5_err:
        raise RuntimeError(f"F5-TTS load failed: {_f5_err}") from _f5_err


def _get_audio_duration(audio_path: str) -> float:
    """Return audio duration in seconds without relying on deprecated torchaudio.info."""
    import subprocess
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            return float(res.stdout.strip())
    except Exception:
        pass
    try:
        wv, sr = torchaudio.load(audio_path)
        return float(wv.shape[-1]) / float(sr)
    except Exception:
        return 0.0


def _prepare_clean_f5_reference(ref_audio: str) -> str:
    """
    Ensure reference audio is <= 9.8s cut cleanly on a natural speech pause,
    keyed by source path+mtime+size so distinct voices never overwrite each other.
    Eliminates F5-TTS 'Audio is over 12s, clipping short' mid-word cuts.
    """
    import hashlib, subprocess
    if not ref_audio or not os.path.exists(ref_audio):
        return ref_audio

    dur = _get_audio_duration(ref_audio)
    if dur <= 10.5 and dur > 0:
        return ref_audio

    os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)
    st = os.stat(ref_audio)
    sig = f"v3|{os.path.abspath(ref_audio)}|{st.st_size}|{int(st.st_mtime)}".encode("utf-8")
    h = hashlib.sha1(sig).hexdigest()[:12]
    trimmed_path = os.path.join(TTS_OUTPUT_DIR, f"ref_{h}.wav")
    if os.path.exists(trimmed_path) and os.path.getsize(trimmed_path) > 1000:
        return trimmed_path

    start_sec = 0.0
    end_sec = 9.5
    try:
        sd = subprocess.run(
            ["ffmpeg", "-i", ref_audio, "-af", "silencedetect=noise=-30dB:d=0.25", "-f", "null", "-"],
            capture_output=True, text=True, timeout=10,
        )
        sil_starts, sil_ends = [], []
        for line in sd.stderr.splitlines():
            m_s = re.search(r"silence_start:\s*([0-9.]+)", line)
            m_e = re.search(r"silence_end:\s*([0-9.]+)", line)
            if m_s:
                sil_starts.append(float(m_s.group(1)))
            if m_e:
                sil_ends.append(float(m_e.group(1)))
        # Skip initial mic-silence if speech begins early
        if sil_ends and sil_ends[0] <= 1.2:
            start_sec = max(0.0, sil_ends[0] - 0.1)
        # Pick the latest pause whose segment duration stays <= 9.8s (min 4.5s speech)
        best_end = None
        for s_start in sil_starts:
            seg = s_start - start_sec
            if 4.5 <= seg <= 9.8:
                best_end = s_start + 0.08
        if best_end is not None:
            end_sec = best_end
        elif dur > 0:
            end_sec = min(dur, start_sec + 9.5)
    except Exception:
        end_sec = min(dur, 9.5) if dur > 0 else 9.5

    clip_dur = max(4.0, min(9.8, end_sec - start_sec))
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{start_sec:.3f}", "-t", f"{clip_dur:.3f}",
             "-i", ref_audio, "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", trimmed_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=15,
        )
        # Preserve explicit sidecar .txt only if original was NOT trimmed past a mismatch
        print(f"[TTS F5-TTS] Cleanly trimmed reference {dur:.1f}s -> {clip_dur:.2f}s at pause ({os.path.basename(trimmed_path)}).")
        return trimmed_path
    except Exception:
        try:
            _wv, _sr = torchaudio.load(ref_audio)
            _s = int(start_sec * _sr)
            _e = min(_s + int(clip_dur * _sr), _wv.shape[-1])
            torchaudio.save(trimmed_path, _wv[:, _s:_e], _sr)
            return trimmed_path
        except Exception:
            return ref_audio


def _ensure_f5_ref_transcript(model, ref_audio: str) -> str:
    """Load or generate & cache sidecar .txt for *ref_audio* so Whisper never re-runs on live calls."""
    if not ref_audio or not os.path.exists(ref_audio):
        return ""
    ref_txt_path = os.path.splitext(ref_audio)[0] + ".txt"
    if os.path.exists(ref_txt_path):
        try:
            with open(ref_txt_path, "r", encoding="utf-8") as f:
                cached = f.read().strip()
            if cached:
                return cached
        except Exception:
            pass
    if model is not None and hasattr(model, "transcribe"):
        try:
            txt = (model.transcribe(ref_audio) or "").strip()
            if txt:
                with open(ref_txt_path, "w", encoding="utf-8") as f:
                    f.write(txt)
                print(f"[TTS F5-TTS] Cached ref transcript to {os.path.basename(ref_txt_path)}: '{txt[:60]}'")
                return txt
        except Exception as _te:
            print(f"[TTS F5-TTS] Ref transcribe cache note: {_te}")
    return ""


def _normalize_for_f5tts(text: str) -> str:
    """Normalize unicode whitespace and shorthand while preserving ?, !, and comma prosody."""
    t = text or ""
    # Replace non-breaking / narrow spaces (e.g. '1\u202fp.m.') and curly quotes
    t = t.replace("\u202f", " ").replace("\u00a0", " ").replace("\u200b", "")
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("—", ", ").replace("–", ", ").replace(";", ",")
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"[*_#`~\[\]()]", " ", t)
    # Expand common spoken time / symbol shorthand that neural TTS stumbles on
    t = re.sub(r"\b(\d{1,2}):00\s*([Aa])\.?[Mm]\.?(?=\s|$|[.,?!])", r"\1 A M", t)
    t = re.sub(r"\b(\d{1,2}):00\s*([Pp])\.?[Mm]\.?(?=\s|$|[.,?!])", r"\1 P M", t)
    t = re.sub(r"\b(\d{1,2})\s*([Aa])\.?[Mm]\.?(?=\s|$|[.,?!])", r"\1 A M", t)
    t = re.sub(r"\b(\d{1,2})\s*([Pp])\.?[Mm]\.?(?=\s|$|[.,?!])", r"\1 P M", t)
    t = t.replace("%", " percent").replace("&", " and ")
    t = re.sub(r"!{2,}", "!", t)
    t = re.sub(r"\?{2,}", "?", t)
    t = re.sub(r"\.{3,}", "...", t)
    t = re.sub(r"\s+([,?!.])", r"\1", t)
    t = re.sub(r"([,?!])(?=[^\s\"',?!.])", r"\1 ", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t or "Hello!"


def _synthesize_f5tts(text: str, reference_audio: str = None) -> str:
    """High-accuracy Flow Matching voice cloning using F5-TTS."""
    global f5_model
    model = get_f5_model()
    ref_audio = _prepare_clean_f5_reference(_resolve_reference_audio(reference_audio))
    clean_text = _normalize_for_f5tts(text)
    ref_text = _ensure_f5_ref_transcript(model, ref_audio)

    os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)
    timestamp = int(time.time() * 1000)
    output_path = os.path.join(TTS_OUTPUT_DIR, f"output_{timestamp}.wav")

    nfe_steps = int(os.getenv("F5_NFE_STEP", "16") or "16")
    # Default 2.0 preserves normal, realistic pitch stability without weird warble
    cfg_strength = float(os.getenv("F5_CFG_STRENGTH", "2.0") or "2.0")
    t0 = time.time()
    wav, sr, _ = model.infer(
        ref_file=ref_audio,
        ref_text=ref_text,
        gen_text=clean_text,
        file_wave=output_path,
        nfe_step=nfe_steps,
        cfg_strength=cfg_strength,
        sway_sampling_coef=-1.0,
        cross_fade_duration=0.15,
        speed=1.0,
    )
    gen_duration = time.time() - t0
    print(f"[TTS F5-TTS] ⚡ Generated speech in {gen_duration:.3f}s for '{clean_text[:40]}...'")

    native_sr = int(sr) if sr else 24000
    return _standardize_and_save_audio(wav, native_sr=native_sr, output_path=output_path, target_sr=48000)


# ---------------------------------------------------------------------------
# Edge-TTS Engine (High-Fidelity Studio Voices for Carrier Native Profiles)
# ---------------------------------------------------------------------------
def _synthesize_edge_tts(text: str, voice_type: str = "female", voice_id_override: str = None) -> str:
    """
    Synthesize natural carrier voice using edge-tts.
    Supports English (Joanna/Matthew), Hindi, Kannada, and other edge-tts neural voices.
    Ultra-crisp studio quality, 0.2s generation, 0 GPU memory.
    """
    import asyncio, concurrent.futures
    os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)
    timestamp = int(time.time() * 1000)
    output_path = os.path.join(TTS_OUTPUT_DIR, f"output_{timestamp}.wav")
    mp3_tmp = os.path.join(TTS_OUTPUT_DIR, f"temp_{timestamp}.mp3")

    v_lower = (voice_type or "female").lower()
    is_indic = any('\u0c80' <= ch <= '\u0cff' or '\u0900' <= ch <= '\u097f' for ch in text)

    # If a specific voice_id is passed (e.g. for Kannada/Hindi), use it directly
    if voice_id_override:
        voice_id = voice_id_override
        fallback_wav = None
    elif any(k in v_lower for k in ["female", "joanna", "woman", "sarah"]):
        voice_id = "en-US-JennyNeural"
        fallback_wav = os.path.join(_BASE_DIR, "default_voices", "joanna_greeting.wav")
    else:
        voice_id = "en-US-GuyNeural"
        fallback_wav = os.path.join(_BASE_DIR, "default_voices", "matthew_greeting.wav")

    clean_text = re.sub(r'[*_#`~\[\]()]', ' ', text)
    clean_text = re.sub(r'https?://\S+', '', clean_text).strip()
    if not clean_text:
        clean_text = "Namaskara" if is_indic else "Hello, how can I assist you today?"

    success = False
    # Attempt 1: Direct in-process async communicate in isolated worker thread
    try:
        def _run_edge_direct(t, v, p):
            import edge_tts
            async def _coro():
                c = edge_tts.Communicate(t, v)
                await c.save(p)
            l = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(l)
                l.run_until_complete(_coro())
            finally:
                l.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            ex.submit(_run_edge_direct, clean_text, voice_id, mp3_tmp).result(timeout=15)
        success = os.path.exists(mp3_tmp) and os.path.getsize(mp3_tmp) > 200
    except Exception as d_err:
        pass

    # Attempt 2: CLI subprocess fallback
    if not success:
        try:
            import subprocess
            res = subprocess.run(
                [sys.executable, "-m", "edge_tts", "--text", clean_text, "--voice", voice_id, "--write-media", mp3_tmp],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20
            )
            success = (res.returncode == 0 and os.path.exists(mp3_tmp) and os.path.getsize(mp3_tmp) > 200)
        except Exception:
            pass

    if success and os.path.exists(mp3_tmp):
        try:
            import subprocess
            subprocess.run(
                ["ffmpeg", "-y", "-i", mp3_tmp, "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", output_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
            )
            try: os.remove(mp3_tmp)
            except Exception: pass
            return output_path
        except Exception as f_err:
            print(f"[TTS Edge-TTS ffmpeg note]: {f_err}")

    # Fallback to pre-rendered high quality audio ONLY for greeting-like phrases
    if fallback_wav and not (voice_id_override or is_indic):
        _is_greeting_text = any(w in clean_text.lower() for w in ["thank you for calling", "how may i assist", "how can i help", "this is joanna", "this is matthew"])
        if _is_greeting_text:
            for candidate in [fallback_wav, os.path.join("default_voices", os.path.basename(fallback_wav)), os.path.join("backend", "default_voices", os.path.basename(fallback_wav))]:
                if os.path.exists(candidate):
                    import shutil as _sh
                    _sh.copyfile(candidate, output_path)
                    return output_path

    # If this is an Indic voice or Indic text, NEVER fall back to English LuxTTS!
    if voice_id_override or is_indic:
        raise RuntimeError(f"Edge-TTS synthesis failed to generate audio for voice {voice_id}")

    # For dynamic English text only, synthesize with LuxTTS using female/male reference audio
    female_ref = os.path.join("default_voices", "female_reference.wav")
    ref = female_ref if "female" in v_lower and os.path.exists(female_ref) else None
    return _synthesize_luxtts(clean_text, reference_audio=ref)


# ---------------------------------------------------------------------------
# Public Unified API
# ---------------------------------------------------------------------------
def synthesize(
    text: str,
    reference_audio: str = None,
    exaggeration: float = 0.5,
    cfg_weight: float = 0.0,
    engine: str = None,
) -> str:
    """
    Synthesize speech from *text* using voice cloning or native carrier engine.
    Supports F5-TTS, LuxTTS (~150x real-time), Chatterbox Turbo, and Studio Native Voices (Joanna / Matthew).
    Selectable per-call via `engine` argument or environment variable TTS_ENGINE.
    """
    engine_preference = (engine or os.getenv("TTS_ENGINE", "f5tts")).lower()

    # ── Strict Priority 1: Multilingual Neural Voices (Indic: Kannada & Hindi) ──
    # Detect language script in text for early, zero-failure native routing
    is_kannada_script = any('\u0c80' <= ch <= '\u0cff' for ch in text)
    is_hindi_script = any('\u0900' <= ch <= '\u097f' for ch in text)

    # Route Kannada (Sapna or Gagan)
    if is_kannada_script or any(k in engine_preference for k in ["kannada", "kn", "kn-in"]):
        target_voice = "kn-IN-GaganNeural" if "male" in engine_preference else "kn-IN-SapnaNeural"
        return _synthesize_edge_tts(text, voice_id_override=target_voice)

    # Route Hindi (Swara or Madhur)
    if is_hindi_script or any(k in engine_preference for k in ["hindi", "hi", "hi-in"]):
        target_voice = "hi-IN-MadhurNeural" if "male" in engine_preference else "hi-IN-SwaraNeural"
        return _synthesize_edge_tts(text, voice_id_override=target_voice)

    # Generic edge-tts voice override (voice_id passed directly e.g. "edge:kn-IN-SapnaNeural")
    if engine_preference.startswith("edge:"):
        voice_id_override = engine_preference[5:]
        return _synthesize_edge_tts(text, voice_id_override=voice_id_override)

    # Native Studio / Polly voices (US Female Joanna & US Male Matthew)
    if any(k in engine_preference for k in ["polly_joanna", "joanna", "polly_female"]):
        return _synthesize_edge_tts(text, voice_type="female")

    if any(k in engine_preference for k in ["polly_matthew", "matthew", "polly_male", "polly"]):
        return _synthesize_edge_tts(text, voice_type="male")

    # Detect language script in text for intelligent fallback
    is_kannada_script = any('\u0c80' <= ch <= '\u0cff' for ch in text)
    is_hindi_script = any('\u0900' <= ch <= '\u097f' for ch in text)

    if engine_preference in ["f5tts", "f5-tts", "f5"]:
        try:
            return _synthesize_f5tts(text, reference_audio)
        except Exception as f5_err:
            if is_kannada_script:
                print(f"[TTS WARNING] F5-TTS failed for Kannada text: {f5_err}. Falling back to native studio Kannada voice...")
                return _synthesize_edge_tts(text, voice_id_override="kn-IN-SapnaNeural")
            elif is_hindi_script:
                print(f"[TTS WARNING] F5-TTS failed for Hindi text: {f5_err}. Falling back to native studio Hindi voice...")
                return _synthesize_edge_tts(text, voice_id_override="hi-IN-SwaraNeural")
            print(f"[TTS WARNING] F5-TTS failed: {f5_err}. Falling back to LuxTTS...")
            try:
                return _synthesize_luxtts(text, reference_audio)
            except Exception as lux_err:
                print(f"[TTS WARNING] LuxTTS fallback also failed: {lux_err}. Falling back to native Edge-TTS...")
                return _synthesize_edge_tts(text, voice_type="female")

    if engine_preference in ["chatterbox", "turbo"]:
        # Legacy fallback - route cleanly to ultra-fast LuxTTS (or F5-TTS)
        try:
            return _synthesize_luxtts(text, reference_audio)
        except Exception:
            try:
                return _synthesize_f5tts(text, reference_audio)
            except Exception:
                return _synthesize_edge_tts(text, voice_type="female")

    if engine_preference in ["luxtts", "lux"]:
        if is_kannada_script:
            return _synthesize_edge_tts(text, voice_id_override="kn-IN-SapnaNeural")
        if is_hindi_script:
            return _synthesize_edge_tts(text, voice_id_override="hi-IN-SwaraNeural")
        try:
            return _synthesize_luxtts(text, reference_audio)
        except Exception as lux_err:
            print(f"[TTS WARNING] LuxTTS failed: {lux_err}. Falling back to F5-TTS...")
            try:
                return _synthesize_f5tts(text, reference_audio)
            except Exception as f5_err:
                print(f"[TTS WARNING] F5-TTS fallback also failed: {f5_err}. Falling back to native Edge-TTS...")
                return _synthesize_edge_tts(text, voice_type="female")

    # Default fallback: try LuxTTS first, then F5-TTS, with native fallback for Indic scripts
    if is_kannada_script:
        return _synthesize_edge_tts(text, voice_id_override="kn-IN-SapnaNeural")
    if is_hindi_script:
        return _synthesize_edge_tts(text, voice_id_override="hi-IN-SwaraNeural")

    try:
        return _synthesize_luxtts(text, reference_audio)
    except Exception:
        try:
            return _synthesize_f5tts(text, reference_audio)
        except Exception:
            return _synthesize_edge_tts(text, voice_type="female")


def prewarm_engine(greeting_text: str = None, engine: str = None, reference_audio: str = None) -> str:
    """
    Pre-warms the active TTS engine on GPU, caches voice conditionals,
    and pre-generates ready-to-play telephony audio:
    1. 'prewarmed_greeting.wav' (initial greeting)
    2. 'prewarmed_reprompt.wav' (silence reprompt)
    3. 'prewarmed_goodbye.wav' (call exit)
    """
    import shutil
    if greeting_text is None:
        greeting_text = "Hello there! This is Alex calling from Vocalyx. How are you doing today?"

    os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)
    prewarmed_path = os.path.join(TTS_OUTPUT_DIR, "prewarmed_greeting.wav")

    cfg_engine = getattr(config, "TWILIO_VOICE_ENGINE", None) if config else None
    active_engine = (engine or cfg_engine or os.getenv("TTS_ENGINE", "f5tts")).lower()

    print(f"[TTS Pre-Warm] Warming up '{active_engine}' engine (ref={reference_audio or 'default'}) with greeting: '{greeting_text[:40]}...'")
    t0 = time.time()
    wav_path = synthesize(greeting_text, reference_audio=reference_audio, engine=active_engine)
    total_time = time.time() - t0

    if wav_path and os.path.exists(wav_path):
        shutil.copy2(wav_path, prewarmed_path)
        print(f"[TTS Pre-Warm] ⚡ Pre-warmed greeting ({active_engine}) generated in {total_time:.2f}s! Ready at: {prewarmed_path}")
        # Save the greeting text alongside the WAV so twilio_voice_webhook can use the exact same text
        # in the call transcript, keeping chat display and actual audio in sync.
        try:
            greeting_txt_path = os.path.join(TTS_OUTPUT_DIR, "prewarmed_greeting.txt")
            with open(greeting_txt_path, "w", encoding="utf-8") as _gtf:
                _gtf.write(greeting_text)
        except Exception as _gtw_err:
            print(f"[TTS Pre-Warm] greeting text save note: {_gtw_err}")

    # Also pre-generate reprompt and goodbye
    reprompt_file = os.path.join(TTS_OUTPUT_DIR, "prewarmed_reprompt.wav")
    try:
        rw = synthesize("Are you still there? Please let me know how I can help.", reference_audio=reference_audio, engine=active_engine)
        if rw and os.path.exists(rw):
            shutil.copy2(rw, reprompt_file)
    except Exception as _re:
        print(f"[TTS Pre-Warm Reprompt Note]: {_re}")

    goodbye_file = os.path.join(TTS_OUTPUT_DIR, "prewarmed_goodbye.wav")
    try:
        gw = synthesize("Thank you for your time with Vocalyx. Have a wonderful day!", reference_audio=reference_audio, engine=active_engine)
        if gw and os.path.exists(gw):
            shutil.copy2(gw, goodbye_file)
    except Exception as _ge:
        print(f"[TTS Pre-Warm Goodbye Note]: {_ge}")

    return prewarmed_path
