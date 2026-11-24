import sys, os, importlib.util
# Ensure working directory modules take precedence over any read-only dataset inputs
_CURR_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
_BACKEND_DIR = os.path.join(_CURR_DIR, "backend")
sys.path = [
    _CURR_DIR,
    _BACKEND_DIR,
    os.path.join(_CURR_DIR, "LuxTTS"),
    "/kaggle/working/LuxTTS",
    "/kaggle/working/vocaly",
    "/kaggle/working"
] + [
    p for p in sys.path if not p.startswith("/kaggle/input") and "/input/" not in p and p != ""
]

# Directly and explicitly load tts_engine into sys.modules to prevent any lookup in read-only /kaggle/input
import types
_tts_file = os.path.join(_BACKEND_DIR, "tts_engine.py")
if not os.path.exists(_tts_file):
    _tts_file = os.path.join(_CURR_DIR, "tts_engine.py")

if os.path.exists(_tts_file):
    try:
        with open(_tts_file, "r") as _f:
            _code = _f.read()
        _tts_mod = types.ModuleType("backend.tts_engine")
        _tts_mod.__file__ = _tts_file
        exec(_code, _tts_mod.__dict__)
        sys.modules["backend.tts_engine"] = _tts_mod
        sys.modules["tts_engine"] = _tts_mod
        print(f"[Startup] ✓ Directly loaded LuxTTS engine from {_tts_file} (synthesize: {hasattr(_tts_mod, 'synthesize')})")
    except Exception as _e:
        print(f"[Startup Error] Binding tts_engine: {_e}")

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import os, shutil, json, re
from datetime import datetime

from backend.database import get_db, init_db
from backend import models
try:
    from backend import config
except ImportError:
    import config
from backend.config import UPLOADED_DOCS_DIR, TTS_OUTPUT_DIR, REFERENCE_AUDIO_PATH
# Import engines lazily inside route handlers to avoid circular imports

app = FastAPI(title="Vocalyx API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    init_db()
    os.makedirs(UPLOADED_DOCS_DIR, exist_ok=True)
    os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)
    # Sync default studio voices into TTS_OUTPUT_DIR if missing (useful after fresh git clone)
    import glob as _glob
    for _dv_dir in [os.path.join(_CURR_DIR, "default_voices"), os.path.join(_BACKEND_DIR, "default_voices"), "default_voices"]:
        if os.path.isdir(_dv_dir):
            for _src_f in _glob.glob(os.path.join(_dv_dir, "*.wav")):
                _dst_f = os.path.join(TTS_OUTPUT_DIR, os.path.basename(_src_f))
                if not os.path.exists(_dst_f):
                    shutil.copy2(_src_f, _dst_f)
            break
    print("[Startup] Database and storage directories initialized. Server ready.")


# Ensure required directories exist before mounting static files
os.makedirs(UPLOADED_DOCS_DIR, exist_ok=True)
os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)
os.makedirs("frontend", exist_ok=True)

@app.get("/tts_output/{filename}")
async def serve_tts_audio_file(filename: str):
    """Serve synthesized WAV audio with telephony and ngrok-bypass headers."""
    filepath = os.path.join(TTS_OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(
        filepath,
        media_type="audio/wav",
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
            "ngrok-skip-browser-warning": "true",
        }
    )

# Mount frontend and TTS output static files
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")
app.mount("/tts_output", StaticFiles(directory=TTS_OUTPUT_DIR), name="tts_output")


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class ContactCreate(BaseModel):
    name: str
    phone_number: str
    notes: Optional[str] = None
    preferred_language: Optional[str] = "en-US"


class ScriptCreate(BaseModel):
    title: str
    content: str


class ChatRequest(BaseModel):
    message: str
    contact_id: Optional[int] = None
    tts_engine: Optional[str] = None
    voice_id: Optional[int] = None
    conversation_history: Optional[List[dict]] = None
    script_id: Optional[int] = None
    language: Optional[str] = "en-US"


class TTSRequest(BaseModel):
    text: str
    engine: Optional[str] = None
    voice_id: Optional[int] = None


class AnalyzeRequest(BaseModel):
    contact_id: Optional[int] = 0
    transcript: str  # Full conversation as a string


class TwilioConfigUpdate(BaseModel):
    account_sid: Optional[str] = None
    auth_token: Optional[str] = None
    phone_number: Optional[str] = None
    public_base_url: Optional[str] = None
    voice_engine: Optional[str] = None


class TwilioCallRequest(BaseModel):
    to_number: str
    contact_id: Optional[int] = None
    mode: Optional[str] = "outbound"
    public_url: Optional[str] = None
    voice_engine: Optional[str] = None
    language: Optional[str] = None


class TwilioHangupRequest(BaseModel):
    call_sid: str


class AlertsConfigUpdate(BaseModel):
    telegram: Optional[dict] = None
    sms: Optional[dict] = None
    whatsapp: Optional[dict] = None


class AlertTestRequest(BaseModel):
    channel: str
    to_phone: Optional[str] = None
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    from_phone: Optional[str] = None
    message: Optional[str] = None


class CreateVoiceRequest(BaseModel):
    name: str
    engine: str = "f5tts"
    audio_path: Optional[str] = None
    preview_url: Optional[str] = None
    activate_now: bool = False


# ---------------------------------------------------------------------------
# Root & Static Assets
# ---------------------------------------------------------------------------

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FRONTEND_DIR = os.path.join(_BASE_DIR, "frontend")
_INDEX_FILE = os.path.join(_FRONTEND_DIR, "index.html")

@app.get("/")
@app.get("/app")
@app.get("/dashboard")
async def serve_frontend():
    if os.path.exists(_INDEX_FILE):
        return FileResponse(_INDEX_FILE)
    return {"status": "Vocalyx API running", "docs": "/docs"}

@app.get("/style.css", include_in_schema=False)
async def serve_root_css():
    css_file = os.path.join(_FRONTEND_DIR, "style.css")
    if os.path.exists(css_file):
        return FileResponse(css_file, media_type="text/css")
    return Response(status_code=404)

@app.get("/script.js", include_in_schema=False)
async def serve_root_js():
    js_file = os.path.join(_FRONTEND_DIR, "script.js")
    if os.path.exists(js_file):
        return FileResponse(js_file, media_type="application/javascript")
    return Response(status_code=404)


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

@app.post("/api/contacts")
def create_contact(contact: ContactCreate, db: Session = Depends(get_db)):
    db_contact = models.Contact(
        name=contact.name,
        phone_number=contact.phone_number,
        notes=contact.notes,
        preferred_language=contact.preferred_language or "en-US",
    )
    db.add(db_contact)
    db.commit()
    db.refresh(db_contact)
    return {
        "id": db_contact.id,
        "name": db_contact.name,
        "phone_number": db_contact.phone_number,
        "notes": db_contact.notes,
        "last_topic": db_contact.last_topic,
        "interest_level": db_contact.interest_level,
        "concerns": db_contact.concerns,
        "commitments": db_contact.commitments,
        "last_contacted_at": db_contact.last_contacted_at,
        "preferred_language": getattr(db_contact, "preferred_language", "en-US") or "en-US",
    }


@app.get("/api/contacts")
def list_contacts(db: Session = Depends(get_db)):
    contacts = db.query(models.Contact).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "phone_number": c.phone_number,
            "notes": c.notes,
            "last_topic": c.last_topic,
            "interest_level": c.interest_level,
            "concerns": c.concerns,
            "commitments": c.commitments,
            "last_contacted_at": c.last_contacted_at,
            "preferred_language": getattr(c, "preferred_language", "en-US") or "en-US",
        }
        for c in contacts
    ]


@app.delete("/api/contacts/{contact_id}")
def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.delete(contact)
    db.commit()
    return {"message": "Contact deleted"}


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None
    notes: Optional[str] = None
    interest_level: Optional[str] = None
    last_topic: Optional[str] = None
    concerns: Optional[str] = None
    commitments: Optional[str] = None
    preferred_language: Optional[str] = None

@app.patch("/api/contacts/{contact_id}")
def update_contact(contact_id: int, update: ContactUpdate, db: Session = Depends(get_db)):
    contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    for field, val in update.dict(exclude_none=True).items():
        setattr(contact, field, val)
    db.commit()
    db.refresh(contact)
    return {
        "id": contact.id,
        "name": contact.name,
        "phone_number": contact.phone_number,
        "notes": contact.notes,
        "interest_level": contact.interest_level,
        "last_topic": contact.last_topic,
        "concerns": contact.concerns,
        "commitments": contact.commitments,
        "last_contacted_at": contact.last_contacted_at,
        "preferred_language": getattr(contact, "preferred_language", "en-US") or "en-US",
    }


