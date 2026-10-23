import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from fcaj_crawler.config import WORKSPACE_ROOT, configure_utf8_console, make_session, sanitize_filename
from fcaj_crawler.crawler import WorkshopCrawler
from fcaj_crawler.markdown_exporter import (
    MarkdownExporter,
    _demote_headings,
    build_combined_bundle,
    build_global_index,
    html_to_markdown,
    slugify,
)
from fcaj_crawler.pdf_generator import PDFGenerator
from fcaj_crawler.processor import WorkshopProcessor
from fcaj_crawler.runner import CrawlManager
from fcaj_crawler.scanner import CatalogScanner
from fcaj_crawler.web.app import app, manager


# ---------------------------------------------------------------------------
# 1. Config & Utilities Tests
# ---------------------------------------------------------------------------

def test_sanitize_filename():
    assert sanitize_filename("Creating Your First AWS Account") == "Creating_Your_First_AWS_Account"
    assert sanitize_filename('Test: "Special" <Chars> | ? * / \\') == "Test_Special_Chars"
    assert sanitize_filename("   ...___   ") == "workshop"
    assert sanitize_filename("") == "workshop"
    # Truncation should cut at word boundary and never leave unmatched '('
    long_name = "Access Management with AWS Identity and Access Management (IAM)"
    res = sanitize_filename(long_name, max_len=60)
    assert len(res) <= 60
    assert not res.endswith("_")
    assert "(" not in res or ")" in res


def test_make_session():
    s = make_session(pool_size=4)
    assert "User-Agent" in s.headers
    assert "https://" in s.adapters


# ---------------------------------------------------------------------------
# 2. Scanner Tests
# ---------------------------------------------------------------------------

def test_scanner_extract_and_zero_categories(tmp_path, monkeypatch):
    cache_file = tmp_path / "catalog.json"
    monkeypatch.setattr("fcaj_crawler.scanner.CATALOG_CACHE_FILE", cache_file)

    hub_html = """
    <html><body>
      <ul class="topics">
        <li><a href="/1-explore/">1.Explore AWS Services</a></li>
      </ul>
      <div id="body-inner">
        <a href="https://000001.awsstudygroup.com"></a>
      </div>
    </body></html>
    """
    cat_html = """
    <html><body>
      <div id="body-inner">
        <h3>Compute &amp; Networking</h3>
        <ul>
          <li><a href="https://000001.awsstudygroup.com">Creating Your First AWS Account</a></li>
          <li><a href="https://000004.awsstudygroup.com">Compute Essentials (EC2)</a></li>
        </ul>
      </div>
    </body></html>
    """

    scanner = CatalogScanner(force_refresh=True)

    def fake_get(url, timeout=20):
        resp = MagicMock()
        resp.status_code = 200
        resp.content = (cat_html if "1-explore" in url else hub_html).encode("utf-8")
        return resp

    monkeypatch.setattr(scanner.session, "get", fake_get)
    progress_steps = []
    catalog = scanner.scan(progress_callback=lambda msg, pct: progress_steps.append((msg, pct)))

    assert catalog["total_workshops"] == 2
    ws_by_id = {w["id"]: w for w in catalog["workshops"]}
    # Workshop 000001 should have its title upgraded from fallback "Workshop 000001" and category upgraded from "Trang chủ"
    assert ws_by_id["000001"]["title"] == "Creating Your First AWS Account"
    assert ws_by_id["000001"]["category"] == "1.Explore AWS Services"
    assert ws_by_id["000001"]["category_slug"] == "1-explore"
    assert ws_by_id["000001"]["subcategory"] == "Compute & Networking"
    assert cache_file.exists()


# ---------------------------------------------------------------------------
# 3. Crawler Tests
# ---------------------------------------------------------------------------

