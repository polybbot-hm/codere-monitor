from scrapers.codere import CodereScaper
from scrapers.granmadrid import GranMadridScraper
from scrapers.base import BookmakerScraper

# Registro de casas de apuestas activas.
# Para añadir una nueva casa:
#   1. Crea scrapers/bet365.py con clase Bet365Scraper(BookmakerScraper)
#   2. Importa aquí y añade al dict
SCRAPERS: dict[str, BookmakerScraper] = {
    "codere": CodereScaper(),
    # "granmadrid": GranMadridScraper(),  # IP datacenter bloqueada por Cloudflare (403 → 401)
    # "bet365": Bet365Scraper(),
    # "bwin": BwinScraper(),
}