# ---------------------------------------------------------------------------
# Scripts
# ---------------------------------------------------------------------------

@app.post("/api/scripts")
def create_script(script: ScriptCreate, db: Session = Depends(get_db)):
    db_script = models.Script(title=script.title, content=script.content)
    db.add(db_script)
    db.commit()
    db.refresh(db_script)
    return {"id": db_script.id, "title": db_script.title, "content": db_script.content}


@app.get("/api/scripts")
def list_scripts(db: Session = Depends(get_db)):
    scripts = db.query(models.Script).all()
    return [{"id": s.id, "title": s.title, "content": s.content} for s in scripts]


@app.delete("/api/scripts/{script_id}")
def delete_script(script_id: int, db: Session = Depends(get_db)):
    script = db.query(models.Script).filter(models.Script.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    db.delete(script)
    db.commit()
    return {"message": "Script deleted"}


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    filepath = os.path.join(UPLOADED_DOCS_DIR, file.filename)
    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)

    db_doc = models.Document(filename=file.filename, filepath=filepath)
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)

    try:
        from backend import rag_engine
        rag_engine.add_document(filepath)
    except Exception:
        pass  # Indexing failure is non-fatal

    return {"message": "Document uploaded and indexed", "filename": file.filename, "id": db_doc.id}


@app.get("/api/documents")
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(models.Document).all()
    return [{"id": d.id, "filename": d.filename, "uploaded_at": d.uploaded_at} for d in docs]


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if os.path.exists(doc.filepath):
        os.remove(doc.filepath)
    db.delete(doc)
    db.commit()
    return {"message": "Document deleted"}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@app.post("/api/chat")
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    contact_memory = {}
    previous_calls_data = []
    if request.contact_id is not None and request.contact_id > 0:
        contact = db.query(models.Contact).filter(models.Contact.id == request.contact_id).first()
        if contact:
            contact_memory = {
                "name": contact.name,
                "phone_number": contact.phone_number,
                "notes": contact.notes,
                "last_topic": contact.last_topic,
                "interest_level": contact.interest_level,
                "concerns": contact.concerns,
                "commitments": contact.commitments,
                "last_contacted_at": str(contact.last_contacted_at) if contact.last_contacted_at else None,
                "preferred_language": getattr(contact, "preferred_language", "en-US") or "en-US",
            }
            # Fetch past calls for cross-call context
            past_calls = db.query(models.Call).filter(models.Call.contact_id == contact.id).order_by(models.Call.created_at.desc()).limit(3).all()
            for pc in reversed(past_calls):
                previous_calls_data.append({
                    "date": pc.created_at.strftime("%b %d") if pc.created_at else None,
                    "summary": pc.summary,
                    "outcome": pc.outcome,
                })

    message = request.message

    rag_context = ""
    try:
        from backend import rag_engine
        rag_context = rag_engine.search(message)
    except Exception as rexc:
        print(f"[CHAT RAG NOTE]: {rexc}")

    from backend import llm_engine

    script_content = None
    if request.script_id:
        script = db.query(models.Script).filter(models.Script.id == request.script_id).first()
        if script:
            script_content = script.content

    target_lang = request.language or contact_memory.get("preferred_language") or "en-US"

    response_text = llm_engine.get_chat_response(
        user_message=message,
        rag_context=rag_context,
        contact_memory=contact_memory,
        conversation_history=request.conversation_history,
        previous_calls=previous_calls_data,
        script_content=script_content,
        language=target_lang,
    )

    # Determine active voice and reference audio
    voice_engine = request.tts_engine
    ref_audio = None
    if request.voice_id:
        selected_voice = db.query(models.Voice).filter(models.Voice.id == request.voice_id).first()
        if selected_voice:
            voice_engine = selected_voice.engine
            ref_audio = selected_voice.audio_path
    elif not voice_engine:
        active_voice = db.query(models.Voice).filter(models.Voice.is_active == True).first()
        if active_voice:
            voice_engine = active_voice.engine
            ref_audio = active_voice.audio_path

    # Auto-route to native studio edge-tts for non-English languages if standard English cloned engine is set
    if target_lang in ("kn-IN", "kn"):
        if "male" in (voice_engine or "").lower() and "female" not in (voice_engine or "").lower():
            voice_engine = "kannada_male"
        else:
            voice_engine = "kannada_female"
    elif target_lang in ("hi-IN", "hi"):
        if "male" in (voice_engine or "").lower() and "female" not in (voice_engine or "").lower():
            voice_engine = "hindi_male"
        else:
            voice_engine = "hindi_female"

    audio_url = None
    tts_error = None
    try:
        from backend import tts_engine
        wav_path = tts_engine.synthesize(response_text, reference_audio=ref_audio, engine=voice_engine)
        audio_filename = os.path.basename(wav_path)
        audio_url = f"/tts_output/{audio_filename}"
    except Exception as exc:
        tts_error = str(exc)
        print(f"[CHAT TTS ERROR] Failed to synthesize response: {exc}")

    return {"text": response_text, "audio_url": audio_url, "tts_error": tts_error}


@app.post("/api/tts")
async def synthesize_text(request: TTSRequest, db: Session = Depends(get_db)):
    try:
        from backend import tts_engine
        engine = request.engine
        ref_audio = None
        if request.voice_id:
            voice = db.query(models.Voice).filter(models.Voice.id == request.voice_id).first()
            if voice:
                engine = voice.engine
                ref_audio = voice.audio_path
        elif not engine:
            active_voice = db.query(models.Voice).filter(models.Voice.is_active == True).first()
            if active_voice:
                engine = active_voice.engine
                ref_audio = active_voice.audio_path

        wav_path = tts_engine.synthesize(request.text, reference_audio=ref_audio, engine=engine)
        audio_filename = os.path.basename(wav_path)
        return {"audio_url": f"/tts_output/{audio_filename}"}
    except Exception as exc:
        print(f"[TTS ERROR] /api/tts synthesis failed: {exc}")
        raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {exc}")


@app.get("/api/tts/prewarm-status")
def get_tts_prewarm_status():
    """Check if the cloned voice engine is pre-warmed and ready on GPU."""
    from backend import tts_engine, config
    prewarmed_file = os.path.join(config.TTS_OUTPUT_DIR, "prewarmed_greeting.wav")
    is_ready = os.path.exists(prewarmed_file) and os.path.getsize(prewarmed_file) > 1000
    voice_status = get_voice_status()
    return {
        "ready": is_ready,
        "greeting_url": "/tts_output/prewarmed_greeting.wav" if is_ready else None,
        "model_loaded": getattr(tts_engine, "tts_model", None) is not None,
        "device": str(getattr(tts_engine, "_device", "none")),
        "has_voice_clone": voice_status["has_voice_clone"],
    }


class TTSPrewarmRequest(BaseModel):
    engine: Optional[str] = None

