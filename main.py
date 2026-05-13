import asyncio
import logging
import signal
import sys

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from scheduler import start_scheduler
from scrapers import SCRAPERS
from notifier.telegram import build_cuotas_snapshot_message
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def handler_cuotas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para el comando /cuotas — scrape en vivo de todos los scrapers registrados."""
    await update.message.reply_text("🔍 Consultando cuotas...")

    results = []

    for scraper_name, scraper in SCRAPERS.items():
        entry: dict = {"scraper_name": scraper_name, "matches": [], "error": None}
        try:
            matches = await scraper.get_laliga_matches()
            for match in matches:
                try:
                    markets = await scraper.get_fouls_markets(match)
                except Exception as e:
                    logger.error(f"[{scraper_name}] Error obteniendo mercados para {match.home_team} vs {match.away_team}: {e}")
                    markets = []
                entry["matches"].append({
                    "home": match.home_team,
                    "away": match.away_team,
                    "markets": markets,
                })
        except Exception as e:
            logger.error(f"[{scraper_name}] Error en handler_cuotas: {e}")
            entry["error"] = str(e)

        results.append(entry)

    message = build_cuotas_snapshot_message(results)

    # Telegram tiene límite de 4096 chars por mensaje — partir si es necesario
    chunk_size = 4096
    for i in range(0, len(message), chunk_size):
        await update.message.reply_text(
            message[i : i + chunk_size],
            parse_mode="Markdown",
        )


async def main():
    logger.info("🚀 Codere Monitor arrancando...")
    logger.info(f"  Polling partidos: cada {config.FETCH_MATCHES_INTERVAL}s")
    logger.info(f"  Polling cuotas:   cada {config.POLL_ODDS_INTERVAL}s")
    logger.info(f"  Ventana:          próximas {config.HOURS_AHEAD}h")

    # Mantener el proceso vivo
    stop_event = asyncio.Event()

    def _shutdown(*_):
        logger.info("🛑 Señal de parada recibida, cerrando...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    # Configurar bot de Telegram
    app = Application.builder().token(config.TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("cuotas", handler_cuotas))

    async with app:
        await app.start()
        await app.updater.start_polling()
        logger.info("✅ Bot Telegram activo. Comando /cuotas disponible.")

        scheduler = start_scheduler(config.DATABASE_URL)
        scheduler.start()
        logger.info("✅ Scheduler activo. Esperando eventos...")

        await stop_event.wait()

        scheduler.shutdown(wait=False)
        await app.updater.stop()
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
