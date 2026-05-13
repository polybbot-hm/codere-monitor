"""
Script de diagnóstico: lista TODOS los mercados disponibles para partidos
de LaLiga en Codere, probando varios categoryInfoId y todos los partidos.

Uso:
    python debug_markets.py
"""
import asyncio
import httpx
import random
import os
from dotenv import load_dotenv

load_dotenv()

CODERE_BASE_URL = "https://m.apuestas.codere.es"
CODERE_LALIGA_PARENT_ID = "2903511051"

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

CATEGORY_IDS_TO_TRY = [78, 151, 52, 55]  # stats, tarjetas/faltas, especiales, córners


async def get_markets(client, match_id, category_id):
    await asyncio.sleep(random.uniform(3, 7))
    resp = await client.get(
        f"{CODERE_BASE_URL}/NavigationService/Game/GetGamesNoLiveByCategoryInfo",
        params={"parentid": match_id, "categoryInfoId": category_id},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


async def main():
    async with httpx.AsyncClient() as client:
        print("Buscando partidos de LaLiga...\n")
        resp = await client.get(
            f"{CODERE_BASE_URL}/NavigationService/Event/GetEvents",
            params={"parentId": CODERE_LALIGA_PARENT_ID, "gameTypes": "1;18"},
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        events = data if isinstance(data, list) else data.get("Events", [])

        if not events:
            print("No hay partidos disponibles.")
            return

        print(f"Partidos encontrados: {len(events)}")
        for e in events:
            mid = str(e.get("EventId") or e.get("Id") or e.get("NodeId") or "")
            home = e.get("HomeTeamName") or e.get("HomeTeam") or e.get("Name", "?")
            away = e.get("AwayTeamName") or e.get("AwayTeam") or ""
            print(f"  id={mid}  {home} vs {away}")

        print()

        # Probar cada partido con cada category ID hasta encontrar mercados
        found = False
        for event in events:
            match_id = str(event.get("EventId") or event.get("Id") or event.get("NodeId") or "")
            home = event.get("HomeTeamName") or event.get("HomeTeam") or event.get("Name", "?")
            away = event.get("AwayTeamName") or event.get("AwayTeam") or ""

            for cat_id in CATEGORY_IDS_TO_TRY:
                print(f"Probando {home} vs {away} | categoryInfoId={cat_id} ...", end=" ")
                try:
                    games = await get_markets(client, match_id, cat_id)
                except Exception as e:
                    print(f"ERROR: {e}")
                    continue

                if not games:
                    print("sin mercados")
                    continue

                print(f"{len(games)} mercados encontrados!")
                print(f"\n{'='*60}")
                print(f"PARTIDO: {home} vs {away}")
                print(f"categoryInfoId: {cat_id}")
                print(f"{'='*60}\n")

                for i, game in enumerate(games, 1):
                    name = game.get("Name", "(sin nombre)")
                    results = game.get("Results", [])
                    outcomes_preview = ", ".join(
                        f"{r.get('Name','')} @ {r.get('Odd','?')}"
                        for r in results[:4]
                        if r.get("Odd") and float(r.get("Odd", 0)) > 1.0
                    )
                    print(f"[{i:02d}] {name!r}")
                    if outcomes_preview:
                        print(f"      → {outcomes_preview}")

                print(f"\n{'='*60}\n")
                found = True

            if found:
                break

        if not found:
            print("\nNingún partido tiene mercados abiertos en este momento.")
            print("Los mercados de estadísticas suelen abrirse 24-48h antes del partido.")


asyncio.run(main())
