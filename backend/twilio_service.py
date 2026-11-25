"""
VOCALYX — Twilio Telephony Service
Handles real phone calls (outbound & inbound), TwiML generation,
speech gathering, and call lifecycle with Groq LLM + Chatterbox TTS.
"""

import os
import re
import json
import time
import traceback
from typing import Dict, Any, Optional, List
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather, Play, Say, Hangup

from backend import config

# Active calls state keyed by call_sid
# Structure: { call_sid: { contact_id, contact_name, to_number, from_number, mode, transcript: [], start_time, status } }
active_calls: Dict[str, Dict[str, Any]] = {}

# Pre-generated audio files for zero-latency greeting playback
# Keys: call_sid, contact_id, to_number, or call_sid:turn_id -> wav_path
pregenerated_audio: Dict[str, str] = {}

# Background synthesis futures keyed by synth_key (kept outside active_calls so active_calls stays JSON-serializable)
pending_synth_futures: Dict[str, Any] = {}

TWILIO_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "twilio_settings.json")


def _load_persisted_config():
    """Load credentials from disk if available to survive cloud restarts."""
    for cand in [TWILIO_SETTINGS_FILE, "twilio_settings.json", os.path.join("backend", "twilio_settings.json")]:
        if os.path.exists(cand):
            try:
                with open(cand, "r") as f:
                    data = json.load(f)
                if data.get("account_sid"):
                    config.TWILIO_ACCOUNT_SID = data["account_sid"]
                    os.environ["TWILIO_ACCOUNT_SID"] = data["account_sid"]
                if data.get("auth_token"):
                    config.TWILIO_AUTH_TOKEN = data["auth_token"]
                    os.environ["TWILIO_AUTH_TOKEN"] = data["auth_token"]
                if data.get("phone_number"):
                    config.TWILIO_PHONE_NUMBER = data["phone_number"]
                    os.environ["TWILIO_PHONE_NUMBER"] = data["phone_number"]
                if data.get("public_base_url"):
                    config.PUBLIC_BASE_URL = data["public_base_url"]
                    os.environ["PUBLIC_BASE_URL"] = data["public_base_url"]
                if data.get("voice_engine"):
                    config.TWILIO_VOICE_ENGINE = data["voice_engine"]
                    os.environ["TWILIO_VOICE_ENGINE"] = data["voice_engine"]
                print(f"[Twilio Config] Restored credentials from {cand}")
                break
            except Exception as _e:
                print(f"[Twilio Config Load Note]: {_e}")


def _persist_config():
    """Save credentials to disk so they survive server restarts."""
    try:
        data = {
            "account_sid": config.TWILIO_ACCOUNT_SID,
            "auth_token": config.TWILIO_AUTH_TOKEN,
            "phone_number": config.TWILIO_PHONE_NUMBER,
            "public_base_url": config.PUBLIC_BASE_URL,
            "voice_engine": getattr(config, "TWILIO_VOICE_ENGINE", "f5tts"),
        }
        for dest in [TWILIO_SETTINGS_FILE, "twilio_settings.json"]:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
                with open(dest, "w") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass
    except Exception as _pe:
        print(f"[Twilio Config Save Note]: {_pe}")


_load_persisted_config()


def get_config() -> Dict[str, str]:
    return {
        "account_sid": config.TWILIO_ACCOUNT_SID,
        "auth_token": config.TWILIO_AUTH_TOKEN,
        "phone_number": config.TWILIO_PHONE_NUMBER,
        "public_base_url": config.PUBLIC_BASE_URL,
        "voice_engine": getattr(config, "TWILIO_VOICE_ENGINE", "f5tts"),
    }


