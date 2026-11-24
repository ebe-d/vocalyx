"""
Unified Message Alerts Service for Vocalyx:
Supports Telegram Bot, Twilio SMS, and Twilio WhatsApp post-call notifications.
Settings are persisted to disk so configurations survive server restarts.
"""
import os
import re
import json
import requests
from typing import Dict, Any, Tuple, Optional

_BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
ALERTS_SETTINGS_FILE = os.path.join(_BASE_DIR, "alerts_settings.json")

try:
    from backend import config, twilio_service
except ImportError:
    try:
        import config, twilio_service
    except ImportError:
        config = None
        twilio_service = None

# Default alert configuration
_alerts_config = {
    "telegram": {
        "enabled": True,
        "bot_token": getattr(config, "TELEGRAM_BOT_TOKEN", "") or "",
        "chat_id": getattr(config, "TELEGRAM_CHAT_ID", "") or "",
    },
    "sms": {
        "enabled": getattr(config, "SMS_ENABLED", False) if config else False,
        "to_phone": getattr(config, "SMS_TO_PHONE", "") if config else "",
    },
    "whatsapp": {
        "enabled": getattr(config, "WHATSAPP_ENABLED", True) if config else True,
        "to_phone": getattr(config, "WHATSAPP_TO_PHONE", "") if config else "",
        "from_phone": getattr(config, "WHATSAPP_FROM_PHONE", "whatsapp:+14155238886") if config else "whatsapp:+14155238886",
    },
}