def test_crawler_discover_chapters_and_sitemap(tmp_path, monkeypatch):
    ws = {"id": "000001", "title": "Test Workshop", "url": "https://000001.awsstudygroup.com"}
    crawler = WorkshopCrawler(ws, lang="en", output_dir=tmp_path)

    root_html = """
    <html><body>
      <nav id="sidebar">
        <ul class="topics">
          <li>
            <a href="/1-intro/">1. Introduction</a>
            <ul>
              <li><a href="/1-intro/1.1-sub/#anchor">1.1 Subtopic</a></li>
              <li><a href="/1-intro/1.1-sub/#another-anchor">1.1 Duplicate Anchor</a></li>
            </ul>
          </li>
          <li><a href="/tags/">Tags</a></li>
        </ul>
      </nav>
      <div id="body-inner"><h1>Workshop Home</h1></div>
    </body></html>
    """
    sitemap_index_xml = """<?xml version="1.0" encoding="utf-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://000001.awsstudygroup.com/en/sitemap.xml</loc></sitemap>
      <sitemap><loc>https://000001.awsstudygroup.com/vi/sitemap.xml</loc></sitemap>
    </sitemapindex>
    """
    en_sitemap_xml = """<?xml version="1.0" encoding="utf-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://000001.awsstudygroup.com/</loc></url>
      <url><loc>https://000001.awsstudygroup.com/1-intro/1.2-extra/</loc></url>
      <url><loc>https://000001.awsstudygroup.com/categories/</loc></url>
    </urlset>
    """

    requested_urls = []

    def fake_get(url, timeout=20, allow_redirects=True):
        requested_urls.append(url)
        resp = MagicMock()
        resp.status_code = 200
        if url.endswith("/sitemap.xml") and "/en/" not in url and "/vi/" not in url:
            resp.content = sitemap_index_xml.encode("utf-8")
        elif "/en/sitemap.xml" in url:
            resp.content = en_sitemap_xml.encode("utf-8")
        elif "/vi/sitemap.xml" in url:
            raise AssertionError("English crawler should not fetch /vi/sitemap.xml!")
        else:
            resp.content = root_html.encode("utf-8")
        return resp

    monkeypatch.setattr(crawler.session, "get", fake_get)
    chapters = crawler.discover_chapters()

    urls = [c["url"] for c in chapters]
    # Home + 1-intro + 1.1-sub (deduplicated despite #anchor) + 1.2-extra (from sitemap); no /tags/ or /categories/
    assert urls == [
        "https://000001.awsstudygroup.com/",
        "https://000001.awsstudygroup.com/1-intro/",
        "https://000001.awsstudygroup.com/1-intro/1.1-sub/",
        "https://000001.awsstudygroup.com/1-intro/1.2-extra/",
    ]


def test_crawler_download_image_and_crawl_chapter(tmp_path, monkeypatch):
    ws = {"id": "000004", "title": "Compute (EC2)", "url": "https://000004.awsstudygroup.com"}
    crawler = WorkshopCrawler(ws, lang="vi", output_dir=tmp_path)

    long_svg_url = "https://000004.awsstudygroup.com/images/" + ("very_long_architecture_diagram_name_" * 2) + ".svg?ver=1"
    chapter_html = f"""
    <html><body>
      <div id="body-inner">
        <h1>Chương 1: Khởi tạo EC2</h1>
        <script>alert(1)</script>
        <img src="{long_svg_url}" width="800" alt="Arch">
        <img src="{long_svg_url}" width="800" alt="Duplicate in same chapter">
        <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=">
        <a href="javascript:void(0)">JS Link</a>
        <a href="subpage/index.html">Subpage</a>
      </div>
    </body></html>
    """

    img_fetch_count = 0

    def fake_get(url, timeout=20, allow_redirects=True):
        nonlocal img_fetch_count
        resp = MagicMock()
        resp.status_code = 200
        if url == long_svg_url:
            img_fetch_count += 1
            resp.content = b"<svg></svg>"
        else:
            resp.content = chapter_html.encode("utf-8")
        return resp

    monkeypatch.setattr(crawler.session, "get", fake_get)

    res = crawler.crawl_chapter({"title": "Ch 1", "url": "https://000004.awsstudygroup.com/vi/1-ec2/", "level": 1})
    assert res["title"] == "Chương 1: Khởi tạo EC2"
    # Image fetched only ONCE despite appearing twice in the chapter
    assert img_fetch_count == 1
    # Preserves .svg extension even though filename > 50 chars
    assert ".svg" in res["html"]
    # javascript: link untouched, relative link resolved
    assert 'href="javascript:void(0)"' in res["html"]
    assert 'href="https://000004.awsstudygroup.com/vi/1-ec2/subpage/index.html"' in res["html"]


# ---------------------------------------------------------------------------
# 4. Markdown Exporter & Global Index Tests
# ---------------------------------------------------------------------------

