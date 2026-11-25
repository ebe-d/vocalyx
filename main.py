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

# Reuse single tts_engine instance across __main__, main, and backend package imports
import types
_existing_tts = sys.modules.get("backend.tts_engine") or sys.modules.get("tts_engine")
if _existing_tts is not None and hasattr(_existing_tts, "synthesize"):
    _existing_tts.__package__ = "backend"
    sys.modules["backend.tts_engine"] = _existing_tts
    sys.modules["tts_engine"] = _existing_tts
    if "backend" in sys.modules:
        setattr(sys.modules["backend"], "tts_engine", _existing_tts)
else:
    _tts_file = os.path.join(_BACKEND_DIR, "tts_engine.py")
    if not os.path.exists(_tts_file):
        _tts_file = os.path.join(_CURR_DIR, "tts_engine.py")

    if os.path.exists(_tts_file):
        try:
            with open(_tts_file, "r") as _f:
                _code = _f.read()
            _tts_mod = types.ModuleType("backend.tts_engine")
            _tts_mod.__file__ = _tts_file
            _tts_mod.__package__ = "backend"
            exec(_code, _tts_mod.__dict__)
            sys.modules["backend.tts_engine"] = _tts_mod
            sys.modules["tts_engine"] = _tts_mod
            if "backend" in sys.modules:
                setattr(sys.modules["backend"], "tts_engine", _tts_mod)
            print(f"[Startup] ✓ Directly loaded TTS engine from {_tts_file} (synthesize: {hasattr(_tts_mod, 'synthesize')})")
        except Exception as _e:
            print(f"[Startup Error] Binding tts_engine: {_e}")

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import os, shutil, json, re, time, uuid
from datetime import datetime

