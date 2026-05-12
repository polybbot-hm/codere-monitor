# Codere Monitor — Alertas de Faltas LaLiga

Sistema de polling que detecta cuando aparecen cuotas de faltas en Codere para partidos de LaLiga y manda notificaciones a Telegram.

## Arquitectura

```
Railway Worker (24/7)
├── Job cada 5min → busca partidos LaLiga próximas 24h
├── Job cada 2min → consulta mercados de faltas por partido
├── Job cada 24h  → limpia snapshots viejos
├── PostgreSQL     → historial de cuotas + alertas enviadas
└── Telegram Bot   → notificaciones a tu chat personal
```

## Setup local

### 1. Requisitos
- Python 3.12+
- PostgreSQL corriendo localmente (o usa Railway en remoto)

### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno
```bash
cp .env.example .env
# Edita .env con tus valores
```

#### Cómo obtener el TELEGRAM_TOKEN
1. Habla con [@BotFather](https://t.me/BotFather) en Telegram
2. `/newbot` → elige nombre → te da el token

#### Cómo obtener el TELEGRAM_CHAT_ID
1. Habla con [@userinfobot](https://t.me/userinfobot)
2. Te responde con tu chat ID

### 4. Arrancar
```bash
python main.py
```

---

## Deploy en Railway

### 1. Crea un proyecto en [railway.app](https://railway.app)

### 2. Añade un servicio PostgreSQL
- New Service → Database → PostgreSQL
- Railway crea automáticamente la variable `DATABASE_URL`

### 3. Añade el código
- Conecta tu repo de GitHub o haz push directo
- Railway detecta el `Dockerfile` automáticamente

### 4. Variables de entorno en Railway
En tu servicio → Settings → Variables:
```
TELEGRAM_TOKEN=tu_token_aqui
TELEGRAM_CHAT_ID=tu_chat_id_aqui
DATABASE_URL=  ← Railway la inyecta sola desde el servicio PostgreSQL
```

### 5. Deploy
Railway hace el build y arranca el worker automáticamente.

---

## Añadir nuevas casas de apuestas

1. Crea `scrapers/bet365.py`:
```python
from scrapers.base import BookmakerScraper, MatchInfo, OddsMarket

class Bet365Scraper(BookmakerScraper):
    @property
    def name(self): return "bet365"

    async def get_laliga_matches(self) -> list[MatchInfo]:
        # Tu implementación aquí
        ...

    async def get_fouls_markets(self, match: MatchInfo) -> list[OddsMarket]:
        # Tu implementación aquí
        ...
```

2. Regístrala en `scrapers/__init__.py`:
```python
from scrapers.bet365 import Bet365Scraper

SCRAPERS = {
    "codere": CodereScaper(),
    "bet365": Bet365Scraper(),   # ← añadir aquí
}
```

¡Listo! El scheduler y el analyzer funcionan igual para todas las casas.

---

## Estructura del proyecto

```
codere-monitor/
├── main.py              # Entry point
├── config.py            # Variables de entorno y constantes
├── scheduler.py         # APScheduler jobs (fetch, poll, cleanup)
├── scrapers/
│   ├── base.py          # Clase abstracta BookmakerScraper
│   ├── codere.py        # Implementación Codere
│   └── __init__.py      # Registro de casas activas
├── analyzer/
│   └── odds_analyzer.py # Detección de nuevos mercados y cambios de cuota
├── notifier/
│   └── telegram.py      # Envío de mensajes Telegram
├── db/
│   ├── models.py        # SQLAlchemy models (Match, OddsSnapshot, AlertSent)
│   └── repository.py    # Queries a BD
├── Dockerfile
├── railway.toml
└── .env.example
```