def test_markdown_exporter_and_global_index(tmp_path):
    assert slugify("Giới thiệu về Đám mây AWS!") == "gioi-thieu-ve-dam-may-aws"
    demoted = _demote_headings("# Title\n```bash\n# comment inside code\n```\n## Sub")
    assert demoted == "## Title\n```bash\n# comment inside code\n```\n### Sub"

    sample_html = """
    <div id="body-inner">
      <h1>Bài 1</h1>
      <div class="notices warning"><p>Cẩn thận chi phí!</p></div>
      <pre><code data-lang="yaml">key: value</code></pre>
      <img src="images/pic.png" alt="Ảnh [1]">
    </div>
    """
    md = html_to_markdown(sample_html, image_prefix="../")
    assert "⚠️ **Warning**" in md
    assert "```yaml" in md
    assert r"![Ảnh \[1\]](../images/pic.png)" in md

    ws = {
        "id": "000004",
        "title": "Compute Essentials with Amazon (EC2) | Part 1",
        "url": "https://000004.awsstudygroup.com",
        "category": "1.Explore | AWS",
    }
    ws_dir = tmp_path / "workshops" / f"000004_{sanitize_filename(ws['title'])}"
    chapters = [
        {"title": "Giới thiệu", "url": "https://000004.awsstudygroup.com/vi/", "level": 1, "html": sample_html},
        {"title": "Tạo máy chủ", "url": "https://000004.awsstudygroup.com/vi/2/", "level": 2, "html": "<p>Step 2</p>"},
    ]

    exporter = MarkdownExporter(ws, chapters, ws_dir, lang="vi")
    full_md_path = exporter.export()
    assert full_md_path.exists()
    assert (ws_dir / "README.md").exists()
    assert (ws_dir / "metadata_vi.json").exists()

    # Check global index handles parentheses and pipes properly
    idx_path = build_global_index(tmp_path)
    idx_content = idx_path.read_text(encoding="utf-8")
    assert "%28EC2%29" in idx_content
    assert r"\|" in idx_content

    # Test single-file combined bundle (Markdown + PDF)
    fake_pdf_gen = MagicMock()

    def write_dummy_pdf(html_p, pdf_p, title=None):
        pdf_p.write_bytes(b"%PDF-1.4 bundle")
        return True

    fake_pdf_gen.convert_html_to_pdf.side_effect = write_dummy_pdf

    bundle_res = build_combined_bundle(
        output_dir=tmp_path,
        lang="vi",
        output_format="both",
        pdf_generator=fake_pdf_gen,
    )
    assert bundle_res["status"] == "success"
    assert bundle_res["workshops_count"] == 1
    bundle_md = tmp_path / "FCAJ_ALL_VI.md"
    bundle_pdf = tmp_path / "FCAJ_ALL_VI.pdf"
    assert bundle_md.exists()
    assert bundle_pdf.exists()
    bundle_md_text = bundle_md.read_text(encoding="utf-8")
    assert '<a id="workshop-000004"></a>' in bundle_md_text
    assert "WORKSHOP_START" not in bundle_md_text
    assert "workshops/000004_" in bundle_md_text


# ---------------------------------------------------------------------------
# 5. Processor & PDF Generator Tests
# ---------------------------------------------------------------------------

def test_processor_and_pdf_generator(tmp_path):
    ws = {
        "id": "000001",
        "title": "AWS & Cloud <Basics>",
        "url": "https://000001.awsstudygroup.com",
        "category": "1.Explore & Learn",
    }
    chapters = [
        {"title": "Chapter 1 & <Intro>", "url": "https://000001.awsstudygroup.com/vi/", "level": 1, "html": "<p>Hello</p>"}
    ]
    processor = WorkshopProcessor(ws, chapters, lang="vi", output_dir=tmp_path)
    html_path = processor.generate_book_html()
    assert html_path.exists()
    content = html_path.read_text(encoding="utf-8")
    assert "AWS &amp; Cloud &lt;Basics&gt;" in content

    # Verify PDFGenerator uses Path.as_uri() (valid file:/// on Windows) and escapes header title
    pdf_gen = PDFGenerator()
    pdf_out = tmp_path / "out.pdf"

    with patch("fcaj_crawler.pdf_generator.sync_playwright") as mock_pw:
        mock_ctx = MagicMock()
        mock_pw.return_value.__enter__.return_value = mock_ctx
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_ctx.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        def fake_pdf(**kwargs):
            Path(kwargs["path"]).write_bytes(b"%PDF-1.4 fake")

        mock_page.pdf.side_effect = fake_pdf

        ok = pdf_gen.convert_html_to_pdf(html_path, pdf_out, title="Title & <Tag>")
        assert ok is True
        called_url = mock_page.goto.call_args[0][0]
        assert called_url.startswith("file:///")
        assert "\\" not in called_url
        header_tpl = mock_page.pdf.call_args[1]["header_template"]
        assert "Title &amp; &lt;Tag&gt;" in header_tpl
        mock_browser.close.assert_called_once()


