"""
Busca qué integración de Altenar funciona sin bloqueo de sesión.

Para cada integración:
1. Intenta GetChampionshipEvents SIN sesión → si da 200, es pública, no necesita cookies
2. Si da 401, intenta inicializar sesión en el frontend y reintentar
3. Reporta cuál funciona y si tiene mercados de faltas para LaLiga

Uso:
    python debug_altenar.py
"""
import asyncio
import httpx
import random

ALTENAR_API = "https://sb2frontend-altenar2.biahosted.com/api/widget"
LALIGA_CHAMP_ID = "2941"

HEADERS_BASE = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# Integraciones conocidas de Altenar + su URL de frontend
# Añade más si encontrás otras (el nombre de integration sale en los requests XHR)
INTEGRATIONS = [
    ("paston",            "https://www.paston.es/apuestas-deportivas"),
    ("goldenpalace",      "https://www.goldenpalacesports.be/en"),
]

FOULS_KEYWORDS = ["falt", "foul", "faltas", "fouls"]


async def discover_integration_name(frontend_url: str) -> str | None:
    """Busca el nombre de integration en el HTML/JS de la página."""
    import re
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            resp = await client.get(frontend_url, headers=HEADERS_BASE, timeout=10)
            if resp.status_code >= 400:
                return None
            html = resp.text
            # Patrones comunes donde Altenar embebe el integration name
            patterns = [
                r'"integration"\s*:\s*"([^"]+)"',
                r"'integration'\s*:\s*'([^']+)'",
                r'integration[=:]"?([a-zA-Z0-9_-]+)"?',
                r'"integrationName"\s*:\s*"([^"]+)"',
            ]
            for pattern in patterns:
                m = re.search(pattern, html)
                if m:
                    return m.group(1)
        except Exception:
            pass
    return None


async def try_without_session(client: httpx.AsyncClient, integration: str) -> tuple[int, list]:
    """Prueba GetEventsByChamp sin inicializar sesión."""
    params = {
        "culture": "es-ES",
        "timezoneOffset": "-120",
        "integration": integration,
        "deviceType": "1",
        "numFormat": "en-GB",
        "countryCode": "ES",
        "champId": "0",
        "champIds": LALIGA_CHAMP_ID,
        "eventCount": "5",
    }
    headers = {**HEADERS_BASE, "Referer": f"https://www.{integration}.es/"}
    resp = await client.get(f"{ALTENAR_API}/GetEventsByChamp", params=params,
                            headers=headers, timeout=10)
    if resp.status_code != 200:
        return resp.status_code, []
    data = resp.json()
    events = data.get("events") or data.get("items") or (data if isinstance(data, list) else [])
    return 200, events


async def try_with_session(integration: str, frontend_url: str) -> tuple[str, list]:
    """Inicializa sesión en el frontend y reintenta."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Init sesión
        try:
            resp = await client.get(frontend_url, headers=HEADERS_BASE, timeout=10)
            cookies = dict(client.cookies)
            status = resp.status_code
        except Exception as e:
            return f"error red: {e}", []

        if status >= 400:
            return f"frontend {status} (bloqueado)", []

        # Llama a la API con las cookies obtenidas
        await asyncio.sleep(random.uniform(2, 5))
        params = {
            "culture": "es-ES",
            "timezoneOffset": "-120",
            "integration": integration,
            "deviceType": "1",
            "numFormat": "en-GB",
            "countryCode": "ES",
            "champId": "0",
            "champIds": LALIGA_CHAMP_ID,
            "eventCount": "5",
        }
        headers = {**HEADERS_BASE, "Referer": frontend_url}
        try:
            resp2 = await client.get(f"{ALTENAR_API}/GetEventsByChamp",
                                     params=params, headers=headers, timeout=10)
        except Exception as e:
            return f"error API: {e}", []

        if resp2.status_code != 200:
            return f"sesión ok ({len(cookies)} cookies) pero API {resp2.status_code}", []

        data = resp2.json()
        events = data.get("events") or data.get("items") or (data if isinstance(data, list) else [])
        return f"OK con sesión ({len(cookies)} cookies)", events


async def check_fouls_markets(client: httpx.AsyncClient, integration: str,
                              event_id: str, frontend_url: str) -> list[str]:
    """Verifica si hay mercados de faltas para un evento."""
    params = {
        "culture": "es-ES",
        "timezoneOffset": "120",
        "integration": integration,
        "deviceType": "1",
        "numFormat": "en-GB",
        "countryCode": "ES",
        "eventId": event_id,
        "showNonBoosts": "false",
    }
    headers = {**HEADERS_BASE, "Referer": frontend_url}
    try:
        await asyncio.sleep(random.uniform(2, 4))
        resp = await client.get(f"{ALTENAR_API}/GetEventDetails",
                                params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        markets = data.get("markets") or []
        return [m["name"] for m in markets if any(k in m.get("name", "").lower() for k in FOULS_KEYWORDS)]
    except Exception:
        return []


async def main():
    print("=" * 60)
    print("BÚSQUEDA DE INTEGRACIÓN ALTENAR SIN BLOQUEO")
    print("=" * 60)

    for integration_guess, frontend_url in INTEGRATIONS:
        print(f"\n[{integration_guess}] → {frontend_url}")

        # Intentar descubrir el nombre real de integration desde el HTML
        discovered = await discover_integration_name(frontend_url)
        if discovered and discovered != integration_guess:
            print(f"  🔍 Integration descubierto en HTML: '{discovered}' (era '{integration_guess}')")
            integration = discovered
        elif discovered:
            print(f"  🔍 Integration confirmado: '{discovered}'")
            integration = discovered
        else:
            print(f"  ⚠️  No se encontró integration en HTML, usando guess: '{integration_guess}'")
            integration = integration_guess

        async with httpx.AsyncClient(follow_redirects=True) as client:
            # Intento 1: sin sesión
            await asyncio.sleep(random.uniform(1, 3))
            code, events = await try_without_session(client, integration)

            if code == 200 and events:
                print(f"  ✅ SIN SESIÓN → HTTP 200 | {len(events)} eventos")
            elif code == 200:
                print(f"  ⚠️  SIN SESIÓN → HTTP 200 pero 0 eventos LaLiga")
            else:
                print(f"  ❌ Sin sesión → HTTP {code}")

                # Intento 2: con sesión
                status_msg, events = await try_with_session(integration, frontend_url)
                print(f"  {'✅' if 'OK' in status_msg else '❌'} Con sesión → {status_msg} | {len(events)} eventos")

            if events:
                # Verificar mercados de faltas en el primer evento
                first_event = events[0]
                event_id = str(first_event.get("id") or first_event.get("Id") or "")
                home = first_event.get("homeTeamName") or first_event.get("name") or "?"

                if event_id:
                    fouls = await check_fouls_markets(client, integration, event_id, frontend_url)
                    if fouls:
                        print(f"  ⚽ MERCADOS DE FALTAS en '{home}':")
                        for m in fouls:
                            print(f"     - {m}")
                    else:
                        print(f"  ℹ️  Sin mercados de faltas en '{home}'")

    print("\n" + "=" * 60)
    print("Fin. Las integraciones con ✅ son candidatas para Railway.")
    print("=" * 60)


asyncio.run(main())
