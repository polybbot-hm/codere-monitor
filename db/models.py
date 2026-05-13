from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean,
    ForeignKey, UniqueConstraint, create_engine, inspect, text
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timezone

Base = declarative_base()


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String, nullable=False)       # ID de Codere
    bookmaker = Column(String, nullable=False, default="codere")
    home_team = Column(String, nullable=False)
    away_team = Column(String, nullable=False)
    match_date = Column(DateTime(timezone=True), nullable=False)
    competition = Column(String, default="LaLiga")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    snapshots = relationship("OddsSnapshot", back_populates="match", cascade="all, delete-orphan")
    alerts = relationship("AlertSent", back_populates="match", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("external_id", "bookmaker", name="uq_match_bookmaker"),
    )

    def __repr__(self):
        return f"<Match {self.home_team} vs {self.away_team} ({self.match_date})>"


class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    bookmaker = Column(String, nullable=False, default="codere")
    market_name = Column(String, nullable=False)        # ej: "Total Faltas Más/Menos"
    outcome = Column(String, nullable=False)            # ej: "Más 22.5"
    odds_value = Column(Float, nullable=False)
    game_id = Column(String, nullable=True)             # GameId de Codere
    captured_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    match = relationship("Match", back_populates="snapshots")

    def __repr__(self):
        return f"<OddsSnapshot {self.market_name} {self.outcome}={self.odds_value}>"


class AlertSent(Base):
    __tablename__ = "alerts_sent"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    market_name = Column(String, nullable=False)
    alert_type = Column(String, nullable=False)         # "new_market" | "odds_change" | "LINE_CHANGE:{hash}" | "MARKET_DISAPPEARANCE:{hash}"
    outcome_detail = Column(String, nullable=True)      # par de líneas (LINE_CHANGE) o outcome (MARKET_DISAPPEARANCE)
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    match = relationship("Match", back_populates="alerts")

    __table_args__ = (
        # Solo una alerta de tipo "new_market" por partido+mercado
        UniqueConstraint("match_id", "market_name", "alert_type", name="uq_alert"),
    )


def init_db(database_url: str):
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    _migrate(engine)
    return engine


def _migrate(engine):
    inspector = inspect(engine)
    existing = {col["name"] for col in inspector.get_columns("alerts_sent")}
    with engine.connect() as conn:
        if "outcome_detail" not in existing:
            conn.execute(text("ALTER TABLE alerts_sent ADD COLUMN outcome_detail VARCHAR"))
            conn.commit()
