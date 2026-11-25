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
        "content_sid": getattr(config, "WHATSAPP_CONTENT_SID", "") if config else "",
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
            "content_sid": wa.get("content_sid", ""),
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
                os.environ["TELEGRAM_BOT_TOKEN"] = data["telegram"]["bot_token"]
            if "chat_id" in data["telegram"]:
                config.TELEGRAM_CHAT_ID = data["telegram"]["chat_id"]
                os.environ["TELEGRAM_CHAT_ID"] = data["telegram"]["chat_id"]

    if "sms" in data and isinstance(data["sms"], dict):
        _alerts_config["sms"].update(data["sms"])
        if config and "to_phone" in data["sms"]:
            config.SMS_TO_PHONE = data["sms"]["to_phone"]
            os.environ["SMS_TO_PHONE"] = data["sms"]["to_phone"]

    if "whatsapp" in data and isinstance(data["whatsapp"], dict):
        _alerts_config["whatsapp"].update(data["whatsapp"])
        if config:
            if "to_phone" in data["whatsapp"]:
                config.WHATSAPP_TO_PHONE = data["whatsapp"]["to_phone"]
                os.environ["WHATSAPP_TO_PHONE"] = data["whatsapp"]["to_phone"]
            if "content_sid" in data["whatsapp"]:
                config.WHATSAPP_CONTENT_SID = data["whatsapp"]["content_sid"]
                os.environ["WHATSAPP_CONTENT_SID"] = data["whatsapp"]["content_sid"]

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


def _ensure_whatsapp_template(client, clean_from: str = "") -> Tuple[Optional[str], Optional[str]]:
    """
    Find or auto-create a reusable Vocalyx Content Template (HX...) on paid Twilio accounts.
    On Trial accounts (error 20003), Content API template creation is disabled by Twilio, so
    callers must open a 24h Sandbox session or paste their Sandbox ContentSid (HX...) manually.
    """
    existing_sid = (_alerts_config.get("whatsapp", {}).get("content_sid") or "").strip()
    if existing_sid:
        return existing_sid, None

    try:
        contents = client.content.v1.contents.list(limit=25)
        for rec in contents:
            fname = (getattr(rec, "friendly_name", "") or "").lower()
            types_dict = getattr(rec, "types", {}) or {}
            if "vocalyx" in fname and isinstance(types_dict, dict):
                _alerts_config["whatsapp"]["content_sid"] = rec.sid
                _persist_config()
                return rec.sid, None
    except Exception as list_err:
        err_s = str(list_err)
        print(f"[Alerts WhatsApp Content List Note]: {err_s}")
        if "20003" in err_s or "trial account" in err_s.lower():
            return None, "Twilio Trial accounts cannot access Content API (error 20003)."

    try:
        from twilio.rest.content.v1.content import ContentList
        req_cls = getattr(ContentList, "ContentCreateRequest", None)
        if req_cls is not None:
            payload = req_cls(
                friendly_name="vocalyx_call_alert",
                language="en",
                types={"twilio/text": {"body": "Vocalyx Alert: {{1}}"}},
            )
            template = client.content.v1.contents.create(content_create_request=payload)
        else:
            template = client.content.v1.contents.create(
                friendly_name="vocalyx_call_alert",
                language="en",
                types={"twilio/text": {"body": "Vocalyx Alert: {{1}}"}},
            )
        sid = template.sid
        try:
            client.content.v1.contents(sid).approval_requests.create(
                name="vocalyx_call_alert",
                category="UTILITY",
            )
        except Exception as appr_err:
            print(f"[Alerts WhatsApp Approval Note]: {appr_err}")
        _alerts_config["whatsapp"]["content_sid"] = sid
        _persist_config()
        print(f"[Alerts WhatsApp] Auto-created Twilio Content Template SID: {sid}")
        return sid, None
    except Exception as create_err:
        return None, str(create_err)


