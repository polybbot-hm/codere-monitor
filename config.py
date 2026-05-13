import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Database
DATABASE_URL = os.environ["DATABASE_URL"]

# Polling intervals (seconds)
FETCH_MATCHES_INTERVAL = 300       # cada 5 minutos busca partidos nuevos
POLL_ODDS_INTERVAL = 120           # cada 2 minutos actualiza cuotas
CLEANUP_INTERVAL = 86400           # cada 24h limpia snapshots viejos

# Codere
CODERE_BASE_URL = "https://m.apuestas.codere.es"
CODERE_LALIGA_PARENT_ID = "2903511051"
CODERE_CATEGORY_STATS = 78         # ESTADÍSTICAS (contiene Faltas)
CODERE_CATEGORY_CORNERS = 55       # Córners

# Monitorizar partidos con X horas de antelación
HOURS_AHEAD = 24

# Anti-ban: jitter entre requests (segundos)
REQUEST_JITTER_MIN = 5
REQUEST_JITTER_MAX = 20

# Detección de desaparición de cuotas
DISAPPEARANCE_THRESHOLD = int(os.getenv("DISAPPEARANCE_THRESHOLD", 2))
DISAPPEARANCE_RATE_LIMIT_MINUTES = int(os.getenv("DISAPPEARANCE_RATE_LIMIT_MINUTES", 30))