@app.post("/api/tts/prewarm")
async def post_tts_prewarm(request: Request):
    """
    Pre-warms the voice cloning engine:
    1. Loads the selected TTS weights into GPU memory.
    2. Computes and caches reference audio voice conditioning.
    3. Synthesizes and writes prewarmed_greeting.wav to disk.
    Ensures subsequent Twilio calls connect with 0.0s latency.
    """
    import time
    t0 = time.time()
    from backend import tts_engine, config
    voice_status = get_voice_status()
    req_engine = request.query_params.get("engine")
    if not req_engine:
        try:
            body = await request.json()
            if isinstance(body, dict):
                req_engine = body.get("engine")
        except Exception:
            pass

    active_engine = (req_engine or getattr(config, "TWILIO_VOICE_ENGINE", "f5tts")).lower()

    indic_studio_profiles = {
        "kannada_female": ("sapna_greeting.wav", "kn-IN-SapnaNeural", "ನಮಸ್ಕಾರ, ವೋಕಲಿಕ್ಸ್‌ಗೆ ಸ್ವಾಗತ! ನನ್ನ ಹೆಸರು ಸ್ವಪ್ನಾ.", "Sapna (Kannada Female Studio)"),
        "kannada_male": ("gagan_greeting.wav", "kn-IN-GaganNeural", "ನಮಸ್ಕಾರ, ವೋಕಲಿಕ್ಸ್‌ಗೆ ಸ್ವಾಗತ! ನನ್ನ ಹೆಸರು ಗಗನ್.", "Gagan (Kannada Male Studio)"),
        "hindi_female": ("swara_greeting.wav", "hi-IN-SwaraNeural", "नमस्ते, वोकलिक्स में आपका स्वागत है! मेरा नाम स्वरा है।", "Swara (Hindi Female Studio)"),
        "hindi_male": ("madhur_greeting.wav", "hi-IN-MadhurNeural", "नमस्ते, वोकलिक्स में आपका स्वागत है! मेरा नाम मधुर है।", "Madhur (Hindi Male Studio)"),
    }
    if active_engine in indic_studio_profiles:
        fname, _voice_id, sample_text, label = indic_studio_profiles[active_engine]
        studio_path = os.path.join(TTS_OUTPUT_DIR, fname)
        if not os.path.exists(studio_path):
            fallback_src = os.path.join("default_voices", fname)
            if os.path.exists(fallback_src):
                shutil.copy2(fallback_src, studio_path)
            else:
                gen_path = tts_engine.synthesize(sample_text, engine=active_engine)
                if gen_path and os.path.exists(gen_path):
                    shutil.copy2(gen_path, studio_path)
        if os.path.exists(studio_path):
            shutil.copy2(studio_path, os.path.join(TTS_OUTPUT_DIR, "prewarmed_greeting.wav"))
        return {
            "success": True,
            "ready": True,
            "greeting_url": f"/tts_output/{fname}",
            "elapsed_seconds": 0.1,
            "message": f"{label} voice profile is ready with 0.0s latency.",
        }

    if "joanna" in active_engine or active_engine == "polly_female":
        joanna_path = os.path.join(TTS_OUTPUT_DIR, "joanna_greeting.wav")
        if not os.path.exists(joanna_path):
            tts_engine.synthesize("Hello, thank you for calling Vocalyx! My name is Joanna. How may I assist you today?", engine="polly_joanna")
        shutil.copy2(joanna_path if os.path.exists(joanna_path) else os.path.join("default_voices", "joanna_greeting.wav"), os.path.join(TTS_OUTPUT_DIR, "prewarmed_greeting.wav"))
        return {
            "success": True,
            "ready": True,
            "greeting_url": "/tts_output/joanna_greeting.wav",
            "elapsed_seconds": 0.1,
            "message": "Joanna (Natural US Female) voice profile is ready with 0.0s latency.",
        }

    if any(k in active_engine for k in ["matthew", "polly_matthew"]) or active_engine == "polly":
        matthew_path = os.path.join(TTS_OUTPUT_DIR, "matthew_greeting.wav")
        if not os.path.exists(matthew_path):
            tts_engine.synthesize("Hello there, thank you for calling Vocalyx. This is Matthew speaking. How can I help you today?", engine="polly_matthew")
        shutil.copy2(matthew_path if os.path.exists(matthew_path) else os.path.join("default_voices", "matthew_greeting.wav"), os.path.join(TTS_OUTPUT_DIR, "prewarmed_greeting.wav"))
        return {
            "success": True,
            "ready": True,
            "greeting_url": "/tts_output/matthew_greeting.wav",
            "elapsed_seconds": 0.1,
            "message": "Matthew (Natural US Male) voice profile is ready with 0.0s latency.",
        }

    try:
        greeting_text = "Hello there! This is Alex calling from Vocalyx. How are you doing today?"
        wav_path = tts_engine.prewarm_engine(greeting_text, engine=active_engine)
        elapsed = time.time() - t0
        return {
            "success": True,
            "ready": True,
            "greeting_url": "/tts_output/prewarmed_greeting.wav",
            "elapsed_seconds": round(elapsed, 2),
            "message": f"Cloned voice ({active_engine}) pre-warmed in {elapsed:.1f}s. Audio is ready on server.",
        }
    except Exception as exc:
        print(f"[TTS ERROR] /api/tts/prewarm failed: {exc}")
        raise HTTPException(status_code=500, detail=f"TTS pre-warm failed: {exc}")



# ---------------------------------------------------------------------------
# Voice Helper & Voice Cloning
# ---------------------------------------------------------------------------

def get_voice_status():
    candidates = [
        REFERENCE_AUDIO_PATH,
        "voice_clone.mp3",
        os.path.join(os.path.dirname(__file__), "..", "voice_clone.mp3"),
        os.path.join(os.path.dirname(__file__), "voice_clone.mp3"),
        "/kaggle/working/vocaly/voice_clone.mp3",
        "/kaggle/working/vocaly/backend/voice_clone.mp3",
        "/kaggle/working/voice_clone.mp3",
        "/content/vocalyx/voice_clone.mp3",
    ]
    found_path = None
    for c in candidates:
        if c and os.path.exists(c) and os.path.getsize(c) > 0:
            found_path = os.path.abspath(c)
            break
    if found_path:
        return {
            "has_voice_clone": True,
            "filename": os.path.basename(found_path),
            "size_kb": round(os.path.getsize(found_path) / 1024, 1),
            "path": found_path,
        }
    return {
        "has_voice_clone": False,
        "filename": None,
        "size_kb": 0,
        "path": None,
    }


@app.get("/api/voice/status")
def api_voice_status():
    return get_voice_status()


@app.post("/api/voice/test")
def api_voice_test(exaggeration: float = 0.5, cfg_weight: float = 0.0):
    voice_info = get_voice_status()
    if not voice_info["has_voice_clone"]:
        raise HTTPException(status_code=400, detail="No voice clone file found on server. Upload one in Voice Studio.")
    try:
        from backend import tts_engine
        wav_path = tts_engine.synthesize(
            "Hello! This is a test of your cloned voice. Vocalyx voice synthesis is working perfectly!",
            reference_audio=voice_info["path"],
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
        )
        audio_filename = os.path.basename(wav_path)
        return {
            "message": "Voice test synthesized successfully",
            "test_audio_url": f"/tts_output/{audio_filename}",
            "voice_info": voice_info,
        }
    except Exception as exc:
        print(f"[API ERROR] Voice test failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Voice test synthesis failed: {exc}")


@app.post("/api/clone-voice")
async def clone_voice(
    audio: UploadFile = File(...),
    exaggeration: float = Form(0.5),
    cfg_weight: float = Form(0.0),
):
    save_path = "voice_clone.mp3"
    with open(save_path, "wb") as f:
        shutil.copyfileobj(audio.file, f)

    if os.path.abspath(REFERENCE_AUDIO_PATH) != os.path.abspath(save_path):
        try:
            shutil.copyfile(save_path, REFERENCE_AUDIO_PATH)
        except Exception:
            pass

    voice_info = get_voice_status()

    try:
        from backend import tts_engine
        wav_path = tts_engine.synthesize(
            "Hello! This is a test of your cloned voice. It sounds great!",
            reference_audio=save_path,
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
        )
        audio_filename = os.path.basename(wav_path)
        return {
            "message": "Voice cloned successfully",
            "test_audio_url": f"/tts_output/{audio_filename}",
            "voice_info": voice_info,
        }
    except Exception as exc:
        print(f"[API ERROR] Voice cloning failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Voice cloning failed: {exc}")


# ---------------------------------------------------------------------------
# Voices Management (Multi-Voice Library)
# ---------------------------------------------------------------------------