# ---------------------------------------------------------------------------
# 6. Runner & Category Filtering Tests
# ---------------------------------------------------------------------------

def test_runner_category_and_combined_filtering():
    categories = [
        {"title": "1.Explore AWS Services", "slug": "1-explore", "url": "https://cloudjourney.awsstudygroup.com/1-explore/"},
        {"title": "2.Migrate to AWS", "slug": "2-migrate", "url": "https://cloudjourney.awsstudygroup.com/2-migrate/"},
    ]
    workshops = [
        {"id": "000001", "title": "Creating AWS Account", "category": "1.Explore AWS Services", "subcategory": "Basics"},
        {"id": "000004", "title": "Compute Essentials (EC2)", "category": "1.Explore AWS Services", "subcategory": "Compute"},
        {"id": "000010", "title": "Database Migration", "category": "2.Migrate to AWS", "subcategory": "DMS"},
    ]

    # Match by category slug '1-explore' even when workshop['category'] is '1.Explore AWS Services'
    res_slug = CrawlManager._filter_workshops(workshops, categories, category_slug="1-explore")
    assert [w["id"] for w in res_slug] == ["000001", "000004"]

    # Combined category slug + keyword filter
    res_combined = CrawlManager._filter_workshops(workshops, categories, category_slug="1-explore", keyword="ec2")
    assert [w["id"] for w in res_combined] == ["000004"]

    # Keyword matching subcategory
    res_subcat = CrawlManager._filter_workshops(workshops, categories, keyword="dms")
    assert [w["id"] for w in res_subcat] == ["000010"]


def test_runner_run_workshops_end_to_end(tmp_path, monkeypatch):
    state_file = tmp_path / "crawl_state.json"
    monkeypatch.setattr("fcaj_crawler.runner.STATE_FILE", state_file)

    fake_catalog = {
        "categories": [{"title": "1.Explore AWS Services", "slug": "1-explore", "url": "https://cloudjourney.awsstudygroup.com/1-explore/"}],
        "workshops": [
            {
                "id": "000001",
                "title": "Creating AWS Account",
                "domain": "000001.awsstudygroup.com",
                "url": "https://000001.awsstudygroup.com",
                "category": "1.Explore AWS Services",
                "subcategory": "Basics",
            }
        ],
    }

    monkeypatch.setattr(CatalogScanner, "scan", lambda self, progress_callback=None: fake_catalog)
    monkeypatch.setattr(
        WorkshopCrawler,
        "crawl_all",
        lambda self, progress_callback=None: [
            {
                "title": "Bài 1: Giới thiệu",
                "url": "https://000001.awsstudygroup.com/vi/1-intro/",
                "level": 1,
                "html": "<div id='body-inner'><h1>Bài 1: Giới thiệu</h1><p>Nội dung thử nghiệm</p></div>",
                "images_count": 0,
            }
        ],
    )

    def fake_convert_pdf(self, html_path, pdf_path, title=None):
        pdf_path.write_bytes(b"%PDF-1.4 fake pdf content")
        return True

    monkeypatch.setattr(PDFGenerator, "convert_html_to_pdf", fake_convert_pdf)

    cm = CrawlManager(output_dir=tmp_path)
    summary = cm.run_workshops(category_slug="1-explore", languages=["vi"], output_format="both")
    assert summary["status"] == "success"
    assert summary["processed"] == 1
    assert summary["failed"] == 0
    assert (tmp_path / "INDEX.md").exists()
    assert state_file.exists()
    state = cm.get_state()
    assert len(state["completed_workshops"]) == 1
    assert state["completed_workshops"][0]["id"] == "000001"


# ---------------------------------------------------------------------------
# 7. Web API & Security Tests
# ---------------------------------------------------------------------------

