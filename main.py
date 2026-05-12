import asyncio
import logging
import signal
import sys

from scheduler import start_scheduler
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("🚀 Codere Monitor arrancando...")
    logger.info(f"  Polling partidos: cada {config.FETCH_MATCHES_INTERVAL}s")
    logger.info(f"  Polling cuotas:   cada {config.POLL_ODDS_INTERVAL}s")
    logger.info(f"  Ventana:          próximas {config.HOURS_AHEAD}h")

    scheduler = start_scheduler(config.DATABASE_URL)
    scheduler.start()
    logger.info("✅ Scheduler activo. Esperando eventos...")

    # Mantener el proceso vivo
    stop_event = asyncio.Event()

    def _shutdown(*_):
        logger.info("🛑 Señal de parada recibida, cerrando...")
        scheduler.shutdown(wait=False)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    await stop_event.wait()


if __name__ == "__main__":
    asyncio.run(main())