def update_config(account_sid: str = None, auth_token: str = None, phone_number: str = None, public_url: str = None, voice_engine: str = None):
    if account_sid is not None and account_sid.strip() and not account_sid.strip().startswith("..."):
        config.TWILIO_ACCOUNT_SID = account_sid.strip()
        os.environ["TWILIO_ACCOUNT_SID"] = config.TWILIO_ACCOUNT_SID
    if auth_token is not None and auth_token.strip():
        config.TWILIO_AUTH_TOKEN = auth_token.strip()
        os.environ["TWILIO_AUTH_TOKEN"] = config.TWILIO_AUTH_TOKEN
    if phone_number is not None and phone_number.strip():
        config.TWILIO_PHONE_NUMBER = phone_number.strip()
        os.environ["TWILIO_PHONE_NUMBER"] = config.TWILIO_PHONE_NUMBER
    if public_url is not None and public_url.strip():
        config.PUBLIC_BASE_URL = public_url.strip().rstrip("/")
        os.environ["PUBLIC_BASE_URL"] = config.PUBLIC_BASE_URL
    if voice_engine is not None and voice_engine.strip():
        config.TWILIO_VOICE_ENGINE = voice_engine.strip().lower()
        os.environ["TWILIO_VOICE_ENGINE"] = config.TWILIO_VOICE_ENGINE
    _persist_config()



def is_configured() -> bool:
    return bool(config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN and config.TWILIO_PHONE_NUMBER)


def get_client() -> Optional[Client]:
    if not (config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN):
        return None
    return Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)


def verify_credentials() -> Dict[str, Any]:
    if not is_configured():
        return {
            "ok": False,
            "error": "Twilio Account SID, Auth Token, or Phone Number is not set.",
            "configured": False,
        }
    try:
        client = get_client()
        account = client.api.accounts(config.TWILIO_ACCOUNT_SID).fetch()
        return {
            "ok": True,
            "configured": True,
            "account_name": account.friendly_name,
            "status": account.status,
            "phone_number": config.TWILIO_PHONE_NUMBER,
        }
    except Exception as exc:
        return {
            "ok": False,
            "configured": True,
            "error": str(exc),
            "phone_number": config.TWILIO_PHONE_NUMBER,
        }


