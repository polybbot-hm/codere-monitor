import httpx
import asyncio
import random
import logging
from datetime import datetime, timezone, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential

from scrapers.base import BookmakerScraper, MatchInfo, OddsMarket
import config

logger = logging.getLogger(__name__)

HEADERS = {
    "Host": "m.apuestas.codere.es",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://m.apuestas.codere.es/",
}

# categoryInfoId=151 → Tarjetas/Faltas
# categoryInfoId=150 → Córners (por si se quiere ampliar)
FOUL_CATEGORY_ID = 151


class CodereScaper(BookmakerScraper):

    @property
    def name(self) -> str:
        return "codere"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=15))
    async def _get(self, client: httpx.AsyncClient, url: str, params: dict = None) -> dict | list:
        """Request con reintentos automáticos."""
        jitter = random.uniform(config.REQUEST_JITTER_MIN, config.REQUEST_JITTER_MAX)
        await asyncio.sleep(jitter)
        response = await client.get(url, params=params, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return response.json()

    async def get_laliga_matches(self) -> list[MatchInfo]:
        """
        Llama a GetEvents con el parentId de LaLiga y devuelve partidos
        de las próximas 24h.
        """
        url = f"{config.CODERE_BASE_URL}/NavigationService/Event/GetEvents"
        params = {
            "parentId": config.CODERE_LALIGA_PARENT_ID,
            "gameTypes": "1;18",
        }

        matches = []
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=config.HOURS_AHEAD)

        async with httpx.AsyncClient() as client:
            try:
                data = await self._get(client, url, params)
            except Exception as e:
                logger.error(f"[Codere] Error obteniendo partidos LaLiga: {e}")
                return []

            events = data if isinstance(data, list) else data.get("Events", [])

            for event in events:
                try:
                    # La fecha puede venir en distintos campos según el endpoint
                    date_str = event.get("StartDate") or event.get("EventDate") or ""
                    if not date_str:
                        continue

                    # Codere devuelve fechas en formato ISO o timestamp ms
                    match_date = self._parse_date(date_str)
                    if not match_date or not (now < match_date <= cutoff):
                        continue

                    event_id = str(event.get("EventId") or event.get("Id") or event.get("NodeId") or "")
                    if not event_id:
                        continue

                    home = event.get("HomeTeamName") or event.get("HomeTeam") or ""
                    away = event.get("AwayTeamName") or event.get("AwayTeam") or ""

                    # A veces viene como "HomeTeam vs AwayTeam" en un solo campo
                    if not home and not away:
                        name = event.get("Name", "")
                        if " - " in name:
                            home, away = name.split(" - ", 1)
                        elif " vs " in name.lower():
                            home, away = name.split(" vs ", 1)

                    matches.append(MatchInfo(
                        external_id=event_id,
                        home_team=home.strip(),
                        away_team=away.strip(),
                        match_date=match_date,
                        bookmaker=self.name,
                    ))

                except Exception as e:
                    logger.warning(f"[Codere] Error parseando evento: {e} | raw={event}")
                    continue

        logger.info(f"[Codere] {len(matches)} partidos LaLiga encontrados (próximas {config.HOURS_AHEAD}h)")
        return matches

    async def get_fouls_markets(self, match: MatchInfo) -> list[OddsMarket]:
        """
        Consulta el endpoint GetGamesNoLiveByCategoryInfo con categoryInfoId=151
        (Tarjetas/Faltas) para el partido dado.
        """
        url = (
            f"{config.CODERE_BASE_URL}/NavigationService/Game"
            f"/GetGamesNoLiveByCategoryInfo"
        )
        params = {
            "parentid": match.external_id,
            "categoryInfoId": FOUL_CATEGORY_ID,
        }

        markets = []

        async with httpx.AsyncClient() as client:
            try:
                data = await self._get(client, url, params)
            except Exception as e:
                logger.error(f"[Codere] Error obteniendo mercados partido {match.external_id}: {e}")
                return []

            games = data if isinstance(data, list) else []

            for game in games:
                try:
                    game_id = str(game.get("GameId", ""))
                    market_name = game.get("Name", "")
                    results = game.get("Results", [])

                    if not results:
                        continue

                    outcomes = [
                        {
                            "name": r.get("Name", ""),
                            "odds": float(r.get("Odd", 0)),
                            "result_id": str(r.get("ResultId", "")),
                        }
                        for r in results
                        if r.get("Odd") and float(r.get("Odd", 0)) > 1.0
                    ]

                    if not outcomes:
                        continue

                    markets.append(OddsMarket(
                        game_id=game_id,
                        market_name=market_name,
                        category="faltas",
                        outcomes=outcomes,
                        bookmaker=self.name,
                    ))

                except Exception as e:
                    logger.warning(f"[Codere] Error parseando mercado: {e}")
                    continue

        logger.info(
            f"[Codere] {len(markets)} mercados de faltas para "
            f"{match.home_team} vs {match.away_team}"
        )
        return markets

    def _parse_date(self, date_str: str) -> datetime | None:
        """Parsea distintos formatos de fecha que usa Codere."""
        try:
            # Timestamp en milisegundos: /Date(1234567890000+0200)/
            if "/Date(" in date_str:
                ts_ms = int(date_str.split("(")[1].split(")")[0].split("+")[0].split("-")[0])
                return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)

            # ISO 8601
            for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue

            return None
        except Exception:
            return None