def test_web_routes_and_security(tmp_path, monkeypatch):
    monkeypatch.setattr("fcaj_crawler.runner.STATE_FILE", tmp_path / "crawl_state.json")
    monkeypatch.setattr(manager, "output_dir", tmp_path)
    ws_dir = tmp_path / "workshops" / "000004_Compute_(EC2)"
    ws_dir.mkdir(parents=True)
    md_file = ws_dir / "000004_Compute_(EC2)_VI.md"
    pdf_file = ws_dir / "000004_Compute_(EC2)_VI.pdf"
    md_file.write_text("# Xin chào AWS\n", encoding="utf-8")
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    # Create a sibling directory with matching prefix to test partial-prefix path traversal defense
    sibling_dir = tmp_path.parent / (tmp_path.name + "_secret")
    sibling_dir.mkdir(exist_ok=True)
    secret_file = sibling_dir / "secret.txt"
    secret_file.write_text("top secret", encoding="utf-8")

    client = app.test_client()

    # Index page
    r_idx = client.get("/")
    assert r_idx.status_code == 200

    # Status API
    r_status = client.get("/api/status")
    assert r_status.status_code == 200
    assert "is_running" in r_status.get_json()

    # Downloads API - must return forward-slash POSIX paths even on Windows
    r_dl = client.get("/api/downloads")
    assert r_dl.status_code == 200
    files = r_dl.get_json()["files"]
    assert len(files) == 2
    for f in files:
        assert "\\" not in f["relative_path"]

    # Preview MD renders HTML view by default, and raw markdown with ?raw=1
    md_rel = next(f["relative_path"] for f in files if f["filename"].endswith(".md"))
    r_prev = client.get(f"/preview/{md_rel}")
    assert r_prev.status_code == 200
    assert "text/html" in r_prev.content_type.lower()
    r_prev_raw = client.get(f"/preview/{md_rel}?raw=1")
    assert r_prev_raw.status_code == 200
    assert "charset=utf-8" in r_prev_raw.content_type.lower()
    r_prev_raw.close()

    # Download PDF
    pdf_rel = next(f["relative_path"] for f in files if f["filename"].endswith(".pdf"))
    r_get_pdf = client.get(f"/download/{pdf_rel}")
    assert r_get_pdf.status_code == 200
    r_get_pdf.close()

    # Download ZIP (Markdown + images)
    img_dir = ws_dir / "images"
    img_dir.mkdir(exist_ok=True)
    (img_dir / "step1.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    r_zip = client.get(f"/download-zip/{md_rel}")
    assert r_zip.status_code == 200
    assert "application/zip" in r_zip.content_type.lower()
    r_zip.close()

    # Delete file via API
    r_del = client.delete(f"/api/downloads/{md_rel}")
    assert r_del.status_code == 200
    assert not md_file.exists()

    # Requesting a directory instead of a file -> 404 (not 500 IsADirectoryError)
    r_dir = client.get("/download/workshops")
    assert r_dir.status_code == 404

    # Path traversal attempt to sibling prefix directory -> 403
    r_trav = client.get(f"/download/../{sibling_dir.name}/secret.txt")
    assert r_trav.status_code == 403

    # Change output directory via API
    custom_out = tmp_path / "custom_folder"
    r_set_dir = client.post("/api/output-dir", json={"output_dir": str(custom_out)})
    assert r_set_dir.status_code == 200
    assert Path(r_set_dir.get_json()["output_dir"]) == custom_out.resolve()
    assert custom_out.is_dir()
    r_get_dir = client.get("/api/output-dir")
    assert r_get_dir.status_code == 200
    assert Path(r_get_dir.get_json()["output_dir"]) == custom_out.resolve()


# ---------------------------------------------------------------------------
# 8. CLI Subprocess UTF-8 Smoke Tests
# ---------------------------------------------------------------------------

def test_cli_list_utf8_on_windows():
    res = subprocess.run(
        [sys.executable, str(WORKSPACE_ROOT / "run_crawler.py"), "list"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert res.returncode == 0
    assert "Tổng số: 127 workshops" in res.stdout


def test_manage_ec2_budget_graceful_fallback():
    res = subprocess.run(
        [sys.executable, str(WORKSPACE_ROOT / "deploy" / "manage_ec2.py"), "budget"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert res.returncode == 0
    assert "$20.00 cho 3 tháng" in res.stdout