SERVER_BOOT_ID = uuid.uuid4().hex[:12]

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
    # Pre-load RAG embedder in background so the first live phone call is never blocked
    try:
        from backend import rag_engine as _rag
        _rag.prewarm_embedder()
    except Exception as _rpe:
        print(f"[Startup] RAG prewarm note: {_rpe}")
    # Pre-load TTS model in background so first call doesn't cold-start (F5-TTS takes ~15s to load)
    try:
        from backend import tts_engine as _tts
        _tts.prewarm_model()
    except Exception as _tpe:
        print(f"[Startup] TTS model prewarm note: {_tpe}")
    # Seed default voices and sample script if the database is empty
    try:
        with next(get_db()) as _sdb:
            seed_default_voices_if_needed(_sdb)
            seed_default_script_if_needed(_sdb)
    except Exception as _seed_err:
        print(f"[Startup] Seed note: {_seed_err}")
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
    cache_hdr = "no-store, no-cache, must-revalidate" if filename.startswith("prewarmed_") else "public, max-age=3600"
    return FileResponse(
        filepath,
        media_type="audio/wav",
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": cache_hdr,
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
    call_context: Optional[str] = None
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
    voice_id: Optional[int] = None
    language: Optional[str] = None
    script_id: Optional[int] = None
    call_context: Optional[str] = None


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
    content_sid: Optional[str] = None
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

    context_parts = []
    if request.script_id:
        script = db.query(models.Script).filter(models.Script.id == request.script_id).first()
        if script and script.content:
            context_parts.append(f"[Call Script: {script.title}]\n{script.content.strip()}")
    if request.call_context and request.call_context.strip():
        ctx_txt = request.call_context.strip()
        if not context_parts or ctx_txt not in context_parts[0]:
            context_parts.append(f"[Caller Status & Live Context]\n{ctx_txt}")
    script_content = "\n\n".join(context_parts) if context_parts else None

    target_lang = request.language or contact_memory.get("preferred_language") or "en-US"

    # Determine active voice, reference audio, and persona BEFORE LLM response
    voice_engine = request.tts_engine
    selected_voice_obj = None
    ref_audio = None
    if request.voice_id:
        selected_voice_obj = db.query(models.Voice).filter(models.Voice.id == request.voice_id).first()
    elif not voice_engine:
        selected_voice_obj = db.query(models.Voice).filter(models.Voice.is_active == True).first()
    else:
        selected_voice_obj = db.query(models.Voice).filter(models.Voice.engine == voice_engine, models.Voice.is_active == True).first() \
            or db.query(models.Voice).filter(models.Voice.engine == voice_engine).first()

    if selected_voice_obj:
        voice_engine = voice_engine or selected_voice_obj.engine
        ref_audio = selected_voice_obj.audio_path

    # Auto-route to native studio edge-tts for non-English languages
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

    persona_name = _get_voice_persona_name(selected_voice_obj if not target_lang in ("kn-IN", "kn", "hi-IN", "hi") else None, voice_engine)

    response_text = llm_engine.get_chat_response(
        user_message=message,
        rag_context=rag_context,
        contact_memory=contact_memory,
        conversation_history=request.conversation_history,
        previous_calls=previous_calls_data,
        script_content=script_content,
        language=target_lang,
        agent_name=persona_name,
    )

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


def _get_voice_persona_name(voice_obj=None, engine: Optional[str] = None) -> str:
    """Resolve spoken persona name for the selected voice (e.g. Lawrence, Alex, Joanna, Sapna)."""
    if voice_obj and getattr(voice_obj, "name", None):
        short = voice_obj.name.split("(")[0].strip()
        if short:
            return short
    eng = (engine or "").lower()
    if "joanna" in eng or eng == "polly_female":
        return "Joanna"
    if "matthew" in eng or eng in ("polly", "polly_matthew"):
        return "Matthew"
    if eng == "kannada_female":
        return "Sapna"
    if eng == "kannada_male":
        return "Gagan"
    if eng == "hindi_female":
        return "Swara"
    if eng == "hindi_male":
        return "Madhur"
    return "Alex"


def _build_greeting_text(persona_name: str = "Alex", contact_name: str = "there", language: str = "en-US", mode: str = "outbound") -> str:
    """Build synchronized greeting text used identically in chat UI, pre-warm audio, and Twilio calls."""
    from backend import twilio_service
    return twilio_service.build_greeting_text(
        persona_name=persona_name,
        contact_name=contact_name,
        language=language,
        mode=mode,
    )


def _compose_script_and_context(db: Session, script_id_val, raw_call_context: Optional[str]) -> Optional[str]:
    """Compose canonical script + caller context string used identically across prewarm, dial, and webhooks."""
    parts = []
    if script_id_val:
        try:
            s_obj = db.query(models.Script).filter(models.Script.id == int(script_id_val)).first()
            if s_obj and s_obj.content:
                parts.append(f"[Call Script: {s_obj.title}]\n{s_obj.content.strip()}")
        except Exception:
            pass
    ctx_clean = (raw_call_context or "").strip()
    if ctx_clean:
        if not parts or ctx_clean not in parts[0]:
            parts.append(f"[Caller Status & Live Context]\n{ctx_clean}")
    return "\n\n".join(parts) if parts else None


def _sync_active_voice_audio(audio_path: Optional[str]):
    """Point runtime reference path to the selected voice WITHOUT overwriting immutable Alex/voice_clone files."""
    from backend import tts_engine
    if audio_path and os.path.exists(audio_path):
        config.REFERENCE_AUDIO_PATH = audio_path
    tts_engine._cached_lux_prompt = None
    tts_engine._cached_chatterbox_ref = None
    for cf in [
        "voice_clone_lux_conds.pt",
        "voice_clone_conds.pt",
        "prewarmed_greeting.wav",
        "prewarmed_greeting.txt",
        "prewarmed_greeting.meta.json",
        "prewarmed_reprompt.wav",
        "prewarmed_goodbye.wav",
    ]:
        fp = os.path.join(TTS_OUTPUT_DIR, cf)
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except Exception:
                pass


@app.get("/api/tts/prewarm-status")
def get_tts_prewarm_status(db: Session = Depends(get_db)):
    """Check if the cloned voice engine is pre-warmed and ready on GPU."""
    from backend import tts_engine, config
    prewarmed_file = os.path.join(config.TTS_OUTPUT_DIR, "prewarmed_greeting.wav")
    is_ready = os.path.exists(prewarmed_file) and os.path.getsize(prewarmed_file) > 1000
    voice_status = get_voice_status()
    active_v = db.query(models.Voice).filter(models.Voice.is_active == True).first()
    return {
        "ready": is_ready,
        "boot_id": SERVER_BOOT_ID,
        "greeting_url": (active_v.preview_url if active_v and active_v.preview_url else "/tts_output/prewarmed_greeting.wav") if is_ready else None,
        "model_loaded": any(
            getattr(tts_engine, attr, None) is not None
            for attr in ("f5_model", "lux_model", "chatterbox_model", "tts_model")
        ),
        "device": str(getattr(tts_engine, "_device", "none")),
        "has_voice_clone": voice_status["has_voice_clone"],
        "active_voice_id": active_v.id if active_v else None,
        "active_voice_name": active_v.name if active_v else None,
    }


class TTSPrewarmRequest(BaseModel):
    engine: Optional[str] = None
    voice_id: Optional[int] = None


@app.post("/api/tts/prewarm")
async def post_tts_prewarm(request: Request, db: Session = Depends(get_db)):
    """
    Pre-warms the selected voice, syncs its exact audio reference, and generates a
    personalized greeting wav + exact greeting_text so browser chat, audio, and Twilio match.
    """
    import time
    t0 = time.time()
    from backend import tts_engine, config
    req_engine = request.query_params.get("engine")
    req_voice_id = request.query_params.get("voice_id")
    req_lang = request.query_params.get("language") or "en-US"
    req_contact_id = request.query_params.get("contact_id")
    req_contact_name = request.query_params.get("contact_name")
    req_mode = request.query_params.get("mode") or "outbound"
    req_script_id = request.query_params.get("script_id")
    req_call_context = ""
    try:
        body = await request.json()
        if isinstance(body, dict):
            req_engine = req_engine or body.get("engine")
            req_voice_id = req_voice_id or body.get("voice_id")
            req_lang = body.get("language") or req_lang
            req_contact_id = req_contact_id or body.get("contact_id")
            req_contact_name = req_contact_name or body.get("contact_name")
            req_mode = body.get("mode") or req_mode
            req_script_id = req_script_id or body.get("script_id")
            req_call_context = (body.get("call_context") or "").strip()
    except Exception:
        pass

    selected_voice = None
    if req_voice_id:
        try:
            selected_voice = db.query(models.Voice).filter(models.Voice.id == int(req_voice_id)).first()
        except Exception:
            selected_voice = None
    if not selected_voice and req_engine:
        selected_voice = db.query(models.Voice).filter(models.Voice.engine == req_engine.lower(), models.Voice.is_active == True).first() \
            or db.query(models.Voice).filter(models.Voice.engine == req_engine.lower()).first()
    if not selected_voice:
        selected_voice = db.query(models.Voice).filter(models.Voice.is_active == True).first()

    # Keep DB active voice synced when pre-warming a specific voice row
    if selected_voice and not selected_voice.is_active:
        db.query(models.Voice).update({models.Voice.is_active: False})
        selected_voice.is_active = True
        db.commit()

    active_engine = (req_engine or (selected_voice.engine if selected_voice else None) or getattr(config, "TWILIO_VOICE_ENGINE", "f5tts")).lower()
    if req_lang in ("kn-IN", "kn"):
        active_engine = "kannada_male" if ("male" in active_engine and "female" not in active_engine) else "kannada_female"
    elif req_lang in ("hi-IN", "hi"):
        active_engine = "hindi_male" if ("male" in active_engine and "female" not in active_engine) else "hindi_female"

    contact_name = (req_contact_name or "").strip()
    if not contact_name and req_contact_id:
        try:
            c_obj = db.query(models.Contact).filter(models.Contact.id == int(req_contact_id)).first()
            if c_obj:
                contact_name = c_obj.name
        except Exception:
            pass
    if not contact_name:
        contact_name = "there"

    persona_name = _get_voice_persona_name(
        selected_voice if req_lang not in ("kn-IN", "kn", "hi-IN", "hi") else None,
        active_engine,
    )
    combined_ctx = _compose_script_and_context(db, req_script_id, req_call_context)

    custom_greeting = None
    if combined_ctx:
        try:
            from backend import llm_engine
            custom_greeting = llm_engine.generate_context_greeting(
                persona_name=persona_name,
                contact_name=contact_name,
                script_content=combined_ctx,
                language=req_lang,
                mode=req_mode,
            )
        except Exception:
            custom_greeting = None

    greeting_text = custom_greeting or _build_greeting_text(
        persona_name=persona_name,
        contact_name=contact_name,
        language=req_lang,
        mode=req_mode,
    )

    try:
        from backend import twilio_service
        ref_audio = None
        if selected_voice and selected_voice.voice_type == "cloned" and selected_voice.audio_path and os.path.exists(selected_voice.audio_path):
            ref_audio = selected_voice.audio_path
        _sync_active_voice_audio(ref_audio)
        config.TWILIO_VOICE_ENGINE = active_engine

        wav_path = tts_engine.prewarm_engine(greeting_text, engine=active_engine, reference_audio=ref_audio)
        prewarm_sig = twilio_service.compute_greeting_signature(
            voice_engine=active_engine,
            voice_id=selected_voice.id if selected_voice else None,
            language=req_lang,
            contact_id=req_contact_id,
            mode=req_mode,
            script_id=req_script_id,
            custom_context=combined_ctx,
            persona_name=persona_name,
        )
        twilio_service.save_prewarm_meta({
            "signature": prewarm_sig,
            "text": greeting_text,
            "boot_id": SERVER_BOOT_ID,
            "engine": active_engine,
            "voice_id": selected_voice.id if selected_voice else None,
            "language": req_lang,
            "contact_id": str(req_contact_id or ""),
            "mode": req_mode,
            "script_id": str(req_script_id or ""),
            "persona_name": persona_name,
        })
        elapsed = time.time() - t0
        print(
            f"[TTS Pre-Warm Complete] engine={active_engine} persona={persona_name} "
            f"f5_loaded={getattr(tts_engine, 'f5_model', None) is not None} "
            f"lux_loaded={getattr(tts_engine, 'lux_model', None) is not None} ({elapsed:.2f}s)"
        )
        return {
            "success": True,
            "ready": True,
            "boot_id": SERVER_BOOT_ID,
            "greeting_url": "/tts_output/prewarmed_greeting.wav",
            "greeting_text": greeting_text,
            "voice_id": selected_voice.id if selected_voice else None,
            "voice_name": selected_voice.name if selected_voice else persona_name,
            "persona_name": persona_name,
            "language": req_lang,
            "mode": req_mode,
            "elapsed_seconds": round(elapsed, 2),
            "message": f"Voice ({persona_name} — {active_engine.upper()}) pre-warmed in {elapsed:.1f}s and ready.",
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
    alex_ref = "default_voices/alex_reference.mp3" if os.path.exists("default_voices/alex_reference.mp3") else "voice_clone.mp3"
    defaults = [
        models.Voice(
            name="Alex (Default F5-TTS Flow-Matching)",
            engine="f5tts",
            voice_type="cloned",
            audio_path=alex_ref,
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
            audio_path=alex_ref,
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
        # Ensure Alex defaults use immutable alex_reference.mp3 & Joanna/Matthew keep audio references
        for v in existing:
            if "alex" in (v.name or "").lower() and v.engine in ("f5tts", "luxtts"):
                if os.path.exists("default_voices/alex_reference.mp3"):
                    v.audio_path = "default_voices/alex_reference.mp3"
            elif "joanna" in v.name.lower() or "natural us female" in v.name.lower():
                v.engine = "polly_joanna"
                v.preview_url = "/tts_output/joanna_greeting.wav"
                v.audio_path = "default_voices/female_reference.wav"
            elif "matthew" in v.name.lower() or "natural us male" in v.name.lower():
                v.engine = "polly_matthew"
                v.preview_url = "/tts_output/matthew_greeting.wav"
        # Purge any legacy chatterbox entries from voices table
        db.query(models.Voice).filter(models.Voice.engine == "chatterbox").delete()
        db.commit()


def seed_default_script_if_needed(db: Session):
    """Seed one clean sample call script if the scripts table is empty."""
    if db.query(models.Script).count() > 0:
        return
    sample_script = models.Script(
        title="Vocalyx Appointment & Demo Scheduler",
        content="""CALL OBJECTIVE: Book a 20-minute product demo for Vocalyx AI calling platform.

STEP 1 — QUALIFY (after caller responds to greeting):
Acknowledge the caller warmly. Ask if this is a convenient time for a quick chat.

STEP 2 — QUALIFY ROLE:
Ask: "Are you currently handling sales or support calls for your team?"
If YES → move to Step 3.
If NO → politely ask who the right person might be, and offer to call back.

STEP 3 — VALUE PITCH (keep under 2 sentences total):
Mention that Vocalyx automates outbound calling with a cloned voice, handles scheduling, and logs every conversation automatically. Teams typically save 3 to 4 hours a day.

STEP 4 — SCHEDULE DEMO:
Ask: "Would a quick 20-minute demo this week work for you? We can do Tuesday or Wednesday afternoon."
Confirm the date and time the caller suggests.

STEP 5 — CLOSE:
Confirm the booking, tell them you will send a calendar invite, and thank them warmly for their time.

TONE: Professional, calm, concise. Never read these step labels aloud. Speak naturally as if you wrote every word yourself.""",
    )
    db.add(sample_script)
    db.commit()
    print("[Startup] Seeded default sample script: 'Vocalyx Appointment & Demo Scheduler'")


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
        try:
            from backend import tts_engine
            _sync_active_voice_audio(new_voice.audio_path)
            tts_engine.prewarm_engine(engine=new_voice.engine, reference_audio=new_voice.audio_path)
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
    try:
        from backend import tts_engine
        ref_arg = voice.audio_path if voice.audio_path and os.path.exists(voice.audio_path) else None
        _sync_active_voice_audio(ref_arg)
        tts_engine.prewarm_engine(engine=voice.engine, reference_audio=ref_arg)
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


class LLMConfigUpdate(BaseModel):
    api_key: Optional[str] = None
    model: Optional[str] = None


@app.get("/api/llm/config")
def get_llm_config():
    from backend import llm_engine
    return llm_engine.get_config()


@app.post("/api/llm/config")
def update_llm_config(req: LLMConfigUpdate):
    from backend import llm_engine
    cfg = llm_engine.update_config(api_key=req.api_key, model=req.model)
    test_res = llm_engine.verify_credentials()
    return {"success": True, **cfg, "verification": test_res}


@app.post("/api/llm/test")
def test_llm_connection():
    from backend import llm_engine
    return llm_engine.verify_credentials()


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
        ok, res = alerts_service.send_whatsapp(
            test_msg,
            to_phone=req.to_phone,
            from_phone=req.from_phone,
            content_sid=req.content_sid,
            template_vars={"1": "Alex Smith (Test) — Score 92/100 (Positive, Interested)", "2": "Vocalyx Test Alert"},
        )
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

    selected_voice = None
    if call_req.voice_id:
        selected_voice = db.query(models.Voice).filter(models.Voice.id == int(call_req.voice_id)).first()
    if not selected_voice and call_req.voice_engine:
        selected_voice = db.query(models.Voice).filter(models.Voice.engine == call_req.voice_engine.strip().lower(), models.Voice.is_active == True).first() \
            or db.query(models.Voice).filter(models.Voice.engine == call_req.voice_engine.strip().lower()).first()
    if not selected_voice:
        selected_voice = db.query(models.Voice).filter(models.Voice.is_active == True).first()

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

    eff_engine = (call_req.voice_engine or (selected_voice.engine if selected_voice else None) or config.TWILIO_VOICE_ENGINE or "f5tts").strip().lower()
    if call_lang in ("kn-IN", "kn"):
        eff_engine = "kannada_male" if ("male" in eff_engine and "female" not in eff_engine) else "kannada_female"
    elif call_lang in ("hi-IN", "hi"):
        eff_engine = "hindi_male" if ("male" in eff_engine and "female" not in eff_engine) else "hindi_female"

    ref_audio = selected_voice.audio_path if selected_voice and selected_voice.voice_type == "cloned" and selected_voice.audio_path and os.path.exists(selected_voice.audio_path) else None
    persona_name = _get_voice_persona_name(
        selected_voice if (call_lang or "en-US") not in ("kn-IN", "kn", "hi-IN", "hi") else None,
        eff_engine,
    )

    combined_call_context = _compose_script_and_context(db, call_req.script_id, call_req.call_context)

    try:
        res = twilio_service.make_outbound_call(
            to_number=call_req.to_number,
            contact_id=call_req.contact_id,
            mode=call_req.mode or "outbound",
            base_url=base_url,
            voice_engine=eff_engine,
            language=call_lang,
            voice_id=selected_voice.id if selected_voice else call_req.voice_id,
            reference_audio=ref_audio,
            persona_name=persona_name,
            script_id=call_req.script_id,
            custom_context=combined_call_context,
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

    return {k: v for k, v in call_data.items() if k != "pending_futures"}


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

        existing_call = twilio_service.active_calls.get(call_sid, {})
        active_voice_db = db.query(models.Voice).filter(models.Voice.is_active == True).first()
        call_engine = existing_call.get("voice_engine") or (active_voice_db.engine if active_voice_db else None) or getattr(config, "TWILIO_VOICE_ENGINE", "f5tts")
        call_ref_audio = existing_call.get("reference_audio") or (active_voice_db.audio_path if active_voice_db and active_voice_db.voice_type == "cloned" else None)

        if call_lang in ("kn-IN", "kn"):
            call_engine = "kannada_male" if ("male" in (call_engine or "").lower() and "female" not in (call_engine or "").lower()) else "kannada_female"
        elif call_lang in ("hi-IN", "hi"):
            call_engine = "hindi_male" if ("male" in (call_engine or "").lower() and "female" not in (call_engine or "").lower()) else "hindi_female"

        persona_name = existing_call.get("persona_name") or _get_voice_persona_name(
            active_voice_db if call_lang not in ("kn-IN", "kn", "hi-IN", "hi") else None,
            call_engine,
        )

        script_id_param = request.query_params.get("script_id") or existing_call.get("script_id")
        call_custom_ctx = (existing_call.get("custom_context") or "").strip()
        if not call_custom_ctx and script_id_param:
            try:
                s_obj = db.query(models.Script).filter(models.Script.id == int(script_id_param)).first()
                if s_obj and s_obj.content:
                    call_custom_ctx = f"[Call Script: {s_obj.title}]\n{s_obj.content.strip()}"
            except Exception:
                pass

        # Use exact locked greeting from make_outbound_call when present so phone audio == chat transcript.
        greeting = (existing_call.get("greeting_text") or "").strip() or None
        if not greeting:
            target_sig = twilio_service.compute_greeting_signature(
                voice_engine=call_engine,
                voice_id=existing_call.get("voice_id") or (active_voice_db.id if active_voice_db else None),
                language=call_lang,
                contact_id=cid,
                mode=mode,
                script_id=script_id_param,
                custom_context=call_custom_ctx,
                persona_name=persona_name,
            )
            prewarm_meta = twilio_service.get_prewarm_meta()
            if prewarm_meta.get("signature") == target_sig and prewarm_meta.get("text"):
                greeting = prewarm_meta["text"].strip()
        if not greeting and call_custom_ctx:
            try:
                from backend import llm_engine as _llm
                greeting = _llm.generate_context_greeting(
                    persona_name=persona_name,
                    contact_name=contact_name,
                    script_content=call_custom_ctx,
                    language=call_lang,
                    mode=mode,
                )
            except Exception as _ge:
                print(f"[Twilio Voice Webhook] Context greeting note: {_ge}")
        if not greeting:
            greeting = _build_greeting_text(
                persona_name=persona_name,
                contact_name=contact_name,
                language=call_lang,
                mode=mode,
            )

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
                "reference_audio": call_ref_audio,
                "persona_name": persona_name,
                "language": call_lang,
                "script_id": int(script_id_param) if script_id_param else None,
                "custom_context": call_custom_ctx,
            }
        else:
            twilio_service.active_calls[call_sid]["transcript"].append({"role": "agent", "text": greeting})
            twilio_service.active_calls[call_sid]["status"] = "in-progress"
            twilio_service.active_calls[call_sid]["voice_engine"] = call_engine
            twilio_service.active_calls[call_sid]["reference_audio"] = call_ref_audio
            twilio_service.active_calls[call_sid]["persona_name"] = persona_name
            twilio_service.active_calls[call_sid]["language"] = call_lang
            if call_custom_ctx:
                twilio_service.active_calls[call_sid]["custom_context"] = call_custom_ctx
            if script_id_param:
                twilio_service.active_calls[call_sid]["script_id"] = int(script_id_param)

        twiml_xml = twilio_service.build_twiml(greeting, call_sid, base_url, is_greeting=True, voice_engine=call_engine, reference_audio=call_ref_audio)
        return Response(content=twiml_xml, media_type="application/xml")
    except Exception as exc:
        print(f"[Twilio Voice Webhook Fallback]: {exc}")
        safe_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Play>{base_url}/tts_output/prewarmed_greeting.wav</Play><Gather action="{base_url}/api/twilio/respond?call_sid={call_sid}" input="speech" method="POST" speechTimeout="auto" timeout="10" actionOnEmptyResult="true"/></Response>'
        return Response(content=safe_xml, media_type="application/xml")


def _build_continue_twiml(public_url: str, call_sid: str, turn_id: str, hop: int, pause_len: int = 3) -> str:
    """Build TwiML that briefly pauses and redirects Twilio to poll synthesized audio."""
    from twilio.twiml.voice_response import VoiceResponse
    vr = VoiceResponse()
    vr.pause(length=pause_len)
    vr.redirect(
        f"{public_url}/api/twilio/continue?call_sid={call_sid}&turn={turn_id}&hop={hop}",
        method="POST",
    )
    return str(vr)


def _load_respond_call_context(contact_id, script_id_val, custom_context: str):
    """Fetch contact memory, prior call summaries, and script text inside a short-lived DB session."""
    from backend import database, models
    contact_memory = {}
    previous_calls_data = []
    contact_preferred_lang = None
    call_script_content = (custom_context or "").strip()

    with database.SessionLocal() as db:
        if contact_id:
            try:
                contact = db.query(models.Contact).filter(models.Contact.id == int(contact_id)).first()
                if contact:
                    contact_preferred_lang = getattr(contact, "preferred_language", None)
                    contact_memory = {
                        "name": contact.name,
                        "phone_number": contact.phone_number,
                        "notes": contact.notes,
                        "last_topic": contact.last_topic,
                        "interest_level": contact.interest_level,
                        "concerns": contact.concerns,
                        "commitments": contact.commitments,
                    }
                    past_calls = (
                        db.query(models.Call)
                        .filter(models.Call.contact_id == contact.id)
                        .order_by(models.Call.created_at.desc())
                        .limit(3)
                        .all()
                    )
                    for pc in reversed(past_calls):
                        previous_calls_data.append({
                            "date": pc.created_at.strftime("%b %d") if pc.created_at else None,
                            "summary": pc.summary,
                            "outcome": pc.outcome,
                        })
            except Exception:
                pass
        if not call_script_content and script_id_val:
            try:
                s_obj = db.query(models.Script).filter(models.Script.id == int(script_id_val)).first()
                if s_obj and s_obj.content:
                    call_script_content = f"[Call Script: {s_obj.title}]\n{s_obj.content.strip()}"
            except Exception:
                pass

    return contact_memory, previous_calls_data, contact_preferred_lang, call_script_content


@app.api_route("/api/twilio/respond", methods=["GET", "POST"])
async def twilio_respond_webhook(request: Request):
    """
    Twilio calls this when caller speech has been recognized by <Gather> or on silence redirect.
    Runs RAG + Groq LLM + TTS and returns next TwiML, handing off cleanly if synthesis exceeds budget.
    """
    import asyncio
    t_req_start = time.monotonic()
    from backend import twilio_service, rag_engine, llm_engine, config
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

        # Record user speech and fetch DB context inside a short-lived synchronous helper
        call_state.setdefault("transcript", []).append({"role": "user", "text": speech_result})
        transcript_snapshot = list(call_state.get("transcript", []))

        loop = asyncio.get_running_loop()
        contact_memory, previous_calls_data, contact_preferred_lang, call_script_content = await loop.run_in_executor(
            None,
            _load_respond_call_context,
            contact_id,
            call_state.get("script_id"),
            call_state.get("custom_context") or "",
        )

        call_lang = call_state.get("language") or contact_preferred_lang or "en-US"
        if call_lang in ("kn-IN", "kn"):
            call_engine = "kannada_male" if ("male" in (call_engine or "").lower() and "female" not in (call_engine or "").lower()) else "kannada_female"
            call_state["voice_engine"] = call_engine
        elif call_lang in ("hi-IN", "hi"):
            call_engine = "hindi_male" if ("male" in (call_engine or "").lower() and "female" not in (call_engine or "").lower()) else "hindi_female"
            call_state["voice_engine"] = call_engine

        call_ref_audio = call_state.get("reference_audio")
        call_persona = call_state.get("persona_name") or _get_voice_persona_name(None, call_engine)

        def _rag_and_llm():
            try:
                rag_ctx = rag_engine.search(speech_result)
            except Exception as rag_err:
                print(f"[RAG Note]: {rag_err}")
                rag_ctx = ""
            return llm_engine.get_chat_response(
                user_message=speech_result,
                rag_context=rag_ctx,
                contact_memory=contact_memory,
                conversation_history=transcript_snapshot,
                previous_calls=previous_calls_data,
                script_content=call_script_content or None,
                language=call_lang,
                agent_name=call_persona,
            )

        try:
            agent_reply = await asyncio.wait_for(loop.run_in_executor(None, _rag_and_llm), timeout=6.5)
        except Exception as llm_err:
            print(f"[LLM Note]: {llm_err}")
            agent_reply = "I understand. Let me check that and get right back to you on that."

        print(f"[Twilio AI Reply] Call {call_sid} ({call_persona}): '{agent_reply}'")

        # Record agent response
        call_state["transcript"].append({"role": "agent", "text": agent_reply})
        turn_id = str(len(call_state["transcript"]))
        synth_key = f"{call_sid}:{turn_id}"

        wav_path = None
        is_cloned_engine = not any(k in (call_engine or "").lower() for k in ["polly", "say", "native"])
        if is_cloned_engine:
            from backend import tts_engine as tts_mod

            def _run_tts():
                out = tts_mod.synthesize(agent_reply, reference_audio=call_ref_audio, engine=call_engine)
                if out and os.path.exists(out):
                    twilio_service.pregenerated_audio[synth_key] = out
                return out

            synth_future = loop.run_in_executor(None, _run_tts)
            twilio_service.pending_synth_futures[synth_key] = synth_future

            model_cold = (
                (call_engine or "").lower() in ("f5tts", "f5-tts", "f5")
                and getattr(tts_mod, "f5_model", None) is None
            )
            deadline = t_req_start + (1.2 if model_cold else 5.5)
            while not synth_future.done() and time.monotonic() < deadline:
                await asyncio.sleep(0.08)

            if synth_future.done():
                twilio_service.pregenerated_audio.pop(synth_key, None)
                twilio_service.pending_synth_futures.pop(synth_key, None)
                try:
                    wav_path = synth_future.result()
                except Exception as synth_err:
                    print(f"[Twilio Webhook] Synthesis note ({call_engine}): {synth_err}")
                    wav_path = None
            else:
                public_url = twilio_service.resolve_base_url(base_url)
                handoff_xml = _build_continue_twiml(public_url, call_sid, turn_id, hop=1, pause_len=3)
                print(
                    f"[Twilio Webhook] Fast handoff to /api/twilio/continue after "
                    f"{time.monotonic() - t_req_start:.2f}s (turn={turn_id}, cold={model_cold})"
                )
                return Response(content=handoff_xml, media_type="application/xml")

        # Build TwiML directly with the synthesized audio or Polly speech
        twiml_xml = twilio_service.build_twiml(agent_reply, call_sid, base_url, wav_path=wav_path, is_greeting=False, voice_engine=call_engine, reference_audio=call_ref_audio)
        return Response(content=twiml_xml, media_type="application/xml")
    except Exception as exc:
        print(f"[Twilio Respond Webhook Critical Error Handled]: {exc}")
        from twilio.twiml.voice_response import VoiceResponse, Gather
        public_url = twilio_service.resolve_base_url(base_url)
        vr = VoiceResponse()
        vr.play(f"{public_url}/tts_output/prewarmed_reprompt.wav")
        vr.append(Gather(input="speech", action=f"{public_url}/api/twilio/respond?call_sid={call_sid}", method="POST", speech_timeout="auto", timeout=10, action_on_empty_result=True))
        return Response(content=str(vr), media_type="application/xml")


@app.api_route("/api/twilio/continue", methods=["GET", "POST"])
async def twilio_continue_webhook(request: Request):
    """
    Called by Twilio <Redirect> when TTS synthesis extends past the initial webhook budget.
    Responds strictly within ~2.5s per hop so HTTP requests never hit Twilio's 15s timeout even under GIL load.
    """
    import asyncio
    t_cont_start = time.monotonic()
    from backend import twilio_service, config
    base_url = get_request_base_url(request)
    call_sid = "call_unknown"

    try:
        form_data = {}
        if request.method == "POST":
            try:
                form_data = await request.form()
            except Exception:
                pass
        call_sid = form_data.get("CallSid") or request.query_params.get("call_sid") or request.query_params.get("CallSid") or "call_unknown"
        turn_id = request.query_params.get("turn") or ""
        try:
            hop = int(request.query_params.get("hop", "1") or "1")
        except ValueError:
            hop = 1

        call_state = twilio_service.active_calls.get(call_sid, {})
        synth_key = f"{call_sid}:{turn_id}" if turn_id else call_sid
        pending_future = twilio_service.pending_synth_futures.get(synth_key) if turn_id else None

        # Short wall-clock poll (max 2.5s) guarantees fast HTTP 200 back to Twilio well under 15s
        wav_path = None
        cont_deadline = t_cont_start + 2.5
        while time.monotonic() < cont_deadline:
            wav_path = twilio_service.pregenerated_audio.pop(synth_key, None)
            if not wav_path and not turn_id:
                wav_path = twilio_service.pregenerated_audio.pop(call_sid, None)
            if wav_path and os.path.exists(wav_path):
                twilio_service.pending_synth_futures.pop(synth_key, None)
                break
            wav_path = None
            if pending_future is not None and pending_future.done():
                twilio_service.pending_synth_futures.pop(synth_key, None)
                try:
                    cand = pending_future.result()
                    if cand and os.path.exists(cand):
                        wav_path = cand
                except Exception as cont_err:
                    print(f"[Twilio Continue] Synthesis future error: {cont_err}")
                break
            await asyncio.sleep(0.12)

        print(
            f"[Twilio Continue] Call {call_sid} turn={turn_id} hop={hop} "
            f"wav_ready={bool(wav_path)} future_done={pending_future.done() if pending_future else 'none'} "
            f"elapsed={time.monotonic() - t_cont_start:.2f}s"
        )

        if (not wav_path or not os.path.exists(wav_path)) and hop < 10 and pending_future is not None and not pending_future.done():
            public_url = twilio_service.resolve_base_url(base_url)
            handoff_xml = _build_continue_twiml(public_url, call_sid, turn_id, hop=hop + 1, pause_len=3)
            return Response(content=handoff_xml, media_type="application/xml")

        if turn_id:
            twilio_service.pending_synth_futures.pop(synth_key, None)

        transcript = call_state.get("transcript", [])
        last_reply = "I am listening, please go ahead."
        for msg in reversed(transcript):
            if msg.get("role") == "agent":
                last_reply = msg.get("text", "")
                break

        if not wav_path or not os.path.exists(wav_path):
            for candidate_name in ["prewarmed_reprompt.wav", "prewarmed_filler.wav"]:
                cand_path = os.path.join(config.TTS_OUTPUT_DIR, candidate_name)
                if os.path.exists(cand_path):
                    wav_path = cand_path
                    break

        call_engine = call_state.get("voice_engine") or getattr(config, "TWILIO_VOICE_ENGINE", "f5tts")
        call_ref = call_state.get("reference_audio")
        twiml_xml = twilio_service.build_twiml(last_reply, call_sid, base_url, wav_path=wav_path, is_greeting=False, voice_engine=call_engine, reference_audio=call_ref)
        return Response(content=twiml_xml, media_type="application/xml")
    except Exception as exc:
        print(f"[Twilio Continue Fallback]: {exc}")
        from twilio.twiml.voice_response import VoiceResponse, Gather
        public_url = twilio_service.resolve_base_url(base_url)
        vr = VoiceResponse()
        vr.play(f"{public_url}/tts_output/prewarmed_reprompt.wav")
        vr.append(Gather(input="speech", action=f"{public_url}/api/twilio/respond?call_sid={call_sid}", method="POST", speech_timeout="auto", timeout=10, action_on_empty_result=True))
        return Response(content=str(vr), media_type="application/xml")




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
    from backend import twilio_service, llm_engine, alerts_service
    llm_cfg = llm_engine.get_config()
    alerts_cfg = alerts_service.get_config()
    doc_count = 0
    try:
        doc_count = db.query(models.Document).count()
    except Exception:
        pass

    return {
        "status": "ok",
        "version": "1.0.0",
        "model": llm_cfg.get("model", "openai/gpt-oss-20b"),
        "tts": "F5-TTS / LuxTTS (cuda)" if torch.cuda.is_available() else "F5-TTS / Edge-TTS (cpu)",
        "rag_docs": doc_count,
        "telegram": bool(alerts_cfg.get("telegram", {}).get("ready")),
        "groq_configured": bool(llm_cfg.get("configured")),
        "twilio_configured": twilio_service.is_configured(),
        "voice_clone": voice_info,
        "has_voice_clone": voice_info["has_voice_clone"],
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"[Vocalyx Startup] Running Uvicorn server on http://0.0.0.0:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
