from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timezone, timedelta
from db.models import Match, OddsSnapshot, AlertSent
import logging

logger = logging.getLogger(__name__)


class MatchRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert_match(self, external_id: str, bookmaker: str, home: str, away: str,
                     match_date: datetime, competition: str = "LaLiga") -> Match:
        match = self.session.query(Match).filter_by(
            external_id=external_id, bookmaker=bookmaker
        ).first()

        if not match:
            match = Match(
                external_id=external_id,
                bookmaker=bookmaker,
                home_team=home,
                away_team=away,
                match_date=match_date,
                competition=competition,
            )
            self.session.add(match)
            self.session.flush()
            logger.info(f"Nuevo partido registrado: {home} vs {away}")
        return match

    def get_active_matches(self) -> list[Match]:
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=24)
        return (
            self.session.query(Match)
            .filter(Match.is_active == True)
            .filter(Match.match_date > now)
            .filter(Match.match_date <= cutoff)
            .all()
        )

    def deactivate_old_matches(self):
        now = datetime.now(timezone.utc)
        self.session.query(Match).filter(Match.match_date < now).update(
            {"is_active": False}
        )


class OddsRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_snapshot(self, match_id: int, bookmaker: str, market_name: str,
                      outcome: str, odds_value: float, game_id: str = None):
        snap = OddsSnapshot(
            match_id=match_id,
            bookmaker=bookmaker,
            market_name=market_name,
            outcome=outcome,
            odds_value=odds_value,
            game_id=game_id,
        )
        self.session.add(snap)

    def get_latest_snapshot(self, match_id: int, market_name: str,
                            outcome: str) -> OddsSnapshot | None:
        return (
            self.session.query(OddsSnapshot)
            .filter_by(match_id=match_id, market_name=market_name, outcome=outcome)
            .order_by(OddsSnapshot.captured_at.desc())
            .first()
        )

    def market_has_been_seen(self, match_id: int, market_name: str) -> bool:
        return (
            self.session.query(OddsSnapshot)
            .filter_by(match_id=match_id, market_name=market_name)
            .count() > 0
        )

    def cleanup_old_snapshots(self, days: int = 7):
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        deleted = (
            self.session.query(OddsSnapshot)
            .filter(OddsSnapshot.captured_at < cutoff)
            .delete()
        )
        logger.info(f"Limpieza: {deleted} snapshots eliminados")


class AlertRepository:
    def __init__(self, session: Session):
        self.session = session

    def already_sent(self, match_id: int, market_name: str, alert_type: str) -> bool:
        return (
            self.session.query(AlertSent)
            .filter_by(match_id=match_id, market_name=market_name, alert_type=alert_type)
            .count() > 0
        )

    def mark_sent(self, match_id: int, market_name: str, alert_type: str):
        alert = AlertSent(
            match_id=match_id,
            market_name=market_name,
            alert_type=alert_type,
        )
        self.session.add(alert)
