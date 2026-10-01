import os
from pathlib import Path

# Base Paths
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(os.environ.get("FCAJ_OUTPUT_DIR", WORKSPACE_ROOT / "output_fcaj"))
DATA_DIR = WORKSPACE_ROOT / "data"

# Web Sources
MAIN_HUB_URL = "https://cloudjourney.awsstudygroup.com"
CATALOG_CACHE_FILE = DATA_DIR / "catalog.json"
STATE_FILE = DATA_DIR / "crawl_state.json"

# Crawler Settings
DEFAULT_CONCURRENCY = 4
REQUEST_TIMEOUT = 20
MAX_RETRIES = 3
BACKOFF_FACTOR = 0.5

# Headers for HTTP requests
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
}

# PDF Settings
PDF_PAGE_FORMAT = "A4"
PDF_MARGIN = {
    "top": "20mm",
    "bottom": "20mm",
    "left": "15mm",
    "right": "15mm"
}
PDF_PRINT_BACKGROUND = True

# Ensure essential directories exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
