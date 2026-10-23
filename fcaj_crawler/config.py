import os
import re
import shutil
import sys
from pathlib import Path
from typing import Optional

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


def sanitize_filename(name: str, max_len: int = 60) -> str:
    """Sanitizes a workshop or file title into a safe cross-platform filesystem name without mid-word cuts."""
    if not name:
        return "workshop"
    clean = re.sub(r'[\\/*?:"<>|]', "", str(name))
    clean = re.sub(r"\s+", "_", clean).strip(" ._")
    if len(clean) > max_len:
        truncated = clean[:max_len]
        if "_" in truncated:
            last_sep = truncated.rfind("_")
            if last_sep >= max_len // 2:
                truncated = truncated[:last_sep]
        clean = truncated
    # Strip trailing unmatched opening brackets/parens or punctuation
    clean = clean.strip(" ._(")
    if clean.count("(") > clean.count(")"):
        clean = clean.rsplit("(", 1)[0].strip(" ._")
    return clean if clean else "workshop"


def find_system_chromium() -> Optional[str]:
    """Finds an installed Chrome/Chromium/Edge binary if Playwright's bundled browser is missing."""
    env_path = os.environ.get("FCAJ_CHROME_PATH")
    if env_path and Path(env_path).is_file():
        return env_path

    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return str(Path(c))

    for binary in ("google-chrome", "chromium", "chromium-browser", "chrome", "msedge"):
        found = shutil.which(binary)
        if found:
            return found
    return None


def configure_utf8_console() -> None:
    """Reconfigures stdout and stderr to UTF-8 on Windows to avoid charmap UnicodeEncodeError."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


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
