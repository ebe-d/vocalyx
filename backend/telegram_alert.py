"""
Telegram and Multi-Channel alert integration for Vocalyx post-call notifications.
Maintains 100% backward compatibility while delegating to unified alerts_service.
"""
import requests

try:
    from backend import alerts_service
except ImportError:
    try:
        import alerts_service
    except ImportError:
        alerts_service = None

import os
from backend import config


def send_alert(
    contact_name: str = "Unknown",
    lead_score: int = 50,
    sentiment: str = "Neutral",
    outcome: str = "Needs Follow-up",
    summary: str = "",
    reasoning: str = "",
    **kwargs,
) -> bool:
    """
    Broadcast post-call notification across all configured channels (Telegram, SMS, WhatsApp).
    Falls back to direct Telegram API request if alerts_service is unavailable.
    """
    if alerts_service and hasattr(alerts_service, "send_all_alerts"):
        return alerts_service.send_all_alerts(
            contact_name=contact_name,
            lead_score=lead_score,
            sentiment=sentiment,
            outcome=outcome,
            summary=summary,
            reasoning=reasoning,
            **kwargs,
        )

    # Standalone Telegram fallback
    bot_token = (getattr(config, "TELEGRAM_BOT_TOKEN", "") or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    chat_id = (getattr(config, "TELEGRAM_CHAT_ID", "") or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
    if not bot_token or not chat_id:
        return False

    message = (
        "🔔 *Vocalyx Call Alert*\n\n"
        f"👤 *Contact:* {contact_name}\n"
        f"📊 *Lead Score:* {lead_score}/100\n"
        f"😊 *Sentiment:* {sentiment}\n"
        f"🎯 *Outcome:* {outcome}\n"
        f"📝 *Summary:* {summary}"
    )
    if reasoning:
        message += f"\n💡 *Reasoning:* {reasoning}"

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception:
        return False


# Compatibility alias
send_lead_alert = send_alert


def send_all_alerts_detailed(*args, **kwargs):
    if alerts_service and hasattr(alerts_service, "send_all_alerts_detailed"):
        return alerts_service.send_all_alerts_detailed(*args, **kwargs)
    return {"sent_any": False}