def seed_default_voices_if_needed(db: Session):
    defaults = [
        models.Voice(
            name="Alex (Default F5-TTS Flow-Matching)",
            engine="f5tts",
            voice_type="cloned",
            audio_path="voice_clone.mp3",
            preview_url="/tts_output/prewarmed_greeting.wav",
            is_active=True,
        ),
        models.Voice(
            name="Joanna (Natural US Female)",
            engine="polly_joanna",
            voice_type="native",
            audio_path="default_voices/female_reference.wav",
            preview_url="/tts_output/joanna_greeting.wav",
            is_active=False,
        ),
        models.Voice(
            name="Matthew (Natural US Male)",
            engine="polly_matthew",
            voice_type="native",
            audio_path=None,
            preview_url="/tts_output/matthew_greeting.wav",
            is_active=False,
        ),
        models.Voice(
            name="Sapna (Kannada Female Studio)",
            engine="kannada_female",
            voice_type="native",
            audio_path=None,
            preview_url="/tts_output/sapna_greeting.wav",
            is_active=False,
        ),
        models.Voice(
            name="Gagan (Kannada Male Studio)",
            engine="kannada_male",
            voice_type="native",
            audio_path=None,
            preview_url="/tts_output/gagan_greeting.wav",
            is_active=False,
        ),
        models.Voice(
            name="Swara (Hindi Female Studio)",
            engine="hindi_female",
            voice_type="native",
            audio_path=None,
            preview_url="/tts_output/swara_greeting.wav",
            is_active=False,
        ),
        models.Voice(
            name="Madhur (Hindi Male Studio)",
            engine="hindi_male",
            voice_type="native",
            audio_path=None,
            preview_url="/tts_output/madhur_greeting.wav",
            is_active=False,
        ),
        models.Voice(
            name="Alex (LuxTTS Ultra-Fast 150x)",
            engine="luxtts",
            voice_type="cloned",
            audio_path="voice_clone.mp3",
            preview_url="/tts_output/prewarmed_greeting.wav",
            is_active=False,
        ),
    ]
    existing = db.query(models.Voice).all()
    if not existing:
        db.add_all(defaults)
        db.commit()
    else:
        existing_engines = {v.engine: v for v in existing}
        for d in defaults:
            if d.engine not in existing_engines:
                db.add(models.Voice(
                    name=d.name,
                    engine=d.engine,
                    voice_type=d.voice_type,
                    audio_path=d.audio_path,
                    preview_url=d.preview_url,
                    is_active=False,
                ))
            else:
                v = existing_engines[d.engine]
                if not v.name or "kannada" in d.engine or "hindi" in d.engine:
                    v.name = d.name
                    v.voice_type = d.voice_type
        # Ensure Joanna and Matthew have audio references (match by specific name, NOT generic "female")
        for v in existing:
            if "joanna" in v.name.lower() or "natural us female" in v.name.lower():
                v.engine = "polly_joanna"
                v.preview_url = "/tts_output/joanna_greeting.wav"
                v.audio_path = "default_voices/female_reference.wav"
            elif "matthew" in v.name.lower() or "natural us male" in v.name.lower():
                v.engine = "polly_matthew"
                v.preview_url = "/tts_output/matthew_greeting.wav"
        # Purge any legacy chatterbox entries from voices table
        db.query(models.Voice).filter(models.Voice.engine == "chatterbox").delete()
        db.commit()


@app.get("/api/voices")
def list_voices(db: Session = Depends(get_db)):
    seed_default_voices_if_needed(db)
    voices = db.query(models.Voice).order_by(models.Voice.id.asc()).all()
    return [
        {
            "id": v.id,
            "name": v.name,
            "engine": v.engine,
            "voice_type": v.voice_type,
            "audio_path": v.audio_path,
            "preview_url": v.preview_url,
            "is_active": v.is_active,
            "created_at": str(v.created_at) if v.created_at else None,
        }
        for v in voices
    ]


@app.post("/api/voices/compute")
async def compute_voice(
    audio: UploadFile = File(...),
    name: str = Form(...),
    engine: str = Form("f5tts"),
    test_text: Optional[str] = Form(None),
):
    import uuid, time
    from backend import tts_engine
    voices_dir = os.path.join(os.path.dirname(__file__), "uploaded_voices")
    os.makedirs(voices_dir, exist_ok=True)
    os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)

    safe_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', audio.filename or "sample.wav")
    unique_name = f"{int(time.time())}_{uuid.uuid4().hex[:6]}_{safe_name}"
    saved_path = os.path.abspath(os.path.join(voices_dir, unique_name))

    with open(saved_path, "wb") as f:
        shutil.copyfileobj(audio.file, f)

    # Trim audio to 30 seconds max and normalize to 48kHz mono PCM WAV (works for mp3/ogg/m4a/wav uploads)
    try:
        import subprocess as _sp
        trimmed_path = saved_path.rsplit(".", 1)[0] + "_30s.wav"
        trim_res = _sp.run(
            ["ffmpeg", "-y", "-i", saved_path, "-t", "30", "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", trimmed_path],
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, timeout=30
        )
        if trim_res.returncode == 0 and os.path.exists(trimmed_path) and os.path.getsize(trimmed_path) > 1000:
            try:
                os.remove(saved_path)
            except Exception:
                pass
            saved_path = trimmed_path
            print(f"[Voices] ✂️ Audio trimmed & converted to 48kHz mono WAV (max 30s): {saved_path}")
    except Exception as _trim_err:
        print(f"[Voices] Trim note: {_trim_err}")

    prompt_text = test_text or f"Hello, this is {name} from Vocalyx. My custom voice clone is computed and ready to speak!"

    # If legacy chatterbox engine is requested, default to luxtts
    if engine.lower() in ("chatterbox", "turbo"):
        engine = "luxtts"

    try:
        t0 = time.time()
        print(f"[Voices] ⚡ Computing voice clone for '{name}' using {engine}...")
        wav_path = tts_engine.synthesize(prompt_text, reference_audio=saved_path, engine=engine)
        if not wav_path or not os.path.exists(wav_path) or os.path.getsize(wav_path) <= 44:
            raise RuntimeError("Synthesized preview audio file was missing or empty.")
        elapsed = time.time() - t0
        filename = os.path.basename(wav_path)
        preview_url = f"/tts_output/{filename}"

        return {
            "success": True,
            "name": name,
            "engine": engine,
            "audio_path": saved_path,
            "preview_url": preview_url,
            "computation_time_seconds": round(elapsed, 2),
            "message": f"Voice computed successfully in {elapsed:.2f}s! Preview audio is ready to save.",
        }
    except Exception as exc:
        print(f"[Voices ERROR] Computation failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Voice computation failed: {exc}")


@app.post("/api/voices")
async def create_voice(request: CreateVoiceRequest, db: Session = Depends(get_db)):
    new_voice = models.Voice(
        name=request.name.strip(),
        engine=request.engine.lower(),
        voice_type="cloned" if request.audio_path else "native",
        audio_path=request.audio_path,
        preview_url=request.preview_url,
        is_active=request.activate_now,
    )
    if request.activate_now:
        db.query(models.Voice).update({models.Voice.is_active: False})
        config.TWILIO_VOICE_ENGINE = new_voice.engine
        if new_voice.audio_path and os.path.exists(new_voice.audio_path):
            config.REFERENCE_AUDIO_PATH = new_voice.audio_path
            try:
                shutil.copyfile(new_voice.audio_path, "voice_clone.mp3")
            except Exception:
                pass
        try:
            from backend import tts_engine
            tts_engine._cached_lux_prompt = None
            tts_engine._cached_chatterbox_ref = None
            for cf in ["voice_clone_lux_conds.pt", "voice_clone_conds.pt", "prewarmed_greeting.wav", "prewarmed_reprompt.wav", "prewarmed_goodbye.wav"]:
                fp = os.path.join(TTS_OUTPUT_DIR, cf)
                if os.path.exists(fp):
                    try: os.remove(fp)
                    except Exception: pass
            tts_engine.prewarm_engine(engine=new_voice.engine)
        except Exception as p_err:
            print(f"[Prewarm Error]: {p_err}")

    db.add(new_voice)
    db.commit()
    db.refresh(new_voice)
    return {
        "id": new_voice.id,
        "name": new_voice.name,
        "engine": new_voice.engine,
        "voice_type": new_voice.voice_type,
        "audio_path": new_voice.audio_path,
        "preview_url": new_voice.preview_url,
        "is_active": new_voice.is_active,
    }


@app.post("/api/voices/{voice_id}/activate")
async def activate_voice(voice_id: int, db: Session = Depends(get_db)):
    voice = db.query(models.Voice).filter(models.Voice.id == voice_id).first()
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found")

    db.query(models.Voice).update({models.Voice.is_active: False})
    voice.is_active = True
    db.commit()

    config.TWILIO_VOICE_ENGINE = voice.engine
    if voice.audio_path and os.path.exists(voice.audio_path):
        config.REFERENCE_AUDIO_PATH = voice.audio_path
        try:
            shutil.copyfile(voice.audio_path, "voice_clone.mp3")
        except Exception:
            pass

    try:
        from backend import tts_engine
        tts_engine._cached_lux_prompt = None
        tts_engine._cached_chatterbox_ref = None
        for cf in ["voice_clone_lux_conds.pt", "voice_clone_conds.pt", "prewarmed_greeting.wav", "prewarmed_reprompt.wav", "prewarmed_goodbye.wav"]:
            fp = os.path.join(TTS_OUTPUT_DIR, cf)
            if os.path.exists(fp):
                try: os.remove(fp)
                except Exception: pass
        tts_engine.prewarm_engine(engine=voice.engine)
    except Exception as p_err:
        print(f"[Voice Activation Prewarm Note]: {p_err}")

    return {"success": True, "active_voice": {
        "id": voice.id,
        "name": voice.name,
        "engine": voice.engine,
        "voice_type": voice.voice_type,
        "is_active": True,
    }}


