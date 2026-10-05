import json
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from fcaj_crawler.config import (
    CATALOG_CACHE_FILE,
    DEFAULT_HEADERS,
    make_session,
    MAIN_HUB_URL,
    REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)


class CatalogScanner:
    """Scans and extracts all workshop listings and categories from the FCAJ main portal."""

    def __init__(self, force_refresh: bool = False):
        self.force_refresh = force_refresh
        self.session = make_session()

    def scan(self, progress_callback=None) -> Dict:
        """
        Scans cloudjourney.awsstudygroup.com and its category sections to discover
        all linked workshop sites (*.awsstudygroup.com).
        """
        if not self.force_refresh and CATALOG_CACHE_FILE.exists():
            try:
                with open(CATALOG_CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("workshops"):
                        logger.info("Loaded %d workshops from cache.", len(data["workshops"]))
                        return data
            except Exception as e:
                logger.warning("Failed to load catalog cache: %s", e)

        if progress_callback:
            progress_callback("Đang tải trang chủ Cloud Journey...", 5)

        logger.info("Scanning main hub: %s", MAIN_HUB_URL)
        resp = self.session.get(MAIN_HUB_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        main_soup = BeautifulSoup(resp.content, "lxml")

        # Discover categories
        categories = []
        for li in main_soup.select("ul.topics li"):
            a = li.find("a")
            if a and a.get("href"):
                cat_url = urljoin(MAIN_HUB_URL, a["href"])
                cat_title = a.get_text(strip=True)
                categories.append({
                    "title": cat_title,
                    "url": cat_url,
                    "slug": urlparse(cat_url).path.strip("/")
                })

        if progress_callback:
            progress_callback(f"Đã tìm thấy {len(categories)} danh mục. Đang quét danh sách workshop...", 20)

        workshops_map: Dict[str, Dict] = {}

        # 1. Parse workshops directly from the main hub page content
        self._extract_workshops_from_soup(main_soup, "Trang chủ", workshops_map)

        # 2. Parse workshops from each category page for completeness
        total_cats = len(categories)
        for idx, cat in enumerate(categories):
            try:
                logger.info("Scanning category: %s (%s)", cat["title"], cat["url"])
                cat_resp = self.session.get(cat["url"], timeout=REQUEST_TIMEOUT)
                if cat_resp.status_code == 200:
                    cat_resp.encoding = "utf-8"
                    cat_soup = BeautifulSoup(cat_resp.content, "lxml")
                    self._extract_workshops_from_soup(cat_soup, cat["title"], workshops_map)
            except Exception as ex:
                logger.warning("Error scanning category %s: %s", cat["url"], ex)
            
            if progress_callback:
                percent = 20 + int(70 * (idx + 1) / total_cats)
                progress_callback(f"Đang quét danh mục: {cat['title']}...", percent)

        # Convert map to sorted list by workshop ID
        workshops = sorted(list(workshops_map.values()), key=lambda w: w.get("sort_key", 999999))

        result = {
            "source": MAIN_HUB_URL,
            "total_workshops": len(workshops),
            "categories": categories,
            "workshops": workshops
        }

        # Cache catalog
        try:
            CATALOG_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CATALOG_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logger.info("Catalog saved with %d workshops to %s", len(workshops), CATALOG_CACHE_FILE)
        except Exception as e:
            logger.error("Failed to write catalog cache: %s", e)

        if progress_callback:
            progress_callback(f"Hoàn tất quét! Tìm thấy {len(workshops)} workshop.", 100)

        return result

    def _extract_workshops_from_soup(self, soup: BeautifulSoup, current_category: str, workshops_map: Dict[str, Dict]):
        """Parses links inside body content that point to child workshop subdomains."""
        body = soup.find("div", id="body-inner") or soup.find("section", id="body") or soup
        
        # Look at list items and links
        for a in body.find_all("a", href=True):
            href = a["href"].strip()
            full_url = urljoin(MAIN_HUB_URL, href)
            parsed = urlparse(full_url)
            netloc = parsed.netloc.lower()

            # Match subdomains like 000001.awsstudygroup.com, 100002.awsstudygroup.com
            if "awsstudygroup.com" in netloc and netloc != "cloudjourney.awsstudygroup.com" and netloc != "awsstudygroup.com":
                # Extract numeric or sub-id
                subdomain_prefix = netloc.split(".")[0]
                ws_id = subdomain_prefix

                # Determine sort key
                try:
                    sort_key = int(re.sub(r"\D", "", ws_id))
                except ValueError:
                    sort_key = 999999

                title = a.get_text(separator=" ", strip=True)
                if not title:
                    title = f"Workshop {ws_id}"

                # Try to determine parent section / subcategory
                parent_li = a.find_parent("li")
                subcategory = None
                if parent_li:
                    parent_ul = parent_li.find_parent(["ul", "ol"])
                    if parent_ul:
                        prev_header = parent_ul.find_previous_sibling(["h2", "h3", "h4", "p", "strong"])
                        if prev_header:
                            subcategory = prev_header.get_text(strip=True)

                workshop_url = f"https://{netloc}"

                if ws_id not in workshops_map:
                    workshops_map[ws_id] = {
                        "id": ws_id,
                        "title": title,
                        "domain": netloc,
                        "url": workshop_url,
                        "category": current_category,
                        "subcategory": subcategory,
                        "sort_key": sort_key,
                        "has_vi": True,
                        "has_en": True
                    }
                else:
                    # Update category if previously set to generic home
                    if workshops_map[ws_id]["category"] == "Trang chủ" and current_category != "Trang chủ":
                        workshops_map[ws_id]["category"] = current_category
                    if subcategory and not workshops_map[ws_id].get("subcategory"):
                        workshops_map[ws_id]["subcategory"] = subcategory

    @staticmethod
    def load_cached_catalog() -> Optional[Dict]:
        if CATALOG_CACHE_FILE.exists():
            try:
                with open(CATALOG_CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None
