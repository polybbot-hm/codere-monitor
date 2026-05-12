import logging
import httpx
from datetime import datetime, timezone
import config

logger = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}"


def _format_odds_line(outcome: dict) -> str:
    name = outcome["name"]
    odds = outcome["odds"]
    return f"  {name} → `{odds:.2f}`"


def build_new_market_message(
    home: str,
    away: str,
    match_date: datetime,
    market_name: str,
    outcomes: list[dict],
    bookmaker: str,
) -> str:
    """Formatea el mensaje cuando aparece un mercado de faltas nuevo."""
    match_date_local = match_date.strftime("%d/%m/%Y %H:%M")
    outcomes_text = "\n".join(_format_odds_line(o) for o in outcomes)
    bookmaker_display = bookmaker.upper()

    return (
        f"⚽ *NUEVO MERCADO DE FALTAS DISPONIBLE*\n\n"
        f"*{home} vs {away}*\n"
        f"📅 {match_date_local}h\n\n"
        f"📊 *{market_name}*\n"
        f"{outcomes_text}\n\n"
        f"🏠 Casa: {bookmaker_display}\n"
        f"⏰ Detectado: {datetime.now(timezone.utc).strftime('%H:%M')} UTC"
    )


def build_odds_change_message(
    home: str,
    away: str,
    market_name: str,
    outcome_name: str,
    old_odds: float,
    new_odds: float,
    bookmaker: str,
) -> str:
    """Formatea el mensaje cuando cambia una cuota."""
    direction = "📈" if new_odds > old_odds else "📉"
    change = new_odds - old_odds
    sign = "+" if change > 0 else ""
    bookmaker_display = bookmaker.upper()

    return (
        f"{direction} *CAMBIO DE CUOTA — FALTAS*\n\n"
        f"*{home} vs {away}*\n\n"
        f"📊 *{market_name}*\n"
        f"  {outcome_name}\n"
        f"  {old_odds:.2f} → `{new_odds:.2f}` ({sign}{change:.2f})\n\n"
        f"🏠 Casa: {bookmaker_display}\n"
        f"⏰ {datetime.now(timezone.utc).strftime('%H:%M')} UTC"
    )


async def send_message(text: str):
    """Envía un mensaje a tu Telegram personal."""
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info("Notificación Telegram enviada OK")
        except Exception as e:
            logger.error(f"Error enviando mensaje Telegram: {e}")