@app.delete("/api/voices/{voice_id}")
def delete_voice(voice_id: int, db: Session = Depends(get_db)):
    voice = db.query(models.Voice).filter(models.Voice.id == voice_id).first()
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found")
    if voice.id in [1, 2, 3]:
        raise HTTPException(status_code=400, detail="Cannot delete system default voices")

    if voice.is_active:
        v1 = db.query(models.Voice).filter(models.Voice.id == 1).first()
        if v1:
            v1.is_active = True
            config.TWILIO_VOICE_ENGINE = v1.engine

    db.delete(voice)
    db.commit()
    return {"success": True, "deleted_id": voice_id}


# ---------------------------------------------------------------------------
# Calls – Analyze
# ---------------------------------------------------------------------------

@app.post("/api/calls/analyze")
async def analyze_call(request: AnalyzeRequest, db: Session = Depends(get_db)):
    contact = None
    if request.contact_id and request.contact_id > 0:
        contact = db.query(models.Contact).filter(models.Contact.id == request.contact_id).first()

    if not contact:
        contact = db.query(models.Contact).filter(models.Contact.name == "Simulator Guest").first()
        if not contact:
            first_c = db.query(models.Contact).first()
            if first_c and (not request.contact_id or request.contact_id <= 0):
                contact = first_c
            else:
                contact = models.Contact(
                    name="Simulator Guest",
                    phone_number="+10000000000",
                    notes="Browser Simulator Test User",
                    interest_level="Unknown",
                )
                db.add(contact)
                db.commit()
                db.refresh(contact)

    transcript = (request.transcript or "").strip()
    if not transcript:
        transcript = f"Agent: Hello, this is Alex from Vocalyx. Caller connected with {contact.name}."

    from backend import llm_engine
    analysis = llm_engine.analyze_call(transcript, contact.name)

    # Update contact record with analysis results
    contact.last_topic = analysis.get("last_topic")
    contact.interest_level = analysis.get("interest_level", "Unknown")
    contact.concerns = analysis.get("concerns")
    contact.commitments = analysis.get("commitments")
    contact.last_contacted_at = datetime.utcnow()

    # Create Call record
    db_call = models.Call(
        contact_id=contact.id,
        transcript=transcript,
        summary=analysis.get("summary"),
        sentiment=analysis.get("sentiment"),
        outcome=analysis.get("outcome"),
        lead_score=analysis.get("lead_score"),
        lead_score_reasoning=analysis.get("lead_score_reasoning"),
    )
    db.add(db_call)
    db.commit()
    db.refresh(db_call)

    alerts_result = {}
    telegram_sent = False
    whatsapp_sent = False
    sms_sent = False
    try:
        from backend import telegram_alert
        alerts_result = telegram_alert.send_all_alerts_detailed(
            contact_name=contact.name,
            lead_score=analysis.get("lead_score", 0),
            sentiment=analysis.get("sentiment", "Neutral"),
            outcome=analysis.get("outcome", "Needs Follow-up"),
            summary=analysis.get("summary", ""),
            reasoning=analysis.get("lead_score_reasoning", ""),
        )
        telegram_sent = alerts_result.get("telegram", {}).get("ok", False)
        whatsapp_sent = alerts_result.get("whatsapp", {}).get("ok", False)
        sms_sent = alerts_result.get("sms", {}).get("ok", False)
    except Exception as t_err:
        print(f"[Analyze Alerts Error]: {t_err}")

    return {
        **analysis,
        "call_id": db_call.id,
        "telegram_sent": telegram_sent,
        "whatsapp_sent": whatsapp_sent,
        "sms_sent": sms_sent,
        "alerts_result": alerts_result,
    }


# ---------------------------------------------------------------------------
# Calls – List & Detail
# ---------------------------------------------------------------------------

@app.get("/api/calls")
def list_calls(
    contact_id: Optional[int] = None,
    outcome: Optional[str] = None,
    min_score: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db)
):
    from datetime import datetime as dt
    q = db.query(models.Call)
    if contact_id:
        q = q.filter(models.Call.contact_id == contact_id)
    if outcome:
        q = q.filter(models.Call.outcome == outcome)
    if min_score is not None:
        q = q.filter(models.Call.lead_score >= min_score)
    if date_from:
        try:
            q = q.filter(models.Call.created_at >= dt.strptime(date_from, "%Y-%m-%d"))
        except Exception:
            pass
    if date_to:
        try:
            q = q.filter(models.Call.created_at <= dt.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59))
        except Exception:
            pass
    calls = q.order_by(models.Call.created_at.desc()).all()
    result = []
    for call in calls:
        result.append({
            "id": call.id,
            "contact_id": call.contact_id,
            "contact_name": call.contact.name if call.contact else None,
            "transcript": call.transcript,
            "summary": call.summary,
            "sentiment": call.sentiment,
            "outcome": call.outcome,
            "lead_score": call.lead_score,
            "lead_score_reasoning": call.lead_score_reasoning,
            "created_at": call.created_at,
        })
    return result


