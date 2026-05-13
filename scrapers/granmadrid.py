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
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.casinogranmadridonline.es/",
}

ALTENAR_BASE_URL = "https://sb2frontend-altenar2.biahosted.com/api/widget"
ALTENAR_PARAMS_BASE = {
    "culture": "es-ES",
    "timezoneOffset": "-120",
    "integration": "casinogranmadrid",
    "deviceType": "1",
    "numFormat": "en-GB",
    "countryCode": "ES",
}

GRANMADRID_SESSION_URL = "https://www.casinogranmadridonline.es/apuestas-deportivas"
GRANMADRID_LALIGA_CHAMP_ID = "2941"

# Mercados que nos interesan (EXCLUSIVAMENTE estos 3)
TARGET_MARKET_TYPE_IDS = {15740, 15732, 15733}

# odd.typeId: 12 = over ("Más de"), 13 = under ("Menos de")
ODD_TYPE_OVER = 12
ODD_TYPE_UNDER = 13


class GranMadridScraper(BookmakerScraper):

    @property
    def name(self) -> str:
        return "granmadrid"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=15))
    async def _get(self, client: httpx.AsyncClient, url: str, params: dict = None) -> dict | list:
        """Request con reintentos automáticos."""
        jitter = random.uniform(config.REQUEST_JITTER_MIN, config.REQUEST_JITTER_MAX)
        await asyncio.sleep(jitter)
        response = await client.get(url, params=params, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return response.json()

    async def _init_session(self, client: httpx.AsyncClient) -> None:
        """
        Hace un GET a la página principal de apuestas para inicializar
        las cookies de sesión que requiere la API Altenar.
        """
        try:
            await client.get(GRANMADRID_SESSION_URL, headers=HEADERS, timeout=15)
            logger.info("[GranMadrid] Sesión inicializada")
        except Exception as e:
            logger.warning(f"[GranMadrid] No se pudo inicializar sesión: {e}")

    async def get_laliga_matches(self) -> list[MatchInfo]:
        """
        Llama a GetChampionshipEvents con el champId de LaLiga
        y devuelve partidos de las próximas HOURS_AHEAD horas.
        """
        url = f"{ALTENAR_BASE_URL}/GetChampionshipEvents"
        params = {
            **ALTENAR_PARAMS_BASE,
            "champIds": GRANMADRID_LALIGA_CHAMP_ID,
            "group": "1",
        }

        matches = []
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=config.HOURS_AHEAD)

        async with httpx.AsyncClient(follow_redirects=True) as client:
            await self._init_session(client)

            try:
                data = await self._get(client, url, params)
            except Exception as e:
                logger.error(f"[GranMadrid] Error obteniendo partidos LaLiga: {e}")
                return []

            # La respuesta puede venir en distintas claves según la versión de la API
            events = (
                data.get("events")
                or data.get("items")
                or data.get("Events")
                or data.get("Items")
                or []
            )
            if isinstance(data, list):
                events = data

            for event in events:
                try:
                    date_str = event.get("startDate") or event.get("StartDate") or ""
                    if not date_str:
                        continue

                    match_date = self._parse_date(date_str)
                    if not match_date or not (now < match_date <= cutoff):
                        continue

                    event_id = str(event.get("id") or event.get("Id") or "")
                    if not event_id:
                        continue

                    competitors = event.get("competitors") or event.get("Competitors") or []
                    if len(competitors) >= 2:
                        home = competitors[0].get("name") or competitors[0].get("Name") or ""
                        away = competitors[1].get("name") or competitors[1].get("Name") or ""
                    else:
                        # Fallback: intentar parsear el campo name
                        name = event.get("name") or event.get("Name") or ""
                        if " vs. " in name:
                            home, away = name.split(" vs. ", 1)
                        elif " vs " in name.lower():
                            home, away = name.split(" vs ", 1)
                        else:
                            home, away = name, ""

                    matches.append(MatchInfo(
                        external_id=event_id,
                        home_team=home.strip(),
                        away_team=away.strip(),
                        match_date=match_date,
                        bookmaker=self.name,
                    ))

                except Exception as e:
                    logger.warning(f"[GranMadrid] Error parseando evento: {e} | raw={event}")
                    continue

        logger.info(f"[GranMadrid] {len(matches)} partidos LaLiga encontrados (próximas {config.HOURS_AHEAD}h)")
        return matches

    async def get_fouls_markets(self, match: MatchInfo) -> list[OddsMarket]:
        """
        Consulta GetEventDetails para el evento dado y extrae
        únicamente los mercados de faltas (typeIds 15740, 15732, 15733).
        """
        url = f"{ALTENAR_BASE_URL}/GetEventDetails"
        params = {
            **ALTENAR_PARAMS_BASE,
            "eventId": match.external_id,
            "showNonBoosts": "false",
        }

        markets = []

        async with httpx.AsyncClient(follow_redirects=True) as client:
            await self._init_session(client)

            try:
                data = await self._get(client, url, params)
            except Exception as e:
                logger.error(
                    f"[GranMadrid] Error obteniendo mercados para {match.external_id}: {e}"
                )
                return []

            # Construir índice de odds por id para lookup O(1)
            raw_odds = data.get("odds") or data.get("Odds") or []
            odds_by_id: dict[int, dict] = {odd["id"]: odd for odd in raw_odds if "id" in odd}

            raw_markets = data.get("markets") or data.get("Markets") or []

            for market in raw_markets:
                try:
                    type_id = market.get("typeId") or market.get("TypeId")
                    if type_id not in TARGET_MARKET_TYPE_IDS:
                        continue

                    market_id = str(market.get("id") or market.get("Id") or "")
                    market_name = market.get("name") or market.get("Name") or ""

                    # Iterar desktopOddIds: lista de listas de oddIds
                    desktop_odd_ids = market.get("desktopOddIds") or []
                    outcomes = []

                    for odd_group in desktop_odd_ids:
                        for odd_id in odd_group:
                            odd = odds_by_id.get(odd_id)
                            if odd is None:
                                continue

                            # Solo cuotas activas
                            if odd.get("oddStatus", -1) != 0:
                                continue

                            odd_type_id = odd.get("typeId")
                            if odd_type_id not in (ODD_TYPE_OVER, ODD_TYPE_UNDER):
                                continue

                            price = odd.get("price")
                            if not price or float(price) <= 1.0:
                                continue

                            outcomes.append({
                                "name": odd.get("name") or odd.get("Name") or "",
                                "odds": float(price),
                                "result_id": str(odd_id),
                            })

                    if not outcomes:
                        continue

                    markets.append(OddsMarket(
                        game_id=market_id,
                        market_name=market_name,
                        category="faltas",
                        outcomes=outcomes,
                        bookmaker=self.name,
                    ))

                except Exception as e:
                    logger.warning(f"[GranMadrid] Error parseando mercado: {e}")
                    continue

        logger.info(
            f"[GranMadrid] {len(markets)} mercados de faltas para "
            f"{match.home_team} vs {match.away_team}"
        )
        return markets

    def _parse_date(self, date_str: str) -> datetime | None:
        """Parsea fechas ISO 8601 UTC que devuelve la API Altenar."""
        try:
            for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
            return None
        except Exception:
            return None
