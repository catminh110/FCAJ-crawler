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


def make_session(pool_size: int = 10):
    """requests.Session with retry/backoff for transient network errors, 429 and 5xx."""
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    retry = Retry(
        total=MAX_RETRIES,
        connect=MAX_RETRIES,
        read=MAX_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=pool_size, pool_maxsize=pool_size)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(DEFAULT_HEADERS)
    return session