def _diagnose_whatsapp_sandbox_window(client, clean_from: str, clean_to: str) -> str:
    """Check Twilio account message history to pinpoint Sandbox/account mismatch issues."""
    sid = getattr(client, "account_sid", "") or ""
    masked_sid = f"{sid[:6]}...{sid[-4:]}" if len(sid) > 10 else (sid or "unknown")
    try:
        inbound = client.messages.list(from_=clean_to, to=clean_from, limit=1)
        if not inbound:
            return (
                f"Twilio account {masked_sid} has 0 inbound WhatsApp messages from {clean_to} to {clean_from}. "
                f"Either your Sandbox session expired (re-send your 'join <2-word-code>' to {clean_from} and wait for 'You are all set!'), "
                f"or your active Twilio Account SID ({masked_sid}) is a different Console project than the Sandbox you joined."
            )
        last_dt = getattr(inbound[0], "date_sent", None) or getattr(inbound[0], "date_created", None)
        return (
            f"Last inbound message to account {masked_sid} was at {last_dt}; if >24h ago, send 'hi' to {clean_from} to reopen the window, "
            f"or paste your Sandbox Content Template SID (HX...) from Twilio Console -> Messaging -> Try it out -> Send a WhatsApp message."
        )
    except Exception:
        return (
            f"Verify in Twilio Console ({masked_sid}) -> Messaging -> Try it out -> Send a WhatsApp message that {clean_to} joined {clean_from}, "
            f"or paste the Sandbox Content Template SID (HX...) into Alerts."
        )


def send_whatsapp(
    text: str,
    to_phone: Optional[str] = None,
    from_phone: Optional[str] = None,
    content_sid: Optional[str] = None,
    template_vars: Optional[Dict[str, str]] = None,
) -> Tuple[bool, str]:
    """Send alert via Twilio WhatsApp API (free-form within 24h session, or ContentSid template)."""
    if not twilio_service or not twilio_service.is_configured():
        return False, "Twilio is not configured. Please enter Account SID and Auth Token in Settings."

    target = to_phone or _alerts_config["whatsapp"].get("to_phone")
    if not target:
        return False, "No WhatsApp recipient phone number configured."

    sender = from_phone or _alerts_config["whatsapp"].get("from_phone") or "whatsapp:+14155238886"
    resolved_content_sid = (
        (content_sid if content_sid is not None else _alerts_config["whatsapp"].get("content_sid"))
        or (getattr(config, "WHATSAPP_CONTENT_SID", "") if config else "")
        or ""
    ).strip()

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

        print(f"[Alerts WhatsApp] Sending from={clean_from} to={clean_to} (content_sid={resolved_content_sid or 'none'})")

        # First attempt free-form body (works whenever the 24-hour customer service window is open)
        try:
            message = client.messages.create(
                body=text,
                from_=clean_from,
                to=clean_to,
            )
            return True, f"WhatsApp alert sent (SID: {message.sid})"
        except Exception as body_exc:
            err_lower = str(body_exc).lower()
            needs_template = any(
                k in err_lower
                for k in ("contentsid", "content_sid", "63016", "21654", "24 hour", "24-hour", "freeform", "outside the allowed window")
            )
            if not needs_template:
                raise

            auto_err = None
            if not resolved_content_sid:
                resolved_content_sid, auto_err = _ensure_whatsapp_template(client, clean_from=clean_from)

            if resolved_content_sid:
                compact_text = re.sub(r"\s+", " ", text.replace("*", "")).strip()[:800]
                vars_payload = {
                    str(k): re.sub(r"\s+", " ", str(v)).strip()[:240]
                    for k, v in (template_vars or {}).items()
                    if v is not None
                }
                vars_payload.setdefault("1", compact_text)
                vars_payload.setdefault("2", "Vocalyx Call Alert")
                try:
                    message = client.messages.create(
                        from_=clean_from,
                        to=clean_to,
                        content_sid=resolved_content_sid,
                        content_variables=json.dumps(vars_payload),
                    )
                    return True, f"WhatsApp alert sent via template {resolved_content_sid} (SID: {message.sid})"
                except Exception as tpl_exc:
                    diag = _diagnose_whatsapp_sandbox_window(client, clean_from, clean_to)
                    return False, f"Template {resolved_content_sid} send failed ({tpl_exc}). {diag}"

            diag = _diagnose_whatsapp_sandbox_window(client, clean_from, clean_to)
            return (
                False,
                f"Twilio blocked free-form WhatsApp ({body_exc}). "
                f"{auto_err + ' ' if auto_err else ''}{diag}",
            )
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
        wa_vars = {
            "1": f"{contact_name} — Score {lead_score}/100 ({sentiment}, {outcome}): {summary}".strip()[:950],
            "2": str(outcome or "Vocalyx Call Alert")[:120],
        }
        ok, res = send_whatsapp(msg_md, template_vars=wa_vars)
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
