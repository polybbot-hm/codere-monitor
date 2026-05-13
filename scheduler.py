import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import sessionmaker, Session

from db.models import init_db
from db.repository import MatchRepository, OddsRepository
from scrapers import SCRAPERS
from analyzer.odds_analyzer import analyze_markets
import config

logger = logging.getLogger(__name__)


async def job_fetch_matches(SessionLocal: sessionmaker):
    """Cada 5 min: busca partidos de LaLiga en las próximas 24h y los registra en BD."""
    logger.info("▶ JOB: fetch_matches")

    for scraper_name, scraper in SCRAPERS.items():
        try:
            matches_info = await scraper.get_laliga_matches()
        except Exception as e:
            logger.error(f"fetch_matches [{scraper_name}] falló: {e}")
            continue

        with SessionLocal() as session:
            repo = MatchRepository(session)
            for m in matches_info:
                repo.upsert_match(
                    external_id=m.external_id,
                    bookmaker=m.bookmaker,
                    home=m.home_team,
                    away=m.away_team,
                    match_date=m.match_date,
                    competition=m.competition,
                )
            repo.deactivate_old_matches()
            session.commit()
        logger.info(f"fetch_matches [{scraper_name}]: {len(matches_info)} partidos procesados")


async def job_poll_odds(SessionLocal: sessionmaker):
    """Cada 2 min: para cada partido activo, consulta mercados de faltas."""
    logger.info("▶ JOB: poll_odds")

    with SessionLocal() as session:
        repo = MatchRepository(session)
        active_matches = repo.get_active_matches()

    if not active_matches:
        logger.info("poll_odds: sin partidos activos ahora mismo")
        return

    logger.info(f"poll_odds: consultando {len(active_matches)} partidos")

    for match in active_matches:
        scraper = SCRAPERS.get(match.bookmaker)
        if scraper is None:
            logger.warning(f"poll_odds: sin scraper para bookmaker '{match.bookmaker}', saltando")
            continue

        from scrapers.base import MatchInfo
        match_info = MatchInfo(
            external_id=match.external_id,
            home_team=match.home_team,
            away_team=match.away_team,
            match_date=match.match_date,
            bookmaker=match.bookmaker,
        )
        try:
            markets = await scraper.get_fouls_markets(match_info)
        except Exception as e:
            logger.error(f"Error obteniendo cuotas para {match}: {e}")
            continue

        if markets:
            with SessionLocal() as session:
                # Re-query el match dentro de la nueva sesión
                from db.models import Match
                db_match = session.get(Match, match.id)
                await analyze_markets(session, db_match, markets)


async def job_cleanup(SessionLocal: sessionmaker):
    """Cada 24h: limpia snapshots de más de 7 días."""
    logger.info("▶ JOB: cleanup")
    with SessionLocal() as session:
        OddsRepository(session).cleanup_old_snapshots(days=7)
        session.commit()


def start_scheduler(database_url: str):
    engine = init_db(database_url)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        job_fetch_matches,
        "interval",
        seconds=config.FETCH_MATCHES_INTERVAL,
        args=[SessionLocal],
        id="fetch_matches",
        next_run_time=__import__("datetime").datetime.now(),   # ejecuta al arrancar
    )
    scheduler.add_job(
        job_poll_odds,
        "interval",
        seconds=config.POLL_ODDS_INTERVAL,
        args=[SessionLocal],
        id="poll_odds",
        next_run_time=__import__("datetime").datetime.now(),
    )
    scheduler.add_job(
        job_cleanup,
        "interval",
        seconds=config.CLEANUP_INTERVAL,
        args=[SessionLocal],
        id="cleanup",
    )

    return scheduler