@app.get("/api/calls/export")
def export_calls_csv(
    contact_id: Optional[int] = None,
    outcome: Optional[str] = None,
    min_score: Optional[int] = None,
    db: Session = Depends(get_db)
):
    import csv, io
    from fastapi.responses import StreamingResponse
    q = db.query(models.Call)
    if contact_id:
        q = q.filter(models.Call.contact_id == contact_id)
    if outcome:
        q = q.filter(models.Call.outcome == outcome)
    if min_score is not None:
        q = q.filter(models.Call.lead_score >= min_score)
    calls = q.order_by(models.Call.created_at.desc()).all()

    contacts = {c.id: c.name for c in db.query(models.Contact).all()}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Contact", "Lead Score", "Sentiment", "Outcome", "Summary", "Transcript"])
    for c in calls:
        writer.writerow([
            str(c.created_at)[:19] if c.created_at else "",
            contacts.get(c.contact_id, f"#{c.contact_id}"),
            c.lead_score or 0,
            c.sentiment or "",
            c.outcome or "",
            (c.summary or "").replace("\n", " "),
            (c.transcript or "").replace("\n", " | "),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=vocalyx_calls.csv"}
    )


@app.get("/api/calls/{call_id}")
def get_call(call_id: int, db: Session = Depends(get_db)):
    call = db.query(models.Call).filter(models.Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    return {
        "id": call.id,
        "contact_id": call.contact_id,
        "contact_name": call.contact.name if call.contact else None,
        "transcript": call.transcript,
        "summary": call.summary,
        "sentiment": call.sentiment,
        "outcome": call.outcome,
        "lead_score": call.lead_score,
        "lead_score_reasoning": call.lead_score_reasoning,
        "created_at": call.created_at,
    }


@app.get("/api/dashboard/stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    from sqlalchemy import func
    calls = db.query(models.Call).all()
    contacts = db.query(models.Contact).all()
    total_calls = len(calls)
    total_contacts = len(contacts)
    hot_leads = sum(1 for c in calls if (c.lead_score or 0) >= 70)
    avg_score = round(sum(c.lead_score or 0 for c in calls) / total_calls, 1) if total_calls else 0
    # Outcome breakdown
    outcome_counts = {}
    for c in calls:
        k = c.outcome or "Unknown"
        outcome_counts[k] = outcome_counts.get(k, 0) + 1
    # Sentiment breakdown
    sentiment_counts = {}
    for c in calls:
        k = c.sentiment or "Unknown"
        sentiment_counts[k] = sentiment_counts.get(k, 0) + 1
    # Recent hot leads
    hot = sorted([c for c in calls if (c.lead_score or 0) >= 70], key=lambda x: x.created_at or "", reverse=True)[:5]
    contact_map = {c.id: c.name for c in contacts}
    def call_dict(c):
        return {"id": c.id, "contact_id": c.contact_id, "contact_name": contact_map.get(c.contact_id, f"#{c.contact_id}"), "lead_score": c.lead_score, "sentiment": c.sentiment, "outcome": c.outcome, "summary": c.summary, "created_at": str(c.created_at) if c.created_at else None}
    recent = sorted(calls, key=lambda x: x.created_at or "", reverse=True)[:5]
    return {
        "total_calls": total_calls,
        "total_contacts": total_contacts,
        "hot_leads": hot_leads,
        "avg_lead_score": avg_score,
        "outcome_breakdown": outcome_counts,
        "sentiment_breakdown": sentiment_counts,
        "recent_hot_leads": [call_dict(c) for c in hot],
        "recent_calls": [call_dict(c) for c in recent],
    }


# ---------------------------------------------------------------------------
# Twilio Telephony Endpoints
# ---------------------------------------------------------------------------

def get_request_base_url(request: Request = None) -> str:
    from backend import config
    if config.PUBLIC_BASE_URL and not any(h in config.PUBLIC_BASE_URL for h in ["0.0.0.0", "127.0.0.1", "localhost"]):
        return config.PUBLIC_BASE_URL.rstrip("/")
    space_host = os.getenv("SPACE_HOST")
    if space_host and not any(h in space_host for h in ["0.0.0.0", "127.0.0.1", "localhost"]):
        return f"https://{space_host}".rstrip("/")
    space_id = os.getenv("SPACE_ID")
    if space_id:
        slug = space_id.replace("/", "-")
        return f"https://{slug}.hf.space".rstrip("/")
    if request:
        proto = request.headers.get("x-forwarded-proto", "https")
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        if host and not any(h in host for h in ["0.0.0.0", "127.0.0.1", "localhost"]):
            return f"{proto}://{host}".rstrip("/")
    return "https://ebedsouza-vocalyx.hf.space"


@app.get("/api/twilio/config")
def get_twilio_config(request: Request):
    from backend import twilio_service
    cfg = twilio_service.get_config()
    is_conf = twilio_service.is_configured()
    account_sid = cfg["account_sid"]
    masked_sid = f"{account_sid[:6]}...{account_sid[-4:]}" if len(account_sid) > 10 else (account_sid or "")
    base_url = get_request_base_url(request)
    return {
        "configured": is_conf,
        "account_sid": masked_sid,
        "phone_number": cfg["phone_number"],
        "public_base_url": cfg["public_base_url"] or base_url,
        "webhook_url": f"{base_url}/api/twilio/voice",
        "voice_engine": cfg.get("voice_engine", "cloned"),
    }


@app.post("/api/twilio/config")
def update_twilio_config(req: TwilioConfigUpdate, request: Request):
    from backend import twilio_service
    base_url = req.public_base_url or get_request_base_url(request)
    twilio_service.update_config(
        account_sid=req.account_sid,
        auth_token=req.auth_token,
        phone_number=req.phone_number,
        public_url=base_url,
        voice_engine=req.voice_engine,
    )
    test_result = twilio_service.verify_credentials()
    return {
        "success": True,
        "verification": test_result,
        "webhook_url": f"{base_url}/api/twilio/voice",
        "voice_engine": req.voice_engine or "cloned",
    }


@app.post("/api/twilio/test")
def test_twilio():
    from backend import twilio_service
    return twilio_service.verify_credentials()


# ---------------------------------------------------------------------------
# Message Alerts (SMS, WhatsApp, Telegram)
# ---------------------------------------------------------------------------

@app.get("/api/alerts/config")
def get_alerts_configuration():
    from backend import alerts_service
    return alerts_service.get_config()


@app.post("/api/alerts/config")
def update_alerts_configuration(update: AlertsConfigUpdate):
    from backend import alerts_service
    return alerts_service.update_config(update.dict(exclude_none=True))


@app.post("/api/alerts/test")
def test_alert_channel(req: AlertTestRequest):
    from backend import alerts_service
    test_msg = req.message or alerts_service.format_alert_message(
        contact_name="Alex Smith (Test)",
        lead_score=92,
        sentiment="Positive",
        outcome="Interested",
        summary="Test verification alert from Vocalyx Message Alerts console. Multi-channel messaging operational.",
        reasoning="Demo caller validated voice clarity and multi-channel message alerts.",
        markdown=(req.channel.lower().strip() != "sms"),
    )
    ch = req.channel.lower().strip()
    if ch == "telegram":
        ok, res = alerts_service.send_telegram(test_msg, bot_token=req.bot_token, chat_id=req.chat_id)
    elif ch == "sms":
        ok, res = alerts_service.send_sms(test_msg, to_phone=req.to_phone)
    elif ch == "whatsapp":
        ok, res = alerts_service.send_whatsapp(test_msg, to_phone=req.to_phone, from_phone=req.from_phone)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported alert channel '{req.channel}'")

    return {"ok": ok, "channel": ch, "result": res}


@app.post("/api/twilio/call")
def initiate_phone_call(call_req: TwilioCallRequest, request: Request, db: Session = Depends(get_db)):
    from backend import twilio_service, config
    base_url = call_req.public_url or get_request_base_url(request)
    if base_url and not any(h in base_url for h in ["0.0.0.0", "127.0.0.1", "localhost"]):
        config.PUBLIC_BASE_URL = base_url.rstrip("/")
        twilio_service._persist_config()
    if call_req.voice_engine:
        config.TWILIO_VOICE_ENGINE = call_req.voice_engine.strip().lower()
        os.environ["TWILIO_VOICE_ENGINE"] = config.TWILIO_VOICE_ENGINE
        twilio_service._persist_config()

    call_lang = call_req.language
    if not call_lang and call_req.contact_id:
        try:
            c = db.query(models.Contact).filter(models.Contact.id == call_req.contact_id).first()
            if c and c.preferred_language:
                call_lang = c.preferred_language
        except Exception:
            pass

    try:
        res = twilio_service.make_outbound_call(
            to_number=call_req.to_number,
            contact_id=call_req.contact_id,
            mode=call_req.mode or "outbound",
            base_url=base_url,
            voice_engine=call_req.voice_engine,
            language=call_lang,
        )
        return res
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/twilio/hangup")
def hangup_phone_call(hangup_req: TwilioHangupRequest):
    from backend import twilio_service
    try:
        return twilio_service.end_call(hangup_req.call_sid)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/twilio/active-call")
def get_active_twilio_call(call_sid: Optional[str] = None, db: Session = Depends(get_db)):
    from backend import twilio_service, llm_engine, models, telegram_alert
    call_data = None
    if call_sid and call_sid in twilio_service.active_calls:
        call_data = twilio_service.active_calls[call_sid]
    elif twilio_service.active_calls:
        call_data = list(twilio_service.active_calls.values())[-1]

    if not call_data:
        return {"active": False}

    # Query live status directly from Twilio API (trial-compatible, no webhooks needed)
    sid = call_data.get("call_sid")
    if sid:
        try:
            client = twilio_service.get_client()
            if client:
                live_call = client.calls(sid).fetch()
                call_data["status"] = live_call.status
                if live_call.duration:
                    call_data["duration"] = int(live_call.duration)

                # If call completed and not yet analyzed, finalize it
                if live_call.status in ["completed", "busy", "no-answer", "failed", "canceled"] and not call_data.get("analyzed"):
                    call_data["analyzed"] = True
                    transcript_entries = call_data.get("transcript", [])
                    if transcript_entries:
                        transcript_text = "\n".join(f"{m['role'].capitalize()}: {m['text']}" for m in transcript_entries)
                        cid = call_data.get("contact_id")
                        contact = None
                        if cid:
                            contact = db.query(models.Contact).filter(models.Contact.id == cid).first()
                        if not contact:
                            contact = db.query(models.Contact).first()
                        if not contact:
                            contact = models.Contact(
                                name="Phone Contact",
                                phone_number=call_data.get("to_number") or "+10000000000",
                                notes="Real Phone Caller",
                                interest_level="Unknown",
                            )
                            db.add(contact)
                            db.commit()
                            db.refresh(contact)
                        cid = contact.id
                        cname = contact.name
                        try:
                            analysis = llm_engine.analyze_call(transcript_text, cname)
                            db_call = models.Call(
                                contact_id=cid,
                                transcript=transcript_text,
                                summary=analysis.get("summary", ""),
                                sentiment=analysis.get("sentiment", "Neutral"),
                                outcome=analysis.get("outcome", "Needs Follow-up"),
                                lead_score=analysis.get("lead_score", 50),
                                lead_score_reasoning=analysis.get("lead_score_reasoning", ""),
                            )
                            db.add(db_call)
                            db.commit()
                            db.refresh(db_call)
                            call_data["analysis"] = analysis
                            call_data["call_id"] = db_call.id
                            try:
                                alerts_res = telegram_alert.send_all_alerts_detailed(
                                    contact_name=cname,
                                    lead_score=analysis.get("lead_score", 0),
                                    sentiment=analysis.get("sentiment", "Neutral"),
                                    summary=analysis.get("summary", ""),
                                    outcome=analysis.get("outcome", ""),
                                    reasoning=analysis.get("lead_score_reasoning", ""),
                                )
                                call_data["alerts_result"] = alerts_res
                                call_data["analysis"]["whatsapp_sent"] = alerts_res.get("whatsapp", {}).get("ok", False)
                                call_data["analysis"]["telegram_sent"] = alerts_res.get("telegram", {}).get("ok", False)
                                call_data["analysis"]["sms_sent"] = alerts_res.get("sms", {}).get("ok", False)
                            except Exception as alert_err:
                                print(f"[Twilio Active-Call Alert Error]: {alert_err}")
                        except Exception as a_err:
                            print(f"[Twilio Active-Call Analysis Error]: {a_err}")
        except Exception as poll_err:
            pass

    return call_data


@app.api_route("/api/twilio/voice", methods=["GET", "POST"])
async def twilio_voice_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Twilio calls this webhook when a call is connected (outbound answered, or inbound received).
    Returns TwiML instructions for speaking the greeting and gathering caller response.
    """
    import time, re
    from backend import twilio_service, models
    base_url = get_request_base_url(request)

    form_data = {}
    if request.method == "POST":
        try:
            form_data = await request.form()
        except Exception:
            pass

    call_sid = form_data.get("CallSid") or request.query_params.get("call_sid") or f"call_{int(time.time())}"
    from_num = form_data.get("From") or ""
    to_num = form_data.get("To") or ""
    mode = request.query_params.get("mode") or "outbound"

    try:
        # Contact matching
        contact_id = request.query_params.get("contact_id")
        contact = None
        if contact_id:
            try:
                contact = db.query(models.Contact).filter(models.Contact.id == int(contact_id)).first()
            except Exception:
                pass

        # If inbound call, try matching caller by phone number
        if not contact and from_num:
            clean_from = re.sub(r"\D", "", from_num)
            for c in db.query(models.Contact).all():
                if c.phone_number and clean_from in re.sub(r"\D", "", c.phone_number):
                    contact = c
                    break

        contact_name = contact.name if contact else "there"
        cid = contact.id if contact else None

        # Check language from query param or contact's preferred language
        lang_param = request.query_params.get("lang")
        call_lang = lang_param or (getattr(contact, "preferred_language", "en-US") if contact else "en-US") or "en-US"

        # Determine initial greeting
        if call_lang in ("kn-IN", "kn"):
            greeting = f"ನಮಸ್ಕಾರ {contact_name}! ವೋಕಲಿಕ್ಸ್‌ನಿಂದ ಅಲೆಕ್ಸ್ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ. ಹೇಗಿದ್ದೀರಾ?"
        elif call_lang in ("hi-IN", "hi"):
            greeting = f"नमस्ते {contact_name}! वोकलिक्स से एलेक्स बोल रहा हूँ। आप कैसे हैं?"
        elif mode == "marketing":
            greeting = f"Hi {contact_name}! This is Alex calling from Vocalyx with an exciting update for you. Do you have a quick minute?"
        elif mode == "inbound":
            greeting = f"Hello {contact_name}! Thank you for calling Vocalyx, this is Alex. How can I help you today?" if contact else "Hello, thank you for calling Vocalyx! My name is Alex. How may I assist you today?"
        else:
            greeting = f"Hello {contact_name}! This is Alex calling from Vocalyx. How are you doing today?"

        call_engine = twilio_service.active_calls.get(call_sid, {}).get("voice_engine") or getattr(config, "TWILIO_VOICE_ENGINE", "f5tts")
        if call_lang in ("kn-IN", "kn"):
            call_engine = "kannada_female"
        elif call_lang in ("hi-IN", "hi"):
            call_engine = "hindi_female"

        # Track in active calls
        if call_sid not in twilio_service.active_calls:
            twilio_service.active_calls[call_sid] = {
                "call_sid": call_sid,
                "contact_id": cid,
                "contact_name": contact_name,
                "to_number": to_num,
                "from_number": from_num,
                "mode": mode,
                "transcript": [{"role": "agent", "text": greeting}],
                "start_time": time.time(),
                "status": "in-progress",
                "voice_engine": call_engine,
                "language": call_lang,
            }
        else:
            twilio_service.active_calls[call_sid]["transcript"].append({"role": "agent", "text": greeting})
            twilio_service.active_calls[call_sid]["status"] = "in-progress"
            twilio_service.active_calls[call_sid]["voice_engine"] = call_engine
            twilio_service.active_calls[call_sid]["language"] = call_lang

        twiml_xml = twilio_service.build_twiml(greeting, call_sid, base_url, is_greeting=True, voice_engine=call_engine)
        return Response(content=twiml_xml, media_type="application/xml")
    except Exception as exc:
        print(f"[Twilio Voice Webhook Fallback]: {exc}")
        safe_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Play>{base_url}/tts_output/prewarmed_greeting.wav</Play><Gather action="{base_url}/api/twilio/respond?call_sid={call_sid}" input="speech" method="POST" speechTimeout="auto" timeout="8"/><Redirect method="POST">{base_url}/api/twilio/respond?call_sid={call_sid}&amp;silence=1</Redirect></Response>'
        return Response(content=safe_xml, media_type="application/xml")


@app.api_route("/api/twilio/respond", methods=["GET", "POST"])
async def twilio_respond_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Twilio calls this when caller speech has been recognized by <Gather> or on silence redirect.
    Runs RAG + Groq LLM + LuxTTS and returns next TwiML.
    """
    from backend import twilio_service, rag_engine, llm_engine, models, config
    base_url = get_request_base_url(request)

    try:
        form_data = {}
        if request.method == "POST":
            try:
                form_data = await request.form()
            except Exception:
                pass

        speech_result = form_data.get("SpeechResult", "").strip() or request.query_params.get("SpeechResult", "").strip()
        call_sid = form_data.get("CallSid") or request.query_params.get("call_sid") or request.query_params.get("CallSid") or "call_unknown"
        is_silence = bool(request.query_params.get("silence") or form_data.get("silence") or not speech_result)

        if call_sid not in twilio_service.active_calls:
            twilio_service.active_calls[call_sid] = {
                "call_sid": call_sid,
                "transcript": [],
                "silence_count": 0,
                "status": "in-progress"
            }
        call_state = twilio_service.active_calls[call_sid]
        contact_id = call_state.get("contact_id")
        call_engine = call_state.get("voice_engine") or getattr(config, "TWILIO_VOICE_ENGINE", "f5tts")

        # Handle silence or missing speech
        if is_silence or not speech_result:
            silence_count = call_state.get("silence_count", 0) + 1
            call_state["silence_count"] = silence_count
            print(f"[Twilio] Silence detected for call {call_sid} (count={silence_count})")

            if silence_count >= 2:
                print(f"[Twilio] Ending call {call_sid} due to repeated silence.")
                goodbye_path = os.path.join(config.TTS_OUTPUT_DIR, "prewarmed_goodbye.wav")
                twiml_xml = twilio_service.build_twiml(
                    "Thank you for your time with Vocalyx. Have a wonderful day!",
                    call_sid,
                    base_url,
                    wav_path=goodbye_path if os.path.exists(goodbye_path) else None,
                    is_final=True,
                    voice_engine=call_engine,
                )
                return Response(content=twiml_xml, media_type="application/xml")
            else:
                reprompt_path = os.path.join(config.TTS_OUTPUT_DIR, "prewarmed_reprompt.wav")
                twiml_xml = twilio_service.build_twiml(
                    "Are you still there? Please let me know how I can help.",
                    call_sid,
                    base_url,
                    wav_path=reprompt_path if os.path.exists(reprompt_path) else None,
                    is_greeting=False,
                    voice_engine=call_engine,
                )
                return Response(content=twiml_xml, media_type="application/xml")

        # Caller spoke -> Reset silence count!
        call_state["silence_count"] = 0
        print(f"[Twilio Caller Speech] Call {call_sid}: '{speech_result}'")

        contact_memory = {}
        previous_calls_data = []
        if contact_id:
            try:
                contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
                if contact:
                    contact_memory = {
                        "name": contact.name,
                        "phone_number": contact.phone_number,
                        "notes": contact.notes,
                        "last_topic": contact.last_topic,
                        "interest_level": contact.interest_level,
                        "concerns": contact.concerns,
                        "commitments": contact.commitments,
                    }
                    past_calls = db.query(models.Call).filter(models.Call.contact_id == contact.id).order_by(models.Call.created_at.desc()).limit(3).all()
                    for pc in reversed(past_calls):
                        previous_calls_data.append({
                            "date": pc.created_at.strftime("%b %d") if pc.created_at else None,
                            "summary": pc.summary,
                            "outcome": pc.outcome,
                        })
            except Exception:
                pass

        # Record user speech
        call_state.setdefault("transcript", []).append({"role": "user", "text": speech_result})

        # Query RAG + LLM with graceful fallbacks
        try:
            rag_context = rag_engine.search(speech_result)
        except Exception as rag_err:
            print(f"[RAG Note]: {rag_err}")
            rag_context = ""

        call_lang = call_state.get("language") or getattr(contact, "preferred_language", "en-US") or "en-US"
        if call_lang in ("kn-IN", "kn"):
            call_engine = "kannada_female"
            call_state["voice_engine"] = "kannada_female"
        elif call_lang in ("hi-IN", "hi"):
            call_engine = "hindi_female"
            call_state["voice_engine"] = "hindi_female"

        try:
            agent_reply = llm_engine.get_chat_response(
                user_message=speech_result,
                rag_context=rag_context,
                contact_memory=contact_memory,
                conversation_history=call_state.get("transcript", []),
                previous_calls=previous_calls_data,
                language=call_lang,
            )
        except Exception as llm_err:
            print(f"[LLM Note]: {llm_err}")
            agent_reply = "I understand. Let me check that and get right back to you on that."

        print(f"[Twilio AI Reply] Call {call_sid}: '{agent_reply}'")

        # Record agent response
        call_state["transcript"].append({"role": "agent", "text": agent_reply})

        import asyncio
        wav_path = None
        loop = asyncio.get_event_loop()
        if call_engine not in ["polly", "twilio_say", "say"]:
            try:
                tts_mod = sys.modules.get("backend.tts_engine")
                if tts_mod is None or not hasattr(tts_mod, "synthesize"):
                    from backend import tts_engine as tts_mod
                wav_path = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: tts_mod.synthesize(agent_reply, engine=call_engine)),
                    timeout=15.0
                )
            except asyncio.TimeoutError:
                print(f"[Twilio Webhook] Synthesis timeout ({call_engine}) for call {call_sid}")
                wav_path = None
            except Exception as synth_err:
                print(f"[Twilio Webhook] Synthesis note ({call_engine}): {synth_err}")
                wav_path = None

        # Build TwiML directly with the synthesized cloned audio or Polly speech:
        twiml_xml = twilio_service.build_twiml(agent_reply, call_sid, base_url, wav_path=wav_path, is_greeting=False, voice_engine=call_engine)
        return Response(content=twiml_xml, media_type="application/xml")
        return Response(content=twiml_xml, media_type="application/xml")
    except Exception as exc:
        print(f"[Twilio Respond Webhook Critical Error Handled]: {exc}")
        safe_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Play>{base_url}/tts_output/prewarmed_reprompt.wav</Play><Gather action="{base_url}/api/twilio/respond?call_sid={call_sid}" input="speech" method="POST" speechTimeout="auto" timeout="8"/><Redirect method="POST">{base_url}/api/twilio/respond?call_sid={call_sid}&amp;silence=2</Redirect></Response>'
        return Response(content=safe_xml, media_type="application/xml")


@app.api_route("/api/twilio/continue", methods=["GET", "POST"])
async def twilio_continue_webhook(request: Request):
    """
    Called by Twilio <Redirect> after playing the cloned filler audio.
    Delivers the synthesized cloned answer and gathers next caller speech.
    """
    import os, asyncio
    from backend import twilio_service, config
    base_url = get_request_base_url(request)

    form_data = {}
    if request.method == "POST":
        try:
            form_data = await request.form()
        except Exception:
            pass
    call_sid = form_data.get("CallSid") or request.query_params.get("call_sid") or request.query_params.get("CallSid") or "call_unknown"

    # Wait up to 12 seconds for background synthesis if finishing (Twilio timeout is 15s)
    wav_path = None
    for _ in range(60):
        wav_path = twilio_service.pregenerated_audio.pop(call_sid, None)
        if wav_path and os.path.exists(wav_path):
            break
        await asyncio.sleep(0.2)

    call_state = twilio_service.active_calls.get(call_sid, {})
    transcript = call_state.get("transcript", [])
    last_reply = "I am listening, please go ahead."
    for msg in reversed(transcript):
        if msg.get("role") == "agent":
            last_reply = msg.get("text", "")
            break

    # If background synthesis did not complete, use pre-warmed audio so it never hangs or crashes
    if not wav_path or not os.path.exists(wav_path):
        for candidate_name in ["prewarmed_reprompt.wav", "prewarmed_filler.wav"]:
            cand_path = os.path.join(config.TTS_OUTPUT_DIR, candidate_name)
            if os.path.exists(cand_path):
                wav_path = cand_path
                break

    twiml_xml = twilio_service.build_twiml(last_reply, call_sid, base_url, wav_path=wav_path, is_greeting=False)
    return Response(content=twiml_xml, media_type="application/xml")




@app.post("/api/twilio/status")
async def twilio_status_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Status callback from Twilio when call state changes (completed, busy, failed, etc.).
    Automatically saves call history, runs AI analysis, and sends Telegram alert.
    """
    from backend import twilio_service, llm_engine, models, telegram_alert
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    call_status = form_data.get("CallStatus", "").lower()
    call_duration = int(form_data.get("CallDuration", 0) or 0)

    print(f"[Twilio Status] CallSid={call_sid} Status={call_status} Duration={call_duration}s")

    if call_sid in twilio_service.active_calls:
        twilio_service.active_calls[call_sid]["status"] = call_status

    if call_status == "completed" and call_sid in twilio_service.active_calls:
        call_info = twilio_service.active_calls[call_sid]
        transcript_entries = call_info.get("transcript", [])

        if transcript_entries:
            transcript_text = "\n".join(
                f"{m['role'].capitalize()}: {m['text']}" for m in transcript_entries
            )
            cid = call_info.get("contact_id")
            contact = None
            if cid:
                contact = db.query(models.Contact).filter(models.Contact.id == cid).first()
            if not contact:
                contact = db.query(models.Contact).first()
            if not contact:
                contact = models.Contact(
                    name="Phone Contact",
                    phone_number=call_info.get("to_number") or "+10000000000",
                    notes="Real Phone Caller",
                    interest_level="Unknown",
                )
                db.add(contact)
                db.commit()
                db.refresh(contact)
            cid = contact.id
            cname = contact.name
            try:
                analysis = llm_engine.analyze_call(transcript_text, cname)
                db_call = models.Call(
                    contact_id=cid,
                    transcript=transcript_text,
                    summary=analysis.get("summary", ""),
                    sentiment=analysis.get("sentiment", "Neutral"),
                    outcome=analysis.get("outcome", "Needs Follow-up"),
                    lead_score=analysis.get("lead_score", 50),
                    lead_score_reasoning=analysis.get("lead_score_reasoning", ""),
                )
                db.add(db_call)
                db.commit()
                db.refresh(db_call)
                call_info["analysis"] = analysis
                call_info["call_id"] = db_call.id

                try:
                    alerts_res = telegram_alert.send_all_alerts_detailed(
                        contact_name=cname,
                        lead_score=analysis.get("lead_score", 0),
                        sentiment=analysis.get("sentiment", "Neutral"),
                        summary=analysis.get("summary", ""),
                        outcome=analysis.get("outcome", ""),
                        reasoning=analysis.get("lead_score_reasoning", ""),
                    )
                    call_info["alerts_result"] = alerts_res
                    call_info["analysis"]["whatsapp_sent"] = alerts_res.get("whatsapp", {}).get("ok", False)
                    call_info["analysis"]["telegram_sent"] = alerts_res.get("telegram", {}).get("ok", False)
                    call_info["analysis"]["sms_sent"] = alerts_res.get("sms", {}).get("ok", False)
                except Exception as alert_err:
                    print(f"[Twilio Status Alert Error]: {alert_err}")
            except Exception as e:
                print(f"[Twilio Status] Analysis error: {e}")

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    voice_info = get_voice_status()
    import torch
    from backend.config import GROQ_MODEL, GROQ_API_KEY, TELEGRAM_BOT_TOKEN
    from backend import twilio_service
    doc_count = 0
    try:
        doc_count = db.query(models.Document).count()
    except Exception:
        pass

    return {
        "status": "ok",
        "version": "1.0.0",
        "model": GROQ_MODEL,
        "tts": "ChatterboxTurboTTS (cuda)" if torch.cuda.is_available() else "ChatterboxTTS (cpu)",
        "rag_docs": doc_count,
        "telegram": bool(TELEGRAM_BOT_TOKEN),
        "groq_configured": bool(GROQ_API_KEY),
        "twilio_configured": twilio_service.is_configured(),
        "voice_clone": voice_info,
        "has_voice_clone": voice_info["has_voice_clone"],
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"[Vocalyx Startup] Running Uvicorn server on http://0.0.0.0:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
