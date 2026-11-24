import os


def _load_local_env():
    """Load key=value pairs from an untracked .env file without extra dependencies."""
    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
    for candidate in (
        os.path.join(base_dir, ".env"),
        os.path.join(base_dir, "..", ".env"),
        ".env",
    ):
        if os.path.exists(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    for raw_line in f:
                        line = raw_line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass
            break


_load_local_env()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")  # Free tier on Groq
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
CUDA_DEVICE = os.getenv("CUDA_DEVICE", "cuda")  # Change to "cpu" if no GPU available
UPLOADED_DOCS_DIR = "backend/uploaded_docs"
TTS_OUTPUT_DIR = "backend/tts_output"
DATABASE_URL = "sqlite:///./backend/vocalyx.db"
REFERENCE_AUDIO_PATH = "voice_clone.mp3"

# Twilio Telephony Integration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")
TWILIO_VOICE_ENGINE = os.getenv("TWILIO_VOICE_ENGINE", "f5tts").lower()  # "f5tts", "luxtts", or "polly"
TTS_ENGINE = os.getenv("TTS_ENGINE", "f5tts").lower()

# Multi-Channel Message Alerts
WHATSAPP_TO_PHONE = os.getenv("WHATSAPP_TO_PHONE", "")
WHATSAPP_FROM_PHONE = os.getenv("WHATSAPP_FROM_PHONE", "whatsapp:+14155238886")
WHATSAPP_CONTENT_SID = os.getenv("WHATSAPP_CONTENT_SID", "")
WHATSAPP_ENABLED = os.getenv("WHATSAPP_ENABLED", "true").lower() in ("true", "1", "yes")
SMS_TO_PHONE = os.getenv("SMS_TO_PHONE", "")
SMS_ENABLED = os.getenv("SMS_ENABLED", "false").lower() in ("true", "1", "yes")
