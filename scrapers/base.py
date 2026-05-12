from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class MatchInfo:
    external_id: str
    home_team: str
    away_team: str
    match_date: datetime
    bookmaker: str
    competition: str = "LaLiga"


@dataclass
class OddsMarket:
    game_id: str
    market_name: str
    category: str           # "faltas", "corners", "tarjetas", etc.
    outcomes: list[dict]    # [{"name": "Más 22.5", "odds": 1.85, "result_id": "..."}]
    bookmaker: str


class BookmakerScraper(ABC):
    """
    Clase base para añadir nuevas casas de apuestas.
    Para añadir una nueva casa (ej: bet365):
      1. Crea scrapers/bet365.py
      2. Hereda de BookmakerScraper
      3. Implementa los 3 métodos abstractos
      4. Regístrala en scrapers/__init__.py
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Identificador de la casa: 'codere', 'bet365', etc."""
        ...

    @abstractmethod
    async def get_laliga_matches(self) -> list[MatchInfo]:
        """
        Devuelve los partidos de LaLiga pre-partido disponibles.
        """
        ...

    @abstractmethod
    async def get_fouls_markets(self, match: MatchInfo) -> list[OddsMarket]:
        """
        Dado un partido, devuelve todos los mercados de faltas/tarjetas.
        """
        ...