def format_phone_number(raw: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", raw.strip())
    if not cleaned.startswith("+"):
        # Default to + if numeric
        cleaned = "+" + cleaned
    return cleaned


def resolve_base_url(request_base: str = None) -> str:
    """Return the public URL for Twilio webhooks, ensuring cloud HTTPS reachability."""
    if config.PUBLIC_BASE_URL and not any(h in config.PUBLIC_BASE_URL for h in ["0.0.0.0", "127.0.0.1", "localhost"]):
        return config.PUBLIC_BASE_URL.rstrip("/")
    space_host = os.getenv("SPACE_HOST")
    if space_host and not any(h in space_host for h in ["0.0.0.0", "127.0.0.1", "localhost"]):
        return f"https://{space_host}".rstrip("/")
    space_id = os.getenv("SPACE_ID")
    if space_id:
        slug = space_id.replace("/", "-")
        return f"https://{slug}.hf.space".rstrip("/")
    if request_base and not any(h in request_base for h in ["0.0.0.0", "127.0.0.1", "localhost"]):
        return request_base.rstrip("/")
    return "https://ebedsouza-vocalyx.hf.space"


def build_greeting_text(
    persona_name: str = "Alex",
    contact_name: str = "there",
    language: str = "en-US",
    mode: str = "outbound",
) -> str:
    """Build synchronized greeting text used identically in chat UI, pre-warm audio, and Twilio calls."""
    persona = (persona_name or "Alex").strip() or "Alex"
    cname = (contact_name or "").strip() or "there"
    lang = (language or "en-US").strip()
    m = (mode or "outbound").strip().lower()

    if lang in ("kn-IN", "kn"):
        kn_name = cname if cname != "there" else "ಸ್ನೇಹಿತರೆ"
        if m == "inbound":
            return (
                f"ನಮಸ್ಕಾರ {kn_name}! ವೋಕಲಿಕ್ಸ್‌ಗೆ ಸ್ವಾಗತ, ನಾನು {persona}. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?"
                if cname != "there"
                else f"ನಮಸ್ಕಾರ, ವೋಕಲಿಕ್ಸ್‌ಗೆ ಸ್ವಾಗತ! ನನ್ನ ಹೆಸರು {persona}. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಲ್ಲೆನು?"
            )
        if m == "marketing":
            return f"ನಮಸ್ಕಾರ {kn_name}! ವೋಕಲಿಕ್ಸ್‌ನಿಂದ {persona} ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ. ಒಂದು ನಿಮಿಷ ಸಮಯವಿದೆಯೇ?"
        return f"ನಮಸ್ಕಾರ {kn_name}! ವೋಕಲಿಕ್ಸ್‌ನಿಂದ {persona} ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ. ಹೇಗಿದ್ದೀರಾ?"

    if lang in ("hi-IN", "hi"):
        hi_name = cname if cname != "there" else "जी"
        if m == "inbound":
            return (
                f"नमस्ते {hi_name}! वोकलिक्स में आपका स्वागत है, मैं {persona} बोल रहा हूँ। मैं आपकी क्या मदद कर सकता हूँ?"
                if cname != "there"
                else f"नमस्ते, वोकलिक्स में आपका स्वागत है! मेरा नाम {persona} है। मैं आपकी क्या मदद कर सकता हूँ?"
            )
        if m == "marketing":
            return f"नमस्ते {hi_name}! वोकलिक्स से {persona} बोल रहा हूँ। क्या आपके पास एक मिनट का समय है?"
        return f"नमस्ते {hi_name}! वोकलिक्स से {persona} बोल रहा हूँ। आप कैसे हैं?"

    if m == "inbound":
        if cname != "there":
            return f"Hello {cname}. Thank you for calling Vocalyx, this is {persona}. How can I help you today?"
        return f"Hello, thank you for calling Vocalyx. My name is {persona}. How may I assist you today?"
    if m == "marketing":
        return f"Hi {cname}. This is {persona} calling from Vocalyx with an update for you. Do you have a quick minute?"
    return f"Hello {cname}. This is {persona} calling from Vocalyx. How are you doing today?"


def compute_greeting_signature(
    voice_engine: Optional[str] = None,
    voice_id: Optional[Any] = None,
    language: Optional[str] = None,
    contact_id: Optional[Any] = None,
    mode: Optional[str] = None,
    script_id: Optional[Any] = None,
    custom_context: Optional[str] = None,
    persona_name: Optional[str] = None,
) -> str:
    """Deterministic signature tying a pre-warmed greeting WAV to its exact call parameters."""
    import hashlib
    norm_ctx = re.sub(r"\s+", " ", (custom_context or "").strip())
    ctx_hash = hashlib.sha1(norm_ctx.encode("utf-8")).hexdigest()[:12] if norm_ctx else ""
    parts = [
        str(voice_engine or "f5tts").strip().lower(),
        str(voice_id or "").strip(),
        str(language or "en-US").strip(),
        str(contact_id or "").strip(),
        str(mode or "outbound").strip().lower(),
        str(script_id or "").strip(),
        str(persona_name or "").strip().lower(),
        ctx_hash,
    ]
    return "|".join(parts)


def _prewarm_meta_path() -> str:
    return os.path.join(config.TTS_OUTPUT_DIR, "prewarmed_greeting.meta.json")


def get_prewarm_meta() -> Dict[str, Any]:
    """Read metadata describing what prewarmed_greeting.wav was synthesized for."""
    meta_file = _prewarm_meta_path()
    if os.path.exists(meta_file):
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_prewarm_meta(meta: Dict[str, Any]) -> None:
    """Persist metadata describing the current prewarmed_greeting.wav."""
    try:
        os.makedirs(config.TTS_OUTPUT_DIR, exist_ok=True)
        with open(_prewarm_meta_path(), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
    except Exception as _me:
        print(f"[Twilio Pre-Warm Meta Note]: {_me}")


def make_outbound_call(to_number: str, contact_id: Optional[int] = None, mode: str = "outbound", base_url: str = None, voice_engine: Optional[str] = None, language: Optional[str] = None, voice_id: Optional[int] = None, reference_audio: Optional[str] = None, persona_name: Optional[str] = None, script_id: Optional[int] = None, custom_context: Optional[str] = None) -> Dict[str, Any]:
    if not is_configured():
        raise RuntimeError("Twilio is not configured. Please enter your Account SID, Auth Token, and Phone Number in Settings.")

    client = get_client()
    if not client:
        raise RuntimeError("Could not initialize Twilio client. Check credentials.")

    to_formatted = format_phone_number(to_number)
    from_formatted = format_phone_number(config.TWILIO_PHONE_NUMBER)
    public_url = resolve_base_url(base_url)

    if any(h in public_url for h in ["localhost", "0.0.0.0", "127.0.0.1"]):
        raise RuntimeError(
            f"Invalid public URL '{public_url}'. Twilio cannot reach localhost from the cloud. "
            f"Please ensure your ngrok URL is connected in Settings."
        )

    # Webhook URLs for Twilio
    voice_url = f"{public_url}/api/twilio/voice?mode={mode}"
    if contact_id:
        voice_url += f"&contact_id={contact_id}"
    if language:
        voice_url += f"&lang={language}"
    if script_id:
        voice_url += f"&script_id={script_id}"

    status_callback = f"{public_url}/api/twilio/status"
    if contact_id:
        status_callback += f"?contact_id={contact_id}"

    active_engine = (voice_engine or getattr(config, "TWILIO_VOICE_ENGINE", "f5tts")).lower()
    active_persona = (persona_name or ("Joanna" if "joanna" in active_engine else "Matthew" if "matthew" in active_engine else "Sapna" if "kannada_female" in active_engine else "Gagan" if "kannada_male" in active_engine else "Swara" if "hindi_female" in active_engine else "Madhur" if "hindi_male" in active_engine else "Alex")).strip() or "Alex"
    eff_lang = language or "en-US"
    clean_custom_ctx = (custom_context or "").strip()

    # Prepare exact greeting text + audio BEFORE dialing so audio and chat text NEVER disagree
    # and different contacts / scripts always receive their own tailored greeting.
    cname = "there"
    if contact_id:
        try:
            from backend import database, models
            with database.SessionLocal() as session:
                c = session.query(models.Contact).filter(models.Contact.id == int(contact_id)).first()
                if c and c.name:
                    cname = c.name
        except Exception:
            pass

    target_sig = compute_greeting_signature(
        voice_engine=active_engine,
        voice_id=voice_id,
        language=eff_lang,
        contact_id=contact_id,
        mode=mode,
        script_id=script_id,
        custom_context=clean_custom_ctx,
        persona_name=active_persona,
    )
    prewarmed_file = os.path.join(config.TTS_OUTPUT_DIR, "prewarmed_greeting.wav")
    has_prewarmed = os.path.exists(prewarmed_file) and os.path.getsize(prewarmed_file) > 1000
    prewarm_meta = get_prewarm_meta()
    sig_matches = bool(has_prewarmed and prewarm_meta.get("signature") == target_sig and prewarm_meta.get("text"))

    prepared_greeting_text = None
    prepared_greeting_wav = None

    if sig_matches:
        prepared_greeting_text = prewarm_meta["text"]
        prepared_greeting_wav = prewarmed_file
        print(f"[Twilio Pre-Gen] ✓ Pre-warmed greeting signature matched for {cname} (0.0s overhead).")
    else:
        # Generate contact + script specific greeting text once, and lock it to both audio and transcript
        if clean_custom_ctx:
            try:
                from backend import llm_engine
                prepared_greeting_text = llm_engine.generate_context_greeting(
                    persona_name=active_persona,
                    contact_name=cname,
                    script_content=clean_custom_ctx,
                    language=eff_lang,
                    mode=mode,
                )
            except Exception as _ge:
                print(f"[Twilio Pre-Gen Context Greeting Note]: {_ge}")
        if not prepared_greeting_text:
            prepared_greeting_text = build_greeting_text(
                persona_name=active_persona,
                contact_name=cname,
                language=eff_lang,
                mode=mode,
            )

        if active_engine not in ["polly", "twilio_say", "say"]:
            try:
                from backend import tts_engine
                print(f"[Twilio Pre-Gen] Generating personalized {active_engine} ({active_persona}) greeting for {cname}...")
                w_path = tts_engine.synthesize(prepared_greeting_text, reference_audio=reference_audio, engine=active_engine)
                if w_path and os.path.exists(w_path):
                    prepared_greeting_wav = w_path
                    print(f"[Twilio Pre-Gen] ✓ Personalized greeting ready: {os.path.basename(w_path)}")
            except Exception as pe:
                print(f"[Twilio Pre-Gen Note]: {pe}")

    print(f"[Twilio] Dialing {to_formatted} from {from_formatted} via {voice_url}")

    try:
        # Use strictly essential parameters compatible with all Twilio accounts (including free trial)
        call = client.calls.create(
            to=to_formatted,
            from_=from_formatted,
            url=voice_url,
        )
    except Exception as call_err:
        err_msg = str(call_err)
        if "21215" in err_msg or "Geo Permission" in err_msg:
            raise RuntimeError(
                f"Twilio Geo-Permission Blocked: Twilio US numbers cannot call {to_formatted} by default. "
                f"Enable '{to_formatted[:3]}' in Twilio Console ➔ Voice ➔ Settings ➔ Geo Permissions."
            ) from call_err
        if "21608" in err_msg or "unverified" in err_msg.lower():
            raise RuntimeError(
                f"Twilio Trial Restriction: {to_formatted} is not verified. "
                f"On a trial account, destination numbers must be verified in Twilio Console."
            ) from call_err
        if "20003" in err_msg or "authenticate" in err_msg.lower() or "401" in err_msg or "does not exist" in err_msg or "auth account" in err_msg:
            raise RuntimeError(
                f"Twilio Authentication Failed (HTTP 401): Account SID or Auth Token is incorrect/expired. "
                f"Please open Settings in the left sidebar, paste your active Account SID and Auth Token from twilio.com/console, and click 'Save & Verify Twilio'."
            ) from call_err
        raise RuntimeError(f"Twilio call failed: {err_msg}") from call_err

    active_calls[call.sid] = {
        "call_sid": call.sid,
        "contact_id": contact_id,
        "contact_name": cname,
        "to_number": to_formatted,
        "from_number": from_formatted,
        "mode": mode,
        "transcript": [],
        "start_time": time.time(),
        "status": call.status,
        "voice_engine": active_engine,
        "voice_id": voice_id,
        "reference_audio": reference_audio,
        "persona_name": active_persona,
        "language": eff_lang,
        "script_id": script_id,
        "custom_context": clean_custom_ctx,
        "greeting_text": prepared_greeting_text,
    }

    if prepared_greeting_wav and os.path.exists(prepared_greeting_wav):
        pregenerated_audio[call.sid] = prepared_greeting_wav
    else:
        pregenerated_audio.pop(call.sid, None)

    return {
        "success": True,
        "call_sid": call.sid,
        "to": to_formatted,
        "from": from_formatted,
        "status": call.status,
    }


def end_call(call_sid: str) -> Dict[str, Any]:
    client = get_client()
    if not client:
        raise RuntimeError("Twilio not configured")
    try:
        call = client.calls(call_sid).update(status="completed")
        if call_sid in active_calls:
            active_calls[call_sid]["status"] = "completed"
        return {"success": True, "call_sid": call_sid, "status": call.status}
    except Exception as exc:
        raise RuntimeError(f"Failed to end Twilio call {call_sid}: {exc}") from exc


def build_twiml(text: str, call_sid: str, base_url: str, wav_path: Optional[str] = None, is_greeting: bool = False, is_final: bool = False, voice_engine: str = None, reference_audio: Optional[str] = None) -> str:
    """
    Build TwiML XML that:
    1. Plays speech using Cloned Voice (F5-TTS, LuxTTS, Chatterbox Turbo) via <Play>,
       or native Amazon Polly Matthew via <Say> if selected.
    2. Gathers caller speech input and posts to /api/twilio/respond.
    3. Handles reprompt and graceful exit using the designated voice engine.
    """
    import time
    t0 = time.time()
    response = VoiceResponse()
    public_url = resolve_base_url(base_url)

    engine = (voice_engine or getattr(config, "TWILIO_VOICE_ENGINE", "f5tts")).lower()
    is_cloned_engine = not any(k in engine for k in ["polly", "say", "native"])
    polly_voice = "Polly.Joanna" if any(k in engine for k in ["joanna", "female", "woman"]) else "Polly.Matthew"
    chosen_wav = None

    # Check caller destination for speech recognition localization
    call_info = active_calls.get(call_sid, {})
    to_num = call_info.get("to_number", "")
    from_num = call_info.get("from_number", "")
    is_india = to_num.startswith("+91") or from_num.startswith("+91")

    # Language priority: explicit call-state language > phone region detection
    call_language = call_info.get("language", "")
    if call_language in ("kn-IN", "kn"):
        gather_lang = "kn-IN"
    elif call_language in ("hi-IN", "hi"):
        gather_lang = "hi-IN"
    elif call_language in ("ta-IN",):
        gather_lang = "ta-IN"
    elif call_language and call_language not in ("en-US", "en-IN", ""):
        gather_lang = call_language  # any other BCP-47 tag passed through
    elif is_india:
        gather_lang = "en-IN"
    else:
        gather_lang = "en-US"

    # 1. Voice playback resolution for cloned/neural TTS engines
    if is_cloned_engine:
        chosen_wav = wav_path
        # Priority 1: Check pre-generated audio for this call (covers both greeting and continued turns)
        if not chosen_wav:
            chosen_wav = pregenerated_audio.pop(call_sid, None)

        # Priority 2: For greeting (e.g. inbound), ONLY reuse prewarmed_greeting.wav if its text matches
        if not chosen_wav and is_greeting:
            prewarmed_file = os.path.join(config.TTS_OUTPUT_DIR, "prewarmed_greeting.wav")
            meta = get_prewarm_meta()
            if (
                os.path.exists(prewarmed_file)
                and os.path.getsize(prewarmed_file) > 1000
                and meta.get("text")
                and text
                and meta.get("text").strip() == text.strip()
            ):
                chosen_wav = prewarmed_file
                print(f"[Twilio TwiML] ✓ Using text-verified Pre-Warmed Cloned Voice greeting ({engine}) for {call_sid}")

        # Priority 3: Dynamic synthesis if text is provided and no audio ready yet
        if not chosen_wav and text:
            try:
                from backend import tts_engine as tts_mod
                ref_audio = reference_audio or call_info.get("reference_audio")
                print(f"[Twilio TwiML] Synthesizing cloned voice response ({engine}, ref={ref_audio or 'default'}) for: '{text[:50]}...'")
                chosen_wav = tts_mod.synthesize(text, reference_audio=ref_audio, engine=engine)
            except Exception as tts_err:
                print(f"[Twilio TwiML] Cloned voice dynamic synthesis error: {tts_err}")

        # Priority 4: Fallback to pre-warmed reprompt or greeting so Polly is NEVER played on cloned mode
        if not chosen_wav or not os.path.exists(chosen_wav):
            for backup_candidate in ["prewarmed_reprompt.wav", "prewarmed_greeting.wav"]:
                bp = os.path.join(config.TTS_OUTPUT_DIR, backup_candidate)
                if os.path.exists(bp) and os.path.getsize(bp) > 1000:
                    chosen_wav = bp
                    break

    # Final turn: Play goodbye / final message and hang up
    if is_final:
        if is_cloned_engine and chosen_wav and os.path.exists(chosen_wav):
            filename = os.path.basename(chosen_wav)
            response.play(f"{public_url}/tts_output/{filename}")
            print(f"[Twilio TwiML] ✓ Final Cloned Voice ({engine}) Playing ({filename})")
        elif text:
            response.say(text, voice=polly_voice, language=gather_lang)
        response.hangup()
        return str(response)

    # Conversational turn: Play synthesized voice cleanly, then Gather caller's speech
    gather_action = f"{public_url}/api/twilio/respond?call_sid={call_sid}"

    if is_cloned_engine and chosen_wav and os.path.exists(chosen_wav):
        filename = os.path.basename(chosen_wav)
        audio_url = f"{public_url}/tts_output/{filename}"
        response.play(audio_url)
        elapsed = time.time() - t0
        print(f"[Twilio TwiML] ✓ Cloned Voice ({engine}) Playing ({filename}) in {elapsed:.3f}s")
    elif text:
        response.say(text, voice=polly_voice, language=gather_lang)

    gather = Gather(
        input="speech",
        action=gather_action,
        method="POST",
        speech_timeout="auto",
        timeout=10,
        language=gather_lang,
        action_on_empty_result=True,
    )
    response.append(gather)

    return str(response)


