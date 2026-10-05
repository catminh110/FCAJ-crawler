import hashlib
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from fcaj_crawler.config import DEFAULT_CONCURRENCY, DEFAULT_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


class WorkshopCrawler:
    """Crawls an individual workshop domain, discovers all chapters, downloads assets, and cleans content."""

    def __init__(self, workshop_info: Dict, lang: str = "vi", output_dir: Optional[Path] = None):
        self.workshop = workshop_info
        self.ws_id = workshop_info["id"]
        self.base_url = workshop_info["url"].rstrip("/")
        self.lang = lang.lower()
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        
        # Directory setup
        base_output = output_dir or Path("output_fcaj")
        self.workshop_dir = base_output / "workshops" / f"{self.ws_id}_{self._sanitize_filename(self.workshop['title'])}"
        self.images_dir = self.workshop_dir / "images"
        self.workshop_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

        self.downloaded_images: Dict[str, str] = {}  # url -> local relative path

    def _sanitize_filename(self, name: str) -> str:
        clean = re.sub(r'[\\/*?:"<>|]', "", name)
        clean = re.sub(r'\s+', "_", clean).strip(" ._")
        return clean[:60] if clean else "workshop"

    def determine_root_url(self) -> str:
        """Determines the correct starting URL based on language preference."""
        if self.lang == "vi":
            vi_url = f"{self.base_url}/vi/"
            try:
                r = self.session.get(vi_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
                if r.status_code == 200:
                    return vi_url
            except Exception:
                pass
        return f"{self.base_url}/"

    def discover_chapters(self) -> List[Dict]:
        """
        Discovers all chapters/pages in the workshop in sequential order.
        Uses sidebar navigation tree as primary source, and sitemap.xml as fallback/verification.
        """
        root_url = self.determine_root_url()
        logger.info("[%s] Discovering chapters from root: %s", self.ws_id, root_url)

        chapters: List[Dict] = []
        seen_urls = set()

        try:
            resp = self.session.get(root_url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                resp.encoding = "utf-8"
                soup = BeautifulSoup(resp.content, "lxml")

                # Strategy 1: Hugo sidebar nav items (<ul class="topics">)
                sidebar = soup.select_one("nav#sidebar ul.topics")
                if sidebar:
                    # Recursively walk sidebar list items to preserve hierarchy
                    self._parse_sidebar_topics(sidebar, root_url, chapters, seen_urls, level=1)

                # Include home page if not already in chapters
                if root_url not in seen_urls:
                    body_home = soup.find("div", id="body-inner")
                    home_title = "Giới thiệu" if self.lang == "vi" else "Overview"
                    if body_home and body_home.find("h1"):
                        home_title = body_home.find("h1").get_text(strip=True)
                    chapters.insert(0, {
                        "title": home_title,
                        "url": root_url,
                        "order": 0,
                        "level": 0
                    })
                    seen_urls.add(root_url)
        except Exception as e:
            logger.error("[%s] Error fetching root URL for chapters: %s", self.ws_id, e)

        # Strategy 2: Check sitemap.xml to verify no subpages were missed
        sitemap_urls = self._fetch_sitemap_urls()
        extras = []
        for sm_url in sorted(set(sitemap_urls)):
            norm_url = sm_url.rstrip("/") + "/"
            if norm_url in seen_urls or sm_url in seen_urls:
                continue
            if self.lang == "vi" and "/vi/" not in sm_url:
                continue
            if self.lang == "en" and "/vi/" in sm_url:
                continue
            extras.append(sm_url)
            seen_urls.add(norm_url)

        # Insert each extra page right after the last chapter that is its URL-prefix parent
        for sm_url in extras:
            norm_url = sm_url.rstrip("/") + "/"
            insert_at = len(chapters)
            parent_level = 0
            for i, ch in enumerate(chapters):
                ch_norm = ch["url"].rstrip("/") + "/"
                if norm_url.startswith(ch_norm) and ch_norm != norm_url:
                    # place after parent and after all its existing descendants
                    j = i + 1
                    while j < len(chapters) and (chapters[j]["url"].rstrip("/") + "/").startswith(ch_norm):
                        j += 1
                    insert_at = j
                    parent_level = ch.get("level", 0)
            chapters.insert(insert_at, {
                "title": self._url_to_title(sm_url),
                "url": sm_url,
                "level": parent_level + 1,
            })

        # Drop Hugo taxonomy pages (tags / categories) - they are not lesson content
        chapters = [c for c in chapters if not self._is_taxonomy_url(c["url"])]
        for idx, ch in enumerate(chapters):
            ch["order"] = idx

        logger.info("[%s] Total chapters discovered: %d", self.ws_id, len(chapters))
        return chapters

    @staticmethod
    def _is_taxonomy_url(url: str) -> bool:
        path = urlparse(url).path.lower()
        return bool(re.search(r"/(tags|categories)(/|$)", path))

    def _parse_sidebar_topics(self, parent_elem, base_url: str, chapters: List[Dict], seen_urls: set, level: int):
        """Recursively parses sidebar navigation elements."""
        for li in parent_elem.find_all("li", recursive=False):
            a = li.find("a", recursive=False)
            if a and a.get("href"):
                page_url = urljoin(base_url, a["href"])
                norm_url = page_url.rstrip("/") + "/"
                if norm_url not in seen_urls and page_url not in seen_urls:
                    title = a.get_text(separator=" ", strip=True)
                    chapters.append({
                        "title": title,
                        "url": page_url,
                        "order": len(chapters) + 1,
                        "level": level
                    })
                    seen_urls.add(norm_url)
                    seen_urls.add(page_url)

            # Check nested sub-topics (sub-chapters)
            sub_ul = li.find("ul", recursive=False)
            if sub_ul:
                self._parse_sidebar_topics(sub_ul, base_url, chapters, seen_urls, level=level + 1)

    def _fetch_sitemap_urls(self) -> List[str]:
        """Fetches all URLs listed in the workshop sitemap.xml."""
        urls = []
        sitemap_root = f"{self.base_url}/sitemap.xml"
        try:
            r = self.session.get(sitemap_root, timeout=8)
            if r.status_code == 200:
                r.encoding = "utf-8"
                soup = BeautifulSoup(r.content, "xml")
                # Check for sitemap index
                locs = soup.find_all("loc")
                for loc in locs:
                    sub_sitemap_url = loc.get_text(strip=True)
                    if sub_sitemap_url.endswith(".xml"):
                        # Target specific language sitemap
                        if self.lang == "vi" and "/vi/sitemap.xml" in sub_sitemap_url:
                            urls.extend(self._fetch_single_sitemap(sub_sitemap_url))
                        elif self.lang == "en" and ("/en/sitemap.xml" in sub_sitemap_url or "/sitemap.xml" in sub_sitemap_url):
                            urls.extend(self._fetch_single_sitemap(sub_sitemap_url))
                    else:
                        urls.append(sub_sitemap_url)
        except Exception as e:
            logger.debug("[%s] Sitemap check note: %s", self.ws_id, e)
        return urls

    def _fetch_single_sitemap(self, url: str) -> List[str]:
        urls = []
        try:
            r = self.session.get(url, timeout=8)
            if r.status_code == 200:
                r.encoding = "utf-8"
                soup = BeautifulSoup(r.content, "xml")
                for loc in soup.find_all("loc"):
                    u = loc.get_text(strip=True)
                    if not u.endswith(".xml"):
                        urls.append(u)
        except Exception:
            pass
        return urls

    def _url_to_title(self, url: str) -> str:
        slug = urlparse(url).path.strip("/").split("/")[-1]
        slug = unquote(slug)
        slug = re.sub(r"^\d+-", "", slug)
        return slug.replace("-", " ").title()

    def download_image(self, img_url: str) -> Optional[str]:
        """Downloads an image and caches it locally, returning relative local path."""
        if img_url in self.downloaded_images:
            return self.downloaded_images[img_url]

        try:
            parsed = urlparse(img_url)
            filename = os.path.basename(parsed.path)
            if not filename or len(filename) > 50 or "." not in filename:
                hash_id = hashlib.md5(img_url.encode()).hexdigest()[:10]
                ext = ".png"
                filename = f"img_{hash_id}{ext}"
            else:
                # Sanitize filename
                name_part, ext_part = os.path.splitext(filename)
                clean_name = re.sub(r'[^a-zA-Z0-9_\-]', "_", name_part)[:30]
                clean_ext = ext_part.split("?")[0]
                if not clean_ext:
                    clean_ext = ".png"
                hash_id = hashlib.md5(img_url.encode()).hexdigest()[:6]
                filename = f"{clean_name}_{hash_id}{clean_ext}"

            local_path = self.images_dir / filename
            if not local_path.exists():
                r = self.session.get(img_url, timeout=15)
                if r.status_code == 200 and len(r.content) > 0:
                    with open(local_path, "wb") as f:
                        f.write(r.content)
                else:
                    return None

            rel_path = f"images/{filename}"
            self.downloaded_images[img_url] = rel_path
            return rel_path
        except Exception as e:
            logger.debug("[%s] Failed to download image %s: %s", self.ws_id, img_url, e)
            return None

    def crawl_chapter(self, chapter: Dict) -> Dict:
        """Fetches page content, rewrites and downloads images, strips unneeded UI chrome."""
        url = chapter["url"]
        logger.info("[%s] Crawling page: %s (%s)", self.ws_id, chapter["title"], url)

        try:
            r = self.session.get(url, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.content, "lxml")

            body_inner = soup.find("div", id="body-inner")
            if not body_inner:
                body_inner = soup.find("section", id="body")
            if not body_inner:
                body_inner = soup.find("body")

            if not body_inner:
                return {**chapter, "html": "<p>Không thể trích xuất nội dung.</p>", "images_count": 0}

            # Extract or refine title
            h1 = body_inner.find("h1")
            page_title = chapter["title"]
            if h1:
                page_title = h1.get_text(strip=True)
            elif soup.title:
                page_title = soup.title.get_text(strip=True).split("::")[0].strip()

            # Clean UI elements
            for tag in body_inner.find_all(["script", "style", "noscript"]):
                tag.decompose()
            for elem in body_inner.select("#sidebar-toggle-span, #navigation, .nav-prev, .nav-next"):
                elem.decompose()
            for hit in body_inner.find_all("img", src=re.compile(r"hitwebcounter|google-analytics")):
                hit.decompose()

            # Process images
            images = body_inner.find_all("img")
            img_download_tasks = []
            img_nodes = []

            for img in images:
                src = img.get("src")
                if not src:
                    continue
                abs_img_url = urljoin(url, src)
                img_nodes.append((img, abs_img_url))

            # Concurrently download images
            with ThreadPoolExecutor(max_workers=DEFAULT_CONCURRENCY) as executor:
                future_to_img = {executor.submit(self.download_image, abs_url): (node, abs_url) for node, abs_url in img_nodes}
                for future in as_completed(future_to_img):
                    node, abs_url = future_to_img[future]
                    try:
                        local_rel = future.result()
                        if local_rel:
                            node["src"] = local_rel
                            # Remove fixed width styles that might distort in print
                            if "width" in node.attrs and "%" not in str(node.attrs.get("width")):
                                del node.attrs["width"]
                        else:
                            node["src"] = abs_url
                    except Exception:
                        node["src"] = abs_url

            # Fix relative links to internal anchors or absolute links
            for a in body_inner.find_all("a", href=True):
                href = a["href"]
                if not href.startswith("http") and not href.startswith("#") and not href.startswith("mailto:"):
                    a["href"] = urljoin(url, href)

            # Return cleaned HTML content
            clean_html = str(body_inner)
            return {
                **chapter,
                "title": page_title,
                "html": clean_html,
                "images_count": len(img_nodes)
            }

        except Exception as e:
            logger.error("[%s] Error crawling %s: %s", self.ws_id, url, e)
            return {
                **chapter,
                "html": f"<div class='error-box'>Lỗi tải nội dung ({url}): {e}</div>",
                "images_count": 0
            }

    def crawl_all(self, progress_callback=None) -> List[Dict]:
        """Discovers and crawls all chapters of the workshop sequentially."""
        if progress_callback:
            progress_callback(f"[{self.ws_id}] Đang tìm danh sách bài viết...", 10)

        chapters = self.discover_chapters()
        if not chapters:
            logger.warning("[%s] No chapters found!", self.ws_id)
            return []

        crawled_chapters = []
        total = len(chapters)

        for idx, ch in enumerate(chapters):
            result = self.crawl_chapter(ch)
            crawled_chapters.append(result)
            if progress_callback:
                pct = 10 + int(85 * (idx + 1) / total)
                progress_callback(f"[{self.ws_id}] Đã cào ({idx+1}/{total}): {ch['title'][:30]}...", pct)

        if progress_callback:
            progress_callback(f"[{self.ws_id}] Hoàn thành cào {total} bài học!", 100)

        return crawled_chapters
