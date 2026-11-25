"""
LLM engine using the Groq API (moonshotai/kimi-k2-instruct).
Provides conversational responses and post-call analysis.
"""
import json
import os
from typing import Optional

from groq import Groq

from backend import config

_BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
LLM_SETTINGS_FILE = os.path.join(_BASE_DIR, "llm_settings.json")

_client = None
_client_key = None


def _load_persisted_config():
    """Load Groq API key and model saved from the UI if present on disk."""
    for cand in (LLM_SETTINGS_FILE, "llm_settings.json", os.path.join("backend", "llm_settings.json")):
        if os.path.exists(cand):
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    if data.get("api_key"):
                        config.GROQ_API_KEY = str(data["api_key"]).strip()
                        os.environ["GROQ_API_KEY"] = config.GROQ_API_KEY
                    if data.get("model"):
                        config.GROQ_MODEL = str(data["model"]).strip()
                        os.environ["GROQ_MODEL"] = config.GROQ_MODEL
                    print(f"[LLM Config] Restored Groq settings from {cand}")
                    return
            except Exception as exc:
                print(f"[LLM Config Load Note]: {exc}")


def _persist_config():
    """Save Groq settings to disk so frontend updates survive backend restarts."""
    data = {
        "api_key": get_active_api_key(),
        "model": get_active_model(),
    }
    for dest in (LLM_SETTINGS_FILE, "llm_settings.json"):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            print(f"[LLM Config Save Note]: {exc}")


def get_active_api_key() -> str:
    return (getattr(config, "GROQ_API_KEY", "") or os.getenv("GROQ_API_KEY", "")).strip()


def get_active_model() -> str:
    return (getattr(config, "GROQ_MODEL", "") or os.getenv("GROQ_MODEL", "") or "openai/gpt-oss-20b").strip()


def get_config() -> dict:
    key = get_active_api_key()
    masked = f"{key[:6]}...{key[-4:]}" if len(key) > 10 else ("***" if key else "")
    return {
        "configured": bool(key),
        "masked_api_key": masked,
        "model": get_active_model(),
    }


def update_config(api_key: Optional[str] = None, model: Optional[str] = None) -> dict:
    global _client, _client_key
    if api_key is not None and api_key.strip() and "..." not in api_key:
        clean_key = api_key.strip()
        config.GROQ_API_KEY = clean_key
        os.environ["GROQ_API_KEY"] = clean_key
        _client = None
        _client_key = None
    if model is not None and model.strip():
        clean_model = model.strip()
        config.GROQ_MODEL = clean_model
        os.environ["GROQ_MODEL"] = clean_model
    _persist_config()
    return get_config()


def verify_credentials() -> dict:
    key = get_active_api_key()
    if not key:
        return {
            "ok": False,
            "configured": False,
            "model": get_active_model(),
            "error": "Groq API Key is not configured. Enter it in Settings on the frontend.",
        }
    try:
        client = _get_client()
        models_page = client.models.list()
        count = len(getattr(models_page, "data", []) or [])
        return {
            "ok": True,
            "configured": True,
            "model": get_active_model(),
            "available_models": count,
        }
    except Exception as exc:
        return {
            "ok": False,
            "configured": True,
            "model": get_active_model(),
            "error": str(exc),
        }


_load_persisted_config()


def _get_client() -> Groq:
    """Lazily initialize Groq client using active UI-saved or environment key."""
    global _client, _client_key
    api_key = get_active_api_key()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured. Enter your Groq API Key in Settings on the frontend.")
    if _client is None or _client_key != api_key:
        _client = Groq(api_key=api_key)
        _client_key = api_key
    return _client

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Language display names for LLM instruction
_LANGUAGE_NAMES = {
    "en-US": "English",
    "en-IN": "English (Indian)",
    "hi-IN": "Hindi (हिंदी)",
    "kn-IN": "Kannada (ಕನ್ನಡ)",
}


