"""
Script de prueba: simula cambios de cuota y de línea para verificar
que las notificaciones de Telegram llegan correctamente.

Uso:
    python test_notifications.py

Qué hace:
  1. Crea un partido de prueba en la DB (o reutiliza uno existente)
  2. Inserta snapshots "anteriores" con cuotas/líneas distintas
  3. Llama al analyzer con cuotas/líneas nuevas → dispara las alertas
  4. Limpia los datos de prueba al terminar
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import sessionmaker

from db.models import init_db, Match, OddsSnapshot, AlertSent
from db.repository import MatchRepository, OddsRepository, AlertRepository
from analyzer.odds_analyzer import analyze_markets
from scrapers.base import OddsMarket
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
logger = logging.getLogger(__name__)

FAKE_MATCH_EXTERNAL_ID = "TEST_MATCH_001"
FAKE_BOOKMAKER = "codere"


def setup_db():
    engine = init_db(config.DATABASE_URL)
    return sessionmaker(bind=engine, expire_on_commit=False)


def create_fake_match(session) -> Match:
    """Crea o reutiliza el partido de prueba."""
    repo = MatchRepository(session)
    match_date = datetime.now(timezone.utc) + timedelta(hours=2)
    match = repo.upsert_match(
        external_id=FAKE_MATCH_EXTERNAL_ID,
        bookmaker=FAKE_BOOKMAKER,
        home="Equipo Local TEST",
        away="Equipo Visitante TEST",
        match_date=match_date,
        competition="LaLiga",
    )
    session.commit()
    logger.info(f"Partido de prueba: id={match.id}")
    return match


def insert_old_snapshots(session, match: Match, scenario: str):
    """Inserta snapshots 'anteriores' que el analyzer va a comparar."""
    odds_repo = OddsRepository(session)

    if scenario == "cambio_cuota":
        # Cuotas actuales → el analyzer recibirá cuotas distintas → CAMBIO DE CUOTA
        odds_repo.save_snapshot(match.id, FAKE_BOOKMAKER, "Total de Faltas Cometidas Más/Menos",
                                "Más de 24.5", 1.85)
        odds_repo.save_snapshot(match.id, FAKE_BOOKMAKER, "Total de Faltas Cometidas Más/Menos",
                                "Menos de 24.5", 1.85)

    elif scenario == "cambio_linea":
        # Línea anterior → el analyzer recibirá una línea diferente → CAMBIO DE LÍNEA
        odds_repo.save_snapshot(match.id, FAKE_BOOKMAKER, "Total de Faltas Cometidas Más/Menos",
                                "Más de 22.5", 1.90)
        odds_repo.save_snapshot(match.id, FAKE_BOOKMAKER, "Total de Faltas Cometidas Más/Menos",
                                "Menos de 22.5", 1.80)

    session.commit()
    logger.info(f"Snapshots anteriores insertados para escenario: {scenario}")


def build_fake_markets(scenario: str) -> list[OddsMarket]:
    """Construye los mercados 'actuales' que recibe el analyzer."""

    if scenario == "cambio_cuota":
        # Misma línea (24.5) pero cuotas distintas → CAMBIO DE CUOTA
        return [OddsMarket(
            game_id="test_game_1",
            market_name="Total de Faltas Cometidas Más/Menos",
            category="faltas",
            outcomes=[
                {"name": "Más de 24.5",   "odds": 2.10},  # era 1.85 → sube
                {"name": "Menos de 24.5", "odds": 1.65},  # era 1.85 → baja
            ],
            bookmaker=FAKE_BOOKMAKER,
        )]

    elif scenario == "cambio_linea":
        # Línea nueva (25.5 en vez de 22.5) → CAMBIO DE LÍNEA
        return [OddsMarket(
            game_id="test_game_1",
            market_name="Total de Faltas Cometidas Más/Menos",
            category="faltas",
            outcomes=[
                {"name": "Más de 25.5",   "odds": 1.88},
                {"name": "Menos de 25.5", "odds": 1.82},
            ],
            bookmaker=FAKE_BOOKMAKER,
        )]

    return []


def cleanup(session, match: Match):
    """Elimina todos los datos de prueba de la DB."""
    session.query(AlertSent).filter_by(match_id=match.id).delete()
    session.query(OddsSnapshot).filter_by(match_id=match.id).delete()
    session.query(Match).filter_by(id=match.id).delete()
    session.commit()
    logger.info("Datos de prueba eliminados.")


async def run_scenario(SessionLocal, scenario: str):
    logger.info(f"\n{'='*50}")
    logger.info(f"ESCENARIO: {scenario.upper().replace('_', ' ')}")
    logger.info(f"{'='*50}")

    with SessionLocal() as session:
        match = create_fake_match(session)

    with SessionLocal() as session:
        db_match = session.get(Match, match.id)
        insert_old_snapshots(session, db_match, scenario)

    markets = build_fake_markets(scenario)

    with SessionLocal() as session:
        db_match = session.get(Match, match.id)
        await analyze_markets(session, db_match, markets)
        logger.info("✅ Analyzer ejecutado — revisá Telegram")

    # Espera para que llegue la notificación antes de limpiar
    await asyncio.sleep(3)

    with SessionLocal() as session:
        db_match = session.get(Match, match.id)
        cleanup(session, db_match)


async def main():
    SessionLocal = setup_db()

    print("\n¿Qué escenario querés probar?")
    print("  1 — Cambio de cuota (misma línea, odds distintas)")
    print("  2 — Cambio de línea (línea diferente)")
    print("  3 — Ambos")
    choice = input("\nOpción (1/2/3): ").strip()

    scenarios = []
    if choice == "1":
        scenarios = ["cambio_cuota"]
    elif choice == "2":
        scenarios = ["cambio_linea"]
    elif choice == "3":
        scenarios = ["cambio_cuota", "cambio_linea"]
    else:
        print("Opción inválida.")
        return

    for scenario in scenarios:
        await run_scenario(SessionLocal, scenario)
        if len(scenarios) > 1:
            await asyncio.sleep(2)

    print("\n✅ Prueba completada. Revisá Telegram.")


if __name__ == "__main__":
    asyncio.run(main())
