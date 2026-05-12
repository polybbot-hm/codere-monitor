import logging
from sqlalchemy.orm import Session

from db.models import Match
from db.repository import OddsRepository, AlertRepository
from scrapers.base import OddsMarket
from notifier import telegram

logger = logging.getLogger(__name__)

# Umbral de cambio de cuota para notificar (en valor absoluto)
ODDS_CHANGE_THRESHOLD = 0.10


async def analyze_markets(
    session: Session,
    match: Match,
    markets: list[OddsMarket],
):
    """
    Para cada mercado de faltas recibido:
      1. Si es nuevo → notifica "nuevo mercado disponible" + guarda snapshot
      2. Si ya existe → compara cuota con último snapshot
         - Si cambió más de THRESHOLD → notifica cambio
      3. Siempre guarda snapshot nuevo
    """
    odds_repo = OddsRepository(session)
    alert_repo = AlertRepository(session)

    for market in markets:
        is_new_market = not odds_repo.market_has_been_seen(match.id, market.market_name)

        if is_new_market and not alert_repo.already_sent(match.id, market.market_name, "new_market"):
            logger.info(
                f"Nuevo mercado detectado: {market.market_name} "
                f"[{match.home_team} vs {match.away_team}]"
            )
            msg = telegram.build_new_market_message(
                home=match.home_team,
                away=match.away_team,
                match_date=match.match_date,
                market_name=market.market_name,
                outcomes=market.outcomes,
                bookmaker=market.bookmaker,
            )
            await telegram.send_message(msg)
            alert_repo.mark_sent(match.id, market.market_name, "new_market")

        else:
            # Mercado ya conocido → buscar cambios de cuota
            for outcome in market.outcomes:
                prev = odds_repo.get_latest_snapshot(
                    match.id, market.market_name, outcome["name"]
                )
                if prev and abs(outcome["odds"] - prev.odds_value) >= ODDS_CHANGE_THRESHOLD:
                    logger.info(
                        f"Cambio de cuota: {market.market_name} {outcome['name']} "
                        f"{prev.odds_value} → {outcome['odds']}"
                    )
                    msg = telegram.build_odds_change_message(
                        home=match.home_team,
                        away=match.away_team,
                        market_name=market.market_name,
                        outcome_name=outcome["name"],
                        old_odds=prev.odds_value,
                        new_odds=outcome["odds"],
                        bookmaker=market.bookmaker,
                    )
                    await telegram.send_message(msg)

        # Guardar snapshot nuevo siempre
        for outcome in market.outcomes:
            odds_repo.save_snapshot(
                match_id=match.id,
                bookmaker=market.bookmaker,
                market_name=market.market_name,
                outcome=outcome["name"],
                odds_value=outcome["odds"],
                game_id=market.game_id,
            )

    session.commit()