def get_chat_response(
    user_message: str,
    rag_context: str = "",
    contact_memory: dict = None,
    conversation_history: list = None,
    previous_calls: list = None,
    script_content: str = None,
    language: str = "en-US",
    agent_name: str = "Alex",
) -> str:
    """
    Generate a conversational reply for an ongoing phone call or simulator session.
    Maintains persistent memory of past calls with this contact, and conversational
    context across current call turns.

    Parameters
    ----------
    user_message : str
        The latest utterance from the contact.
    rag_context : str
        Relevant document excerpts retrieved via RAG (may be empty).
    contact_memory : dict
        Persistent memory for this contact (last_topic, interest_level, concerns, commitments).
    conversation_history : list
        Recent turns in this current call (list of {'role': 'user'|'agent', 'text': '...'}).
    previous_calls : list
        Summaries and outcomes from previous recorded calls with this contact.

    Returns
    -------
    str
        The agent's reply (1–2 sentences).
    """
    if contact_memory is None:
        contact_memory = {}

    lang_name = _LANGUAGE_NAMES.get(language or "en-US", "English")
    if language in ("kn-IN", "kn"):
        lang_instruction = (
            " MANDATORY SCRIPT REQUIREMENT FOR KANNADA: You MUST write your entire response exclusively in the native Kannada script (ಕನ್ನಡ ಲಿಪಿ), "
            "such as 'ಖಂಡಿತ, ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?'. NEVER use the English/Latin alphabet or Roman transliteration (do NOT write words like 'Namaskara' or 'Neevu'). "
            "Every single word must be in genuine Kannada characters so the speech synthesizer reads it with authentic native accent."
        )
    elif language in ("hi-IN", "hi"):
        lang_instruction = (
            " MANDATORY SCRIPT REQUIREMENT FOR HINDI: You MUST write your entire response exclusively in the native Devanagari script (देवनागरी लिपि), "
            "such as 'नमस्ते, मैं आपकी क्या सहायता कर सकता हूँ?'. NEVER use the English/Latin alphabet or Roman transliteration (do NOT write words like 'Namaste' or 'Aap'). "
            "Every single word must be in genuine Devanagari characters so the speech synthesizer reads it with authentic native accent."
        )
    elif language and language not in ("en-US", "en-IN", ""):
        lang_instruction = f" Always respond in {lang_name}. Use natural, spoken {lang_name} suitable for a phone call."
    else:
        lang_instruction = ""

    persona = (agent_name or "Alex").strip() or "Alex"
    system_parts = [
        f"You are {persona}, a polite, calm, natural-sounding human representative on a live telephone call. "
        "Never say or imply that you are an AI, a robot, an assistant, or a language model. "
        "Speak normally and naturally like a real person on the phone—friendly and clear, never robotic, dramatic, or over-excited. "
        "Use standard punctuation cleanly: use '?' for genuine questions, '.' for normal statements, commas ',' for natural pauses, and at most an occasional '!' for a polite greeting. "
        "Avoid semicolons, slashes, emojis, hyphenated numbers (never write '2-minute' or '20-minute'—write 'two minute' or 'twenty minute'), or exaggerated sales hype. "
        "Write all times, dates, and numbers in plain spelled-out spoken words (for example 'one in the afternoon' instead of '1 p.m.' and 'twenty minutes' instead of '20-minute') so the voice synthesizer pronounces every word clearly. "
        f"Keep your response to 1 short, crisp spoken sentence (under 22 words whenever possible) so it sounds natural and responsive over the phone.{lang_instruction}",
    ]

    # Active call script & live caller status/context (highest operational priority)
    if script_content and script_content.strip():
        # Strip explicit placeholder tokens from the script before injecting (prevents TTS reading [Name], XYZ etc.)
        import re as _re
        clean_script = _re.sub(r'\[[^\]]{1,40}\]', '', script_content)
        clean_script = _re.sub(r'<[^>]{1,40}>', '', clean_script)
        clean_script = _re.sub(r'\{[^}]{1,40}\}', '', clean_script)
        clean_script = _re.sub(r'\b(?:[Xx][Yy][Zz]|[Xx]{3,}|[Aa][Bb][Cc]\s+Company)\b', '', clean_script)
        clean_script = _re.sub(r'\s{2,}', ' ', clean_script).strip()
        system_parts.append(
            "\nMANDATORY CALL SCRIPT & CALLER CONTEXT — You MUST follow the context, caller's previous position/status, and script steps below on every turn. "
            "Check the conversation history so you advance cleanly without repeating finished steps, and prioritize these instructions over generic defaults. "
            "CRITICAL: Your reply must contain ONLY natural spoken words. Never output template placeholders like [Name], [Company], XYZ, ABC, <Bracket>, or {variable}. "
            "If you need a name and don't have it, use the contact's real name from memory or say 'you' instead:\n"
            f"{clean_script}"
        )

    if rag_context:
        system_parts.append(
            f"\nRelevant information from our knowledge base:\n{rag_context}"
        )

    memory_lines = []
    if contact_memory.get("name"):
        memory_lines.append(f"Contact name: {contact_memory['name']}")
    if contact_memory.get("last_topic"):
        memory_lines.append(f"Last topic discussed: {contact_memory['last_topic']}")
    if contact_memory.get("interest_level"):
        memory_lines.append(f"Interest level: {contact_memory['interest_level']}")
    if contact_memory.get("concerns"):
        memory_lines.append(f"Known concerns: {contact_memory['concerns']}")
    if contact_memory.get("commitments"):
        memory_lines.append(f"Previous commitments: {contact_memory['commitments']}")

    if memory_lines:
        system_parts.append("\nContact memory:\n" + "\n".join(memory_lines))

    # Cross-call persistent context
    if previous_calls and len(previous_calls) > 0:
        prev_lines = []
        for pc in previous_calls[-3:]:
            date_str = f"[{pc.get('date')}] " if pc.get('date') else ""
            summary = pc.get('summary') or pc.get('last_topic') or 'General conversation'
            outcome = f" (Outcome: {pc.get('outcome')})" if pc.get('outcome') else ""
            prev_lines.append(f"- {date_str}{summary}{outcome}")
        if prev_lines:
            system_parts.append(
                "\nPrevious Call History with this caller:\n" + "\n".join(prev_lines) +
                "\nSeamlessly maintain context from these past calls. Reference previous topics naturally when appropriate."
            )

    system_prompt = "\n".join(system_parts)

    messages = [{"role": "system", "content": system_prompt}]

    # In-call conversation context
    if conversation_history:
        for turn in conversation_history[-8:]:
            r = turn.get("role")
            txt = turn.get("text") or turn.get("content") or ""
            if not txt:
                continue
            if r in ["user", "caller"]:
                messages.append({"role": "user", "content": txt})
            elif r in ["agent", "assistant"]:
                messages.append({"role": "assistant", "content": txt})

    # Ensure the latest user utterance is present as final user message
    if not messages or messages[-1].get("role") != "user" or messages[-1].get("content") != user_message:
        messages.append({"role": "user", "content": user_message})

    # Call Groq with automatic model fallback so tool_use_failed / <|channel|> quirks on non-English never 500
    import re as _re_clean
    candidate_models = []
    for _m in (get_active_model(), "llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
        if _m and _m not in candidate_models:
            candidate_models.append(_m)

    last_err = None
    for idx_m, model_name in enumerate(candidate_models):
        try:
            completion = _get_client().chat.completions.create(
                model=model_name,
                messages=messages,
            )
            raw_out = (completion.choices[0].message.content or "").strip()
            raw_out = _re_clean.sub(r"<\|[^|>]+?\|>", "", raw_out).strip()
            if raw_out:
                return raw_out
        except Exception as exc:
            last_err = exc
            err_str = str(exc)
            print(f"[LLM get_chat_response Note] Model {model_name} failed: {err_str[:180]}")
            # If this is the last fallback, rescue clean text from failed_generation if present
            if idx_m == len(candidate_models) - 1:
                m_fg = _re_clean.search(r'"arguments"\s*:\s*([^}]+)\}', err_str)
                if m_fg:
                    rescued = m_fg.group(1).strip().strip('"').strip("'").strip()
                    if len(rescued) > 4:
                        return rescued
    raise last_err


def _sanitize_greeting(text: str) -> Optional[str]:
    """
    Strip placeholder tokens that TTS would read literally
    (e.g. [Name], [Company], XYZ, ABC, <Contact>, {variable})
    while preserving legitimate words/acronyms like AI, US, CRM, PM.
    """
    import re
    if not text:
        return None
    cleaned = re.sub(r'\[[^\]]{1,40}\]', '', text)
    cleaned = re.sub(r'<[^>]{1,40}>', '', cleaned)
    cleaned = re.sub(r'\{[^}]{1,40}\}', '', cleaned)
    cleaned = re.sub(
        r'\b(?:[Xx][Yy][Zz]|x\.y\.z\.|[Xx]{3,}|ABC\s*(?:Corp|Company|Inc)?|ACME|PLACEHOLDER|TBD)\b',
        '',
        cleaned,
    )
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    cleaned = re.sub(r'\s+([.,?!])', r'\1', cleaned).strip().strip(',').strip()
    if len(cleaned.split()) < 4:
        return None
    return cleaned


def generate_context_greeting(
    persona_name: str = "Alex",
    contact_name: str = "there",
    script_content: str = "",
    language: str = "en-US",
    mode: str = "outbound",
) -> Optional[str]:
    """Generate a single concise opening greeting tailored to the script/caller status context."""
    if not script_content or not script_content.strip():
        return None
    lang_name = _LANGUAGE_NAMES.get(language or "en-US", "English")
    extra_lang = f" Respond strictly in {lang_name} using native script if Hindi/Kannada." if language not in ("en-US", "en-IN", "") else ""
    prompt = (
        f"You are {persona_name} starting a live {mode} phone call with {contact_name}. "
        f"Write ONLY the very first opening line (1 short, normal polite spoken sentence under 24 words following the call script/context below).{extra_lang}\n"
        "CRITICAL: Use ONLY real words. Never output placeholder tokens like [Name], [Company], XYZ, ABC, "
        "<Contact>, or any bracketed / ALL-CAPS template variable. Use the contact's actual name if known.\n\n"
        f"Context/Script:\n{script_content.strip()}"
    )
    try:
        completion = _get_client().chat.completions.create(
            model=get_active_model(),
            messages=[{"role": "system", "content": prompt}],
            timeout=5.0,
        )
        raw = (completion.choices[0].message.content or "").strip().strip('"').strip("'")
        out = _sanitize_greeting(raw)
        return out if out else None
    except Exception:
        return None


def analyze_call(transcript: str, contact_name: str = "Contact") -> dict:
    """
    Analyse a completed call transcript and return structured insights.

    Parameters
    ----------
    transcript : str
        The full call transcript text.
    contact_name : str
        The name of the contact for context.

    Returns
    -------
    dict
        Keys: lead_score, lead_score_reasoning, sentiment, outcome,
              summary, last_topic, interest_level, concerns, commitments.
    """
    _safe_defaults = {
        "lead_score": 50,
        "lead_score_reasoning": "Unable to determine",
        "sentiment": "Neutral",
        "outcome": "Needs Follow-up",
        "summary": "Call analysis unavailable",
        "last_topic": "",
        "interest_level": "Unknown",
        "concerns": "",
        "commitments": "",
    }

    if not transcript or not transcript.strip():
        transcript = f"Agent: Hello, this is Alex from Vocalyx. User called or was connected with contact {contact_name}."

    prompt = f"""You are an expert sales call analyser. Analyse the following call transcript for contact "{contact_name}" and return ONLY a JSON object with these exact keys:

- lead_score: integer 0-100 (likelihood of conversion)
- lead_score_reasoning: brief explanation of the score
- sentiment: one of "Positive", "Neutral", "Negative"
- outcome: one of "Interested", "Not Interested", "Requested Callback", "Time-Waster", "Needs Follow-up"
- summary: 2-3 sentence summary of the call
- last_topic: the main topic discussed
- interest_level: one of "High", "Medium", "Low", "Unknown"
- concerns: any objections or concerns raised by the contact (empty string if none)
- commitments: any commitments made by either party (empty string if none)

Return ONLY the JSON object, no markdown, no explanation.

Transcript:
{transcript}"""

    import re

    models_to_try = [get_active_model(), "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    # De-duplicate while preserving order
    seen = set()
    candidate_models = [m for m in models_to_try if m and not (m in seen or seen.add(m))]

    last_err = None
    for model_name in candidate_models:
        try:
            completion = _get_client().chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "user", "content": prompt},
                ],
            )
            raw = completion.choices[0].message.content.strip()

            # Clean JSON extraction via regex (matches first '{' through last '}')
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
            else:
                cleaned = raw.strip()
                if cleaned.startswith("```"):
                    parts = cleaned.split("```")
                    if len(parts) >= 2:
                        cleaned = parts[1]
                        if cleaned.startswith("json"):
                            cleaned = cleaned[4:]
                result = json.loads(cleaned)

            # Ensure lead_score is integer
            try:
                result["lead_score"] = int(result.get("lead_score", 50))
            except Exception:
                result["lead_score"] = 50

            # Validate / fill missing keys with safe defaults
            for key, default in _safe_defaults.items():
                if key not in result or result[key] is None:
                    result[key] = default

            print(f"[LLM analyze_call] ✓ Call analysis success ({model_name}) for '{contact_name}': score={result['lead_score']}, sentiment={result['sentiment']}")
            return result

        except Exception as exc:
            last_err = exc
            print(f"[LLM analyze_call Warning] Model {model_name} failed: {exc}")
            continue

    print(f"[LLM ERROR] analyze_call exhausted all models. Last error: {last_err}")
    return _safe_defaults.copy()
