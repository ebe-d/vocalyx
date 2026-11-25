"""
LLM engine using the Groq API (moonshotai/kimi-k2-instruct).
Provides conversational responses and post-call analysis.
"""
import json
import os
from typing import Optional

from groq import Groq

from backend.config import GROQ_API_KEY, GROQ_MODEL

_client = None


def _get_client() -> Groq:
    """Lazily initialize Groq client using active config or environment key."""
    global _client
    api_key = os.getenv("GROQ_API_KEY") or GROQ_API_KEY
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured. Set it in .env or Kaggle Secrets.")
    if _client is None:
        _client = Groq(api_key=api_key)
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
        f"You are {persona}, a calm, articulate, and professional representative on a live telephone conversation. "
        "Never say or imply that you are an AI, a robot, an assistant, or a language model. "
        "Speak in a natural, polite, composed, and formal business tone. "
        "Do not use exclamation marks, hyperactive enthusiasm, sales hype, or casual slang. "
        f"Keep your response to 1 to 2 clear, concise spoken sentences (under 35 words) so it sounds like a poised human speaking over the phone.{lang_instruction}",
    ]

    # Active call script & live caller status/context (highest operational priority)
    if script_content and script_content.strip():
        system_parts.append(
            "\nMANDATORY CALL SCRIPT & CALLER CONTEXT — You MUST follow the context, caller's previous position/status, and script steps below on every turn. "
            "Check the conversation history so you advance cleanly without repeating finished steps, and prioritize these instructions over generic defaults:\n"
            f"{script_content.strip()}"
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

    completion = _get_client().chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
    )
    return completion.choices[0].message.content.strip()


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
        f"Write ONLY the very first opening line (1 short natural sentence, under 24 words) following the call script/context below.{extra_lang}\n\n"
        f"Context/Script:\n{script_content.strip()}"
    )
    try:
        completion = _get_client().chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "system", "content": prompt}],
            timeout=5.0,
        )
        out = (completion.choices[0].message.content or "").strip().strip('"').strip("'")
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

    models_to_try = [GROQ_MODEL, "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
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