def _load_persisted_config():
    global _alerts_config
    candidates = [
        ALERTS_SETTINGS_FILE,
        "alerts_settings.json",
        os.path.join(os.getcwd(), "alerts_settings.json"),
        os.path.join(os.getcwd(), "backend", "alerts_settings.json"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            try:
                with open(c, "r") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        for section in ["telegram", "sms", "whatsapp"]:
                            if section in data and isinstance(data[section], dict):
                                _alerts_config[section].update(data[section])
                        # Sync back to config module if set
                        if config:
                            if _alerts_config["telegram"].get("bot_token"):
                                config.TELEGRAM_BOT_TOKEN = _alerts_config["telegram"]["bot_token"]
                            if _alerts_config["telegram"].get("chat_id"):
                                config.TELEGRAM_CHAT_ID = _alerts_config["telegram"]["chat_id"]
                            if not _alerts_config["whatsapp"].get("to_phone") and getattr(config, "WHATSAPP_TO_PHONE", None):
                                _alerts_config["whatsapp"]["to_phone"] = getattr(config, "WHATSAPP_TO_PHONE")
                                _alerts_config["whatsapp"]["enabled"] = True
                        print(f"[Alerts Config] Loaded persisted alerts configuration from {c}")
                        return
            except Exception as e:
                print(f"[Alerts Config] Error loading {c}: {e}")


def _persist_config():
    candidates = [
        ALERTS_SETTINGS_FILE,
        "alerts_settings.json",
    ]
    for dest in candidates:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
            with open(dest, "w") as f:
                json.dump(_alerts_config, f, indent=2)
        except Exception as e:
            print(f"[Alerts Config Save Note]: {e}")


_load_persisted_config()


def get_config() -> Dict[str, Any]:
    """Returns current configuration and live connection readiness for each channel."""
    tw_ready = False
    tw_phone = ""
    if twilio_service and hasattr(twilio_service, "is_configured"):
        tw_ready = twilio_service.is_configured()
    if config:
        tw_phone = getattr(config, "TWILIO_PHONE_NUMBER", "") or ""

    tg = _alerts_config.get("telegram", {})
    sms = _alerts_config.get("sms", {})
    wa = _alerts_config.get("whatsapp", {})

    tg_ready = bool(tg.get("bot_token") and tg.get("chat_id"))

    return {
        "twilio_configured": tw_ready,
        "twilio_phone_number": tw_phone,
        "telegram": {
            "enabled": bool(tg.get("enabled", True)),
            "bot_token": tg.get("bot_token", ""),
            "chat_id": tg.get("chat_id", ""),
            "ready": tg_ready,
        },
        "sms": {
            "enabled": bool(sms.get("enabled", False)),
            "to_phone": sms.get("to_phone", ""),
            "from_phone": tw_phone,
            "twilio_ready": tw_ready,
            "ready": tw_ready and bool(sms.get("to_phone")),
        },
        "whatsapp": {
            "enabled": bool(wa.get("enabled", False)),
            "to_phone": wa.get("to_phone", ""),
            "from_phone": wa.get("from_phone", "whatsapp:+14155238886"),
            "twilio_ready": tw_ready,
            "ready": tw_ready and bool(wa.get("to_phone")),
        },
    }


def update_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """Update and persist alert configurations."""
    global _alerts_config
    if "telegram" in data and isinstance(data["telegram"], dict):
        _alerts_config["telegram"].update(data["telegram"])
        if config:
            if "bot_token" in data["telegram"]:
                config.TELEGRAM_BOT_TOKEN = data["telegram"]["bot_token"]
            if "chat_id" in data["telegram"]:
                config.TELEGRAM_CHAT_ID = data["telegram"]["chat_id"]

    if "sms" in data and isinstance(data["sms"], dict):
        _alerts_config["sms"].update(data["sms"])

    if "whatsapp" in data and isinstance(data["whatsapp"], dict):
        _alerts_config["whatsapp"].update(data["whatsapp"])

    _persist_config()
    return get_config()


def format_alert_message(
    contact_name: str = "Unknown",
    lead_score: int = 50,
    sentiment: str = "Neutral",
    outcome: str = "Needs Follow-up",
    summary: str = "",
    reasoning: str = "",
    markdown: bool = True,
) -> str:
    """Format standardized post-call alert message."""
    if markdown:
        msg = (
            "🔔 *Vocalyx Call Alert*\n\n"
            f"👤 *Contact:* {contact_name}\n"
            f"📊 *Lead Score:* {lead_score}/100\n"
            f"😊 *Sentiment:* {sentiment}\n"
            f"🎯 *Outcome:* {outcome}\n"
            f"📝 *Summary:* {summary}"
        )
        if reasoning:
            msg += f"\n💡 *Reasoning:* {reasoning}"
        return msg
    else:
        # Plain text for SMS
        msg = (
            f"Vocalyx Alert: Call with {contact_name} finished. "
            f"Score: {lead_score}/100 | {sentiment} | {outcome}. "
            f"Summary: {summary}"
        )
        return msg[:1590]  # Respect SMS limits


def send_telegram(text: str, bot_token: Optional[str] = None, chat_id: Optional[str] = None) -> Tuple[bool, str]:
    """Send alert via Telegram Bot API."""
    token = bot_token or _alerts_config["telegram"].get("bot_token") or getattr(config, "TELEGRAM_BOT_TOKEN", "")
    cid = chat_id or _alerts_config["telegram"].get("chat_id") or getattr(config, "TELEGRAM_CHAT_ID", "")

    if not token or not cid:
        return False, "Telegram Bot Token or Chat ID not configured."

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": cid,
        "text": text,
        "parse_mode": "Markdown",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True, "Telegram alert sent successfully."
        else:
            return False, f"Telegram API error {resp.status_code}: {resp.text}"
    except Exception as exc:
        return False, f"Telegram connection error: {exc}"


def send_sms(text: str, to_phone: Optional[str] = None) -> Tuple[bool, str]:
    """Send alert via Twilio SMS."""
    if not twilio_service or not twilio_service.is_configured():
        return False, "Twilio is not configured. Please enter Account SID and Auth Token in Settings."

    target = to_phone or _alerts_config["sms"].get("to_phone")
    if not target:
        return False, "No SMS recipient phone number configured."

    client = twilio_service.get_client()
    if not client:
        return False, "Failed to initialize Twilio client."

    from_phone = getattr(config, "TWILIO_PHONE_NUMBER", None)
    if not from_phone:
        return False, "Twilio phone number is not configured."

    try:
        clean_to = twilio_service.format_phone_number(target)
        # Strip markdown bold asterisks for clean SMS reading
        plain_text = text.replace("*", "")
        message = client.messages.create(
            body=plain_text,
            from_=from_phone,
            to=clean_to,
        )
        return True, f"SMS alert sent (SID: {message.sid})"
    except Exception as exc:
        return False, f"Twilio SMS error: {exc}"


def send_whatsapp(text: str, to_phone: Optional[str] = None, from_phone: Optional[str] = None) -> Tuple[bool, str]:
    """Send alert via Twilio WhatsApp API."""
    if not twilio_service or not twilio_service.is_configured():
        return False, "Twilio is not configured. Please enter Account SID and Auth Token in Settings."

    target = to_phone or _alerts_config["whatsapp"].get("to_phone")
    if not target:
        return False, "No WhatsApp recipient phone number configured."

    sender = from_phone or _alerts_config["whatsapp"].get("from_phone") or "whatsapp:+14155238886"

    client = twilio_service.get_client()
    if not client:
        return False, "Failed to initialize Twilio client."

    try:
        # Standardize target WhatsApp address (strip spaces, hyphens, punctuation)
        raw_to = target.strip()
        is_wa_to = raw_to.lower().startswith("whatsapp:")
        num_to = raw_to[9:] if is_wa_to else raw_to
        digits_to = re.sub(r"[^\d+]", "", num_to.strip())
        if not digits_to.startswith("+"):
            digits_to = "+" + digits_to
        clean_to = f"whatsapp:{digits_to}"

        # Standardize sender address
        raw_from = sender.strip()
        is_wa_from = raw_from.lower().startswith("whatsapp:")
        num_from = raw_from[9:] if is_wa_from else raw_from
        digits_from = re.sub(r"[^\d+]", "", num_from.strip())
        if not digits_from.startswith("+"):
            digits_from = "+" + digits_from
        clean_from = f"whatsapp:{digits_from}"

        # WhatsApp supports Markdown formatting (*bold*, etc.) natively
        message = client.messages.create(
            body=text,
            from_=clean_from,
            to=clean_to,
        )
        return True, f"WhatsApp alert sent (SID: {message.sid})"
    except Exception as exc:
        return False, f"Twilio WhatsApp error: {exc}"


def send_all_alerts_detailed(
    contact_name: str = "Unknown",
    lead_score: int = 50,
    sentiment: str = "Neutral",
    outcome: str = "Needs Follow-up",
    summary: str = "",
    reasoning: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """
    Broadcast post-call alert across all enabled channels (Telegram, SMS, WhatsApp)
    and return per-channel outcome details.
    """
    _load_persisted_config()
    msg_md = format_alert_message(
        contact_name=contact_name,
        lead_score=lead_score,
        sentiment=sentiment,
        outcome=outcome,
        summary=summary,
        reasoning=reasoning,
        markdown=True,
    )
    msg_plain = format_alert_message(
        contact_name=contact_name,
        lead_score=lead_score,
        sentiment=sentiment,
        outcome=outcome,
        summary=summary,
        reasoning=reasoning,
        markdown=False,
    )

    results = {
        "sent_any": False,
        "telegram": {"enabled": bool(_alerts_config["telegram"].get("enabled", True)), "ok": False, "message": "Disabled"},
        "sms": {"enabled": bool(_alerts_config["sms"].get("enabled", False)), "ok": False, "message": "Disabled"},
        "whatsapp": {"enabled": bool(_alerts_config["whatsapp"].get("enabled", False)), "ok": False, "message": "Disabled"},
    }

    # 1. Telegram
    if results["telegram"]["enabled"]:
        ok, res = send_telegram(msg_md)
        results["telegram"]["ok"] = ok
        results["telegram"]["message"] = res
        if ok:
            results["sent_any"] = True
            print(f"[Alerts] ✓ Telegram delivered for {contact_name}")
        else:
            print(f"[Alerts Note] Telegram: {res}")

    # 2. SMS (Twilio)
    if results["sms"]["enabled"]:
        ok, res = send_sms(msg_plain)
        results["sms"]["ok"] = ok
        results["sms"]["message"] = res
        if ok:
            results["sent_any"] = True
            print(f"[Alerts] ✓ Twilio SMS delivered for {contact_name}")
        else:
            print(f"[Alerts Note] Twilio SMS: {res}")

    # 3. WhatsApp (Twilio)
    if results["whatsapp"]["enabled"]:
        ok, res = send_whatsapp(msg_md)
        results["whatsapp"]["ok"] = ok
        results["whatsapp"]["message"] = res
        if ok:
            results["sent_any"] = True
            print(f"[Alerts] ✓ Twilio WhatsApp delivered for {contact_name} ({res})")
        else:
            print(f"[Alerts Note] Twilio WhatsApp error: {res}")

    return results


def send_all_alerts(
    contact_name: str = "Unknown",
    lead_score: int = 50,
    sentiment: str = "Neutral",
    outcome: str = "Needs Follow-up",
    summary: str = "",
    reasoning: str = "",
    **kwargs,
) -> bool:
    """
    Broadcast post-call alert across all enabled channels (Telegram, SMS, WhatsApp).
    Guarantees non-blocking, exception-safe delivery.
    """
    res = send_all_alerts_detailed(
        contact_name=contact_name,
        lead_score=lead_score,
        sentiment=sentiment,
        outcome=outcome,
        summary=summary,
        reasoning=reasoning,
        **kwargs,
    )
    return res.get("sent_any", False)
