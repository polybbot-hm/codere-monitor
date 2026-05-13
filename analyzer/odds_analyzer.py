import hashlib
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

import config
from db.models import Match
from db.repository import OddsRepository, AlertRepository
from scrapers.base import OddsMarket
from notifier import telegram

logger = logging.getLogger(__name__)

ODDS_CHANGE_THRESHOLD = 0.10
DISAPPEARANCE_THRESHOLD = config.DISAPPEARANCE_THRESHOLD
DISAPPEARANCE_RATE_LIMIT_MINUTES = config.DISAPPEARANCE_RATE_LIMIT_MINUTES

# Contador en memoria: (match_id, market_name, outcome) → polls consecutivos sin verlo
_miss_counter: dict[tuple, int] = {}


async def analyze_markets(
    session: Session,
    match: Match,
    markets: list[OddsMarket],
):
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
            # limpia contadores en memoria para este mercado (por si desapareció y volvió)
            for key in list(_miss_counter.keys()):
                if key[0] == match.id and key[1] == market.market_name:
                    del _miss_counter[key]

        else:
            # Mercado ya conocido → buscar cambios de cuota (comparación directa)
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

        # Diff simétrico: detecta cambio de línea y desaparición de outcomes
        if not is_new_market:
            prev_outcomes = odds_repo.get_latest_market_outcomes(match.id, market.market_name)
            curr_outcomes = {o["name"] for o in market.outcomes}

            if prev_outcomes:
                disappeared = prev_outcomes - curr_outcomes
                appeared    = curr_outcomes - prev_outcomes

                if disappeared and appeared:
                    # Línea/total reemplazado por una línea diferente
                    pair_key   = f"{sorted(disappeared)}→{sorted(appeared)}"
                    h          = hashlib.sha256(pair_key.encode()).hexdigest()[:8]
                    alert_type = f"LINE_CHANGE:{h}"
                    if not alert_repo.already_sent(match.id, market.market_name, alert_type):
                        logger.info(
                            f"Cambio de línea: {market.market_name} "
                            f"{sorted(disappeared)} → {sorted(appeared)}"
                        )
                        msg = telegram.build_line_change_message(
                            home=match.home_team,
                            away=match.away_team,
                            market_name=market.market_name,
                            disappeared=disappeared,
                            appeared=appeared,
                            bookmaker=market.bookmaker,
                        )
                        await telegram.send_message(msg)
                        alert_repo.mark_sent(
                            match.id, market.market_name, alert_type,
                            outcome_detail=pair_key,
                        )

                elif disappeared:
                    # Outcomes presentes antes que ya no aparecen
                    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
                    for d in disappeared:
                        key = (match.id, market.market_name, d)
                        _miss_counter[key] = _miss_counter.get(key, 0) + 1
                        if _miss_counter[key] >= DISAPPEARANCE_THRESHOLD:
                            h          = hashlib.sha256(d.encode()).hexdigest()[:8]
                            alert_type = f"MARKET_DISAPPEARANCE:{h}"
                            last       = alert_repo.last_sent_at(
                                match.id, market.market_name, alert_type
                            )
                            rate_ok = last is None or (
                                (now_naive - last)
                                >= timedelta(minutes=DISAPPEARANCE_RATE_LIMIT_MINUTES)
                            )
                            if rate_ok:
                                logger.info(
                                    f"Outcome desaparecido: {market.market_name} '{d}'"
                                )
                                msg = telegram.build_market_disappearance_message(
                                    home=match.home_team,
                                    away=match.away_team,
                                    market_name=market.market_name,
                                    outcome_name=d,
                                    bookmaker=market.bookmaker,
                                )
                                await telegram.send_message(msg)
                                alert_repo.mark_disappearance_sent(
                                    match.id, market.market_name, alert_type,
                                    outcome_detail=d,
                                )

                # Resetea contadores para outcomes que sí están presentes
                for o in curr_outcomes:
                    _miss_counter.pop((match.id, market.market_name, o), None)

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
