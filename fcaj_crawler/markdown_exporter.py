"""
Markdown exporter: converts crawled workshop chapters into clean, portable Markdown,
and builds combined single-file bundles (Markdown & HTML/PDF) for offline reading.

Output layout per workshop (inside output_fcaj/workshops/<id>_<title>/):

    README.md                 -> Index: metadata + table of contents linking to chapters
    <id>_<title>_<LANG>.md    -> Whole workshop in ONE markdown file
    chapters_<lang>/
        00-<slug>.md          -> One file per chapter
        01-<slug>.md
    images/                   -> Shared images (already downloaded by the crawler)

Global outputs in output_fcaj/:
    INDEX.md                  -> Global index table of all exported workshops
    FCAJ_ALL_<LANG>.md        -> Single combined Markdown file containing all workshops
    FCAJ_ALL_<LANG>.pdf       -> Single combined PDF book containing all workshops
"""

import datetime
import html as html_lib
import io
import json
import logging
import re
import unicodedata
import zipfile
from pathlib import Path
from typing import Callable, Dict, List, Optional

from bs4 import BeautifulSoup
from markdownify import MarkdownConverter

from fcaj_crawler.config import sanitize_filename

logger = logging.getLogger(__name__)


class _FCAJConverter(MarkdownConverter):
    """markdownify converter tuned for the Hugo 'learn' theme used by awsstudygroup.com."""

    def __init__(self, image_prefix: str = "", **options):
        self.image_prefix = image_prefix
        super().__init__(**options)

    def convert_img(self, el, text, *args, **kwargs):
        src = el.get("src") or ""
        alt = (el.get("alt") or "").replace("\n", " ").replace("[", "\\[").replace("]", "\\]").strip()
        if src.startswith("images/") and self.image_prefix:
            src = self.image_prefix + src
        return f"\n\n![{alt}]({src})\n\n"


def _code_language(el):
    """Detect fenced-code language from class="language-xxx" or data-lang on <pre> or nested <code>."""
    candidates = [el] + el.find_all("code", limit=1)
    for node in candidates:
        for cls in node.get("class", []) or []:
            if cls.startswith("language-"):
                return cls[len("language-"):]
        data_lang = node.get("data-lang")
        if data_lang:
            return str(data_lang).strip()
    return ""


def slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:max_len].strip("-") or "chapter"


def _preprocess_html(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "lxml")

    # Remove theme chrome
    for sel in ["footer.footline", "#sidebar-toggle-span", "#navigation", "script", "style"]:
        for node in soup.select(sel):
            node.decompose()

    # Hugo notices -> blockquote with a label, so they survive conversion
    labels = {"info": "ℹ️ **Info**", "note": "📝 **Note**", "tip": "💡 **Tip**", "warning": "⚠️ **Warning**"}
    for div in soup.select("div.notices"):
        kind = next((c for c in div.get("class", []) if c in labels), "info")
        bq = soup.new_tag("blockquote")
        label = soup.new_tag("p")
        label.string = labels[kind]
        bq.append(label)
        for child in list(div.children):
            bq.append(child.extract())
        div.replace_with(bq)

    return soup


def html_to_markdown(html: str, image_prefix: str = "") -> str:
    soup = _preprocess_html(html)
    body = soup.find("div", id="body-inner") or soup.body or soup
    md = _FCAJConverter(
        image_prefix=image_prefix,
        heading_style="ATX",
        bullets="-",
        code_language_callback=_code_language,
        escape_underscores=False,
        escape_asterisks=False,
    ).convert_soup(body)
    # Collapse 3+ blank lines
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip() + "\n"


def _demote_headings(md: str, levels: int = 1) -> str:
    """Shift headings down so chapters nest under the book title in the single-file export."""
    def repl(m):
        hashes = m.group(1)
        return "#" * min(6, len(hashes) + levels) + m.group(2)
    out, in_fence = [], False
    for line in md.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence:
            line = re.sub(r"^(#{1,6})(\s)", repl, line)
        out.append(line)
    return "\n".join(out)


def _md_link_path(path_str: str) -> str:
    """Encodes parentheses in Markdown link paths so folder names like _(EC2) don't break [text](url)."""
    return path_str.replace("(", "%28").replace(")", "%29")


class MarkdownExporter:
    def __init__(self, workshop_info: Dict, chapters: List[Dict], workshop_dir: Path, lang: str = "vi"):
        self.ws = workshop_info
        self.chapters = chapters
        self.dir = workshop_dir
        self.lang = lang.lower()

    def export(self) -> Path:
        ws_id = self.ws["id"]
        title = self.ws["title"]
        source = self.ws.get("url", "")
        category = self.ws.get("category", "")
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        chapters_dir = self.dir / f"chapters_{self.lang}"
        chapters_dir.mkdir(parents=True, exist_ok=True)
        for old in chapters_dir.glob("*.md"):
            old.unlink()

        toc_lines, full_parts, chapter_files = [], [], []

        for idx, ch in enumerate(self.chapters):
            ch_title = (ch.get("title") or f"Chapter {idx}").strip()
            fname = f"{idx:02d}-{slugify(ch_title)}.md"
            body_md = html_to_markdown(ch.get("html", ""), image_prefix="../")

            # Ensure each chapter file starts with a title heading
            if not body_md.lstrip().startswith("# "):
                body_md = f"# {ch_title}\n\n{body_md}"

            header = f"> Nguồn: <{ch.get('url', '')}>  \n> Workshop [{ws_id}](../README.md) · {title}\n\n"
            (chapters_dir / fname).write_text(header + body_md, encoding="utf-8")
            chapter_files.append(fname)

            indent = "  " * max(0, ch.get("level", 1) - 1)
            toc_lines.append(f"{indent}- [{ch_title}](chapters_{self.lang}/{fname})")

            # Single-file version: images are relative to workshop dir
            single_md = html_to_markdown(ch.get("html", ""), image_prefix="")
            if not single_md.lstrip().startswith("# "):
                single_md = f"# {ch_title}\n\n{single_md}"
            full_parts.append(f"<a id=\"ch-{idx}\"></a>\n\n" + _demote_headings(single_md) +
                              f"\n\n*Nguồn: <{ch.get('url', '')}>*\n")

        # Add prev/next navigation now that all filenames are known
        for i, fname in enumerate(chapter_files):
            nav = []
            if i > 0:
                nav.append(f"[← Bài trước]({chapter_files[i-1]})")
            nav.append("[Mục lục](../README.md)")
            if i < len(chapter_files) - 1:
                nav.append(f"[Bài tiếp →]({chapter_files[i+1]})")
            p = chapters_dir / fname
            p.write_text(p.read_text(encoding="utf-8").rstrip() + "\n\n---\n\n" + " · ".join(nav) + "\n",
                         encoding="utf-8")

        meta_block = (
            f"| | |\n|---|---|\n"
            f"| **ID** | `{ws_id}` |\n"
            f"| **Danh mục** | {category} |\n"
            f"| **Ngôn ngữ** | {self.lang.upper()} |\n"
            f"| **Số chương** | {len(self.chapters)} |\n"
            f"| **Trang gốc** | <{source}> |\n"
            f"| **Cập nhật** | {now} |\n"
        )

        # README.md (index) - merge sections for multiple languages
        readme = self.dir / "README.md"
        section = f"## Mục lục ({self.lang.upper()})\n\n" + "\n".join(toc_lines) + "\n"
        existing_sections = {}
        if readme.exists():
            for m in re.finditer(r"<!-- lang:(\w+) -->\n(.*?)<!-- /lang -->", readme.read_text(encoding="utf-8"), re.S):
                existing_sections[m.group(1)] = m.group(2)
        existing_sections[self.lang] = section
        safe_title = sanitize_filename(title)
        full_name = f"{ws_id}_{safe_title}_{self.lang.upper()}.md"
        readme_text = (
            f"# {title}\n\n{meta_block}\n"
            f"📄 Bản gộp 1 file: " +
            " · ".join(f"[{l.upper()}]({_md_link_path(f'{ws_id}_{safe_title}_{l.upper()}.md')})" for l in sorted(existing_sections)) +
            "\n\n" +
            "\n".join(f"<!-- lang:{l} -->\n{s}<!-- /lang -->\n" for l, s in sorted(existing_sections.items()))
        )
        readme.write_text(readme_text, encoding="utf-8")

        # Single combined file
        full_toc = "\n".join(
            f"{'  ' * max(0, c.get('level', 1) - 1)}- [{(c.get('title') or '').strip()}](#ch-{i})"
            for i, c in enumerate(self.chapters)
        )
        full_text = (
            f"# {title}\n\n{meta_block}\n## Mục lục\n\n{full_toc}\n\n---\n\n" +
            "\n\n---\n\n".join(full_parts)
        )
        full_path = self.dir / full_name
        full_path.write_text(full_text, encoding="utf-8")

        meta = {
            "id": ws_id, "title": title, "category": category, "source_url": source,
            "language": self.lang, "chapters_count": len(self.chapters),
            "generated_at": datetime.datetime.now().isoformat(),
            "chapters": [{"title": c.get("title"), "url": c.get("url"), "file": f"chapters_{self.lang}/{f}"}
                         for c, f in zip(self.chapters, chapter_files)],
        }
        (self.dir / f"metadata_{self.lang}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info("[%s] Markdown exported: %s (+ %d chapter files)", ws_id, full_path.name, len(chapter_files))
        return full_path


def build_global_index(output_dir: Path) -> Path:
    """Write output_fcaj/INDEX.md listing every workshop that has a README.md."""
    ws_root = output_dir / "workshops"
    rows = []
    if ws_root.exists():
        for d in sorted(p for p in ws_root.iterdir() if p.is_dir()):
            readme = d / "README.md"
            if not readme.exists():
                continue
            ws_id = d.name.split("_")[0]
            lines = readme.read_text(encoding="utf-8").splitlines()
            title_line = lines[0].lstrip("# ").strip() if lines else ws_id
            title_line = title_line.replace("|", "\\|")
            category, chapters = "", ""
            for meta_file in sorted(d.glob("metadata_*.json")):
                try:
                    m = json.loads(meta_file.read_text(encoding="utf-8"))
                    category = str(m.get("category", category)).replace("|", "\\|")
                    chapters = m.get("chapters_count", chapters)
                except Exception:
                    pass
            files = sorted(f.name for f in d.glob(f"{ws_id}_*.md"))
            pdfs = sorted(f.name for f in d.glob("*.pdf"))
            links = " ".join(
                f"[MD-{f.rsplit('_', 1)[-1][:-3]}]({_md_link_path(f'workshops/{d.name}/{f}')})" for f in files
            )
            links += " " + " ".join(
                f"[PDF-{f.rsplit('_', 1)[-1][:-4]}]({_md_link_path(f'workshops/{d.name}/{f}')})" for f in pdfs
            )
            readme_link = _md_link_path(f"workshops/{d.name}/README.md")
            rows.append(f"| `{ws_id}` | [{title_line}]({readme_link}) | {category} | {chapters} | {links.strip()} |")

    text = (
        "# FCAJ – Kho tài liệu đã thu thập\n\n"
        f"Cập nhật: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} · Tổng: **{len(rows)}** workshop\n\n"
        "| ID | Workshop | Danh mục | Chương | Tệp |\n|---|---|---|---|---|\n" +
        "\n".join(rows) + "\n"
    )
    path = output_dir / "INDEX.md"
    path.write_text(text, encoding="utf-8")
    return path


def _simple_md_to_html(md_text: str) -> str:
    """Fallback converter from Markdown to basic HTML when book_<lang>.html was not previously generated."""
    lines = md_text.splitlines()
    out = []
    in_code = False
    for line in lines:
        if line.lstrip().startswith("```"):
            if not in_code:
                out.append("<pre><code>")
                in_code = True
            else:
                out.append("</code></pre>")
                in_code = False
            continue
        if in_code:
            out.append(html_lib.escape(line))
            continue
        m_h = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m_h:
            lvl = len(m_h.group(1))
            out.append(f"<h{lvl}>{html_lib.escape(m_h.group(2))}</h{lvl}>")
            continue
        m_img = re.match(r"^!\[(.*?)\]\((.*?)\)$", line.strip())
        if m_img:
            alt, src = m_img.group(1), m_img.group(2).replace("%28", "(").replace("%29", ")")
            out.append(f'<img src="{html_lib.escape(src)}" alt="{html_lib.escape(alt)}">')
            continue
        if line.strip():
            out.append(f"<p>{html_lib.escape(line)}</p>")
    if in_code:
        out.append("</code></pre>")
    return "\n".join(out)


def build_combined_bundle(
    output_dir: Path,
    lang: str = "vi",
    output_format: str = "both",
    workshop_ids: Optional[List[str]] = None,
    pdf_generator=None,
    progress_callback: Optional[Callable[[str, int], None]] = None,
) -> Dict:
    """
    Combines all downloaded workshops (or selected workshop_ids) for `lang` into:
      - output_dir / FCAJ_ALL_<LANG>.md   (when output_format in ('md', 'both'))
      - output_dir / FCAJ_ALL_<LANG>.pdf  (when output_format in ('pdf', 'both'))
    """
    from fcaj_crawler.pdf_generator import PDFGenerator
    from fcaj_crawler.processor import BOOK_CSS

    lang = lang.lower()
    ws_root = output_dir / "workshops"
    norm_ids = {wid.strip() for wid in workshop_ids if wid.strip()} if workshop_ids else None

    discovered_by_id: Dict[str, Dict] = {}
    if ws_root.exists():
        for d in sorted(p for p in ws_root.iterdir() if p.is_dir()):
            ws_id = d.name.split("_")[0]
            if norm_ids and ws_id not in norm_ids:
                continue
            meta_file = d / f"metadata_{lang}.json"
            md_candidates = sorted(d.glob(f"{ws_id}_*_{lang.upper()}.md"))
            pdf_candidates = sorted(d.glob(f"{ws_id}_*_{lang.upper()}.pdf"))
            book_html = d / f"book_{lang}.html"

            if not meta_file.exists() and not md_candidates and not book_html.exists() and not pdf_candidates:
                continue

            meta = {}
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}

            title = meta.get("title") or d.name.split("_", 1)[-1].replace("_", " ")
            category = meta.get("category") or "AWS Cloud Journey"
            source_url = meta.get("source_url") or f"https://{ws_id}.awsstudygroup.com"
            chapters_meta = meta.get("chapters") or []

            entry = {
                "id": ws_id,
                "dir": d,
                "folder": d.name,
                "title": title,
                "category": category,
                "source_url": source_url,
                "chapters_meta": chapters_meta,
                "md_file": md_candidates[0] if md_candidates else None,
                "pdf_file": pdf_candidates[0] if pdf_candidates else None,
                "book_html": book_html if book_html.exists() else None,
            }
            # If duplicate folders exist for the same ws_id, prefer the one that has exported PDF/MD
            prev = discovered_by_id.get(ws_id)
            if not prev or (entry["pdf_file"] and not prev["pdf_file"]) or (entry["md_file"] and not prev["md_file"]):
                discovered_by_id[ws_id] = entry

    discovered = [discovered_by_id[k] for k in sorted(discovered_by_id.keys())]

    if not discovered:
        return {
            "status": "empty",
            "workshops_count": 0,
            "message": f"Chưa có dữ liệu workshop nào cho ngôn ngữ {lang.upper()} để gộp.",
            "files": [],
        }

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    produced_files: List[str] = []
    total_chapters = sum(max(1, len(w["chapters_meta"])) for w in discovered)

    # 1. Build Master Markdown Bundle (FCAJ_ALL_<LANG>.md)
    if output_format in ("md", "both"):
        if progress_callback:
            progress_callback(f"Đang gộp {len(discovered)} workshop vào 1 file Markdown ({lang.upper()})...", 30)

        master_toc = []
        ws_blocks = []

        for idx, item in enumerate(discovered):
            ws_id = item["id"]
            title = item["title"]
            category = item["category"]
            source_url = item["source_url"]
            folder = item["folder"]

            master_toc.append(f"{idx + 1}. **[#{ws_id} - {title}](#workshop-{ws_id})** · *{category}*")

            if item["md_file"] and item["md_file"].exists():
                raw_md = item["md_file"].read_text(encoding="utf-8")
            elif item["book_html"] and item["book_html"].exists():
                raw_md = html_to_markdown(item["book_html"].read_text(encoding="utf-8"))
            else:
                raw_md = f"# {title}\n"

            # Rewrite relative image links: ](images/xxx) -> ](workshops/<folder>/images/xxx)
            img_prefix = _md_link_path(f"workshops/{folder}/images/")
            rewritten_md = re.sub(r"\]\(images/", f"]({img_prefix}", raw_md)
            # Namespace internal chapter anchors: (#ch-0) -> (#ws-000001-ch-0) and id="ch-0" -> id="ws-000001-ch-0"
            rewritten_md = re.sub(r"\(#ch-(\d+)\)", f"(#ws-{ws_id}-ch-\\1)", rewritten_md)
            rewritten_md = re.sub(r'id="ch-(\d+)"', f'id="ws-{ws_id}-ch-\\1"', rewritten_md)

            block = (
                f'<a id="workshop-{ws_id}"></a>\n\n'
                f"{rewritten_md.strip()}\n"
            )
            ws_blocks.append(block)

        bundle_md_text = (
            f"# TỔNG HỢP TÀI LIỆU AWS CLOUD JOURNEY ({lang.upper()})\n\n"
            f"- **Số lượng workshop**: {len(discovered)}\n"
            f"- **Tổng số chương**: {total_chapters}\n"
            f"- **Ngôn ngữ**: {lang.upper()}\n"
            f"- **Cập nhật**: {now_str}\n"
            f"- **Nguồn**: <https://cloudjourney.awsstudygroup.com>\n\n"
            f"## Danh mục Workshop trong tệp này\n\n"
            + "\n".join(master_toc)
            + "\n\n---\n\n"
            + "\n\n---\n\n".join(ws_blocks)
            + "\n"
        )

        bundle_md_path = output_dir / f"FCAJ_ALL_{lang.upper()}.md"
        bundle_md_path.write_text(bundle_md_text, encoding="utf-8")
        produced_files.append(str(bundle_md_path))
        logger.info("Combined Markdown bundle written to %s (%d workshops)", bundle_md_path, len(discovered))

    # 2. Build Master PDF Bundle (FCAJ_ALL_<LANG>.pdf)
    if output_format in ("pdf", "both"):
        if progress_callback:
            progress_callback(f"Đang biên soạn HTML & kết xuất PDF tổng hợp ({len(discovered)} workshop)...", 65)

        toc_items_html = []
        sections_html = []

        for w_idx, item in enumerate(discovered):
            ws_id = item["id"]
            title = item["title"]
            category = item["category"]
            source_url = item["source_url"]
            folder = item["folder"]
            ws_anchor = f"ws-{ws_id}"

            toc_items_html.append(
                f'<li class="toc-item">'
                f'  <a href="#{ws_anchor}">#{html_lib.escape(ws_id)} — {html_lib.escape(title)}</a>'
                f'  <span style="font-size:9pt;color:#64748B;">{html_lib.escape(category)}</span>'
                f'</li>'
            )

            # Extract chapters HTML
            ws_chapters_html = []
            if item["book_html"] and item["book_html"].exists():
                soup = BeautifulSoup(item["book_html"].read_text(encoding="utf-8"), "lxml")
                for iframe in soup.find_all("iframe"):
                    iframe.decompose()
                for img in soup.find_all("img", src=True):
                    src = img["src"]
                    if src.startswith("images/"):
                        img["src"] = f"workshops/{folder}/{src}"
                    elif src.startswith(("http://", "https://")):
                        img.decompose()
                chapters_nodes = soup.select("section.chapter")
                for c_idx, sec in enumerate(chapters_nodes):
                    sec["id"] = f"{ws_anchor}-ch-{c_idx+1}"
                    ws_chapters_html.append(str(sec))
            elif item["md_file"] and item["md_file"].exists():
                raw_md = item["md_file"].read_text(encoding="utf-8")
                rewritten_md = re.sub(r"\]\(images/", f"](workshops/{folder}/images/", raw_md)
                body_html = _simple_md_to_html(rewritten_md)
                ws_chapters_html.append(
                    f'<section class="chapter" id="{ws_anchor}-ch-1">'
                    f'  <div class="chapter-body">{body_html}</div>'
                    f'</section>'
                )

            ws_header_block = f"""
            <section class="chapter" id="{ws_anchor}">
              <div class="chapter-header">
                <div class="chapter-badge">WORKSHOP #{html_lib.escape(ws_id)} · {html_lib.escape(category)}</div>
                <h1 class="chapter-title">{html_lib.escape(title)}</h1>
                <div class="chapter-source">Nguồn: <a href="{html_lib.escape(source_url)}">{html_lib.escape(source_url)}</a></div>
              </div>
            </section>
            """
            sections_html.append(ws_header_block + "\n".join(ws_chapters_html))

        lang_label = "Tiếng Việt" if lang == "vi" else "English"
        master_html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <title>FCAJ Tổng Hợp ({lang.upper()}) - {len(discovered)} Workshops</title>
  <style>
    {BOOK_CSS}
  </style>
</head>
<body>
  <div class="cover-page">
    <div class="cover-badge">AWS STUDY GROUP · CLOUD JOURNEY</div>
    <h1 class="cover-title">Tài Liệu Tổng Hợp Cloud Journey ({lang.upper()})</h1>
    <div class="cover-subtitle">Bản gộp {len(discovered)} Workshop · {total_chapters} chương thực hành</div>
    <div class="cover-meta">
      <div class="cover-meta-item">
        <span class="cover-meta-label">Ngôn ngữ</span>
        <span>{lang_label}</span>
      </div>
      <div class="cover-meta-item">
        <span class="cover-meta-label">Số Workshop</span>
        <span>{len(discovered)} bài</span>
      </div>
      <div class="cover-meta-item">
        <span class="cover-meta-label">Tổng số chương</span>
        <span>{total_chapters} chương</span>
      </div>
      <div class="cover-meta-item">
        <span class="cover-meta-label">Ngày tạo</span>
        <span>{now_str}</span>
      </div>
    </div>
  </div>

  <div class="toc-container">
    <h2 class="toc-title">Mục Lục Tổng Hợp ({len(discovered)} Workshop)</h2>
    <ul class="toc-list">
      {"".join(toc_items_html)}
    </ul>
  </div>

  <main class="content-body">
    {"".join(sections_html)}
  </main>
</body>
</html>"""

        bundle_html_path = output_dir / f"FCAJ_ALL_{lang.upper()}.html"
        bundle_pdf_path = output_dir / f"FCAJ_ALL_{lang.upper()}.pdf"
        bundle_html_path.write_text(master_html, encoding="utf-8")

        gen = pdf_generator or PDFGenerator()
        existing_pdfs = [item for item in discovered if item.get("pdf_file") and item["pdf_file"].exists()]

        # Fast & memory-safe PDF merging when individual workshop PDFs already exist on disk
        if existing_pdfs and isinstance(gen, PDFGenerator):
            try:
                from pypdf import PdfReader, PdfWriter

                # Render missing individual PDFs first if any workshop only has book_html
                for item in discovered:
                    if not (item.get("pdf_file") and item["pdf_file"].exists()) and item.get("book_html"):
                        ws_pdf = item["dir"] / f"{item['id']}_{sanitize_filename(item['title'])}_{lang.upper()}.pdf"
                        if gen.convert_html_to_pdf(item["book_html"], ws_pdf, title=f"Workshop #{item['id']}: {item['title']}"):
                            item["pdf_file"] = ws_pdf

                # Render lightweight Master Cover + TOC PDF
                cover_toc_html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <title>FCAJ Tổng Hợp ({lang.upper()}) - Mục Lục</title>
  <style>{BOOK_CSS}</style>
</head>
<body>
  <div class="cover-page">
    <div class="cover-badge">AWS STUDY GROUP · CLOUD JOURNEY</div>
    <h1 class="cover-title">Tài Liệu Tổng Hợp Cloud Journey ({lang.upper()})</h1>
    <div class="cover-subtitle">Bản gộp {len(discovered)} Workshop · {total_chapters} chương thực hành</div>
    <div class="cover-meta">
      <div class="cover-meta-item"><span class="cover-meta-label">Ngôn ngữ</span><span>{lang_label}</span></div>
      <div class="cover-meta-item"><span class="cover-meta-label">Số Workshop</span><span>{len(discovered)} bài</span></div>
      <div class="cover-meta-item"><span class="cover-meta-label">Tổng số chương</span><span>{total_chapters} chương</span></div>
      <div class="cover-meta-item"><span class="cover-meta-label">Ngày tạo</span><span>{now_str}</span></div>
    </div>
  </div>
  <div class="toc-container">
    <h2 class="toc-title">Mục Lục Tổng Hợp ({len(discovered)} Workshop)</h2>
    <ul class="toc-list">{"".join(toc_items_html)}</ul>
  </div>
</body>
</html>"""
                cover_html_path = output_dir / f"_cover_toc_{lang}.html"
                cover_pdf_path = output_dir / f"_cover_toc_{lang}.pdf"
                cover_html_path.write_text(cover_toc_html, encoding="utf-8")

                writer = PdfWriter()
                current_page = 0

                if gen.convert_html_to_pdf(
                    cover_html_path,
                    cover_pdf_path,
                    title=f"FCAJ Cloud Journey ({lang.upper()}) — Mục Lục Tổng Hợp",
                ) and cover_pdf_path.exists():
                    reader = PdfReader(str(cover_pdf_path))
                    for page in reader.pages:
                        writer.add_page(page)
                    writer.add_outline_item("Bìa & Mục Lục Tổng Hợp", 0)
                    current_page += len(reader.pages)

                for idx, item in enumerate(discovered):
                    pfile = item.get("pdf_file")
                    if not pfile or not pfile.exists():
                        continue
                    if progress_callback and (idx % 10 == 0 or idx == len(discovered) - 1):
                        pct = 70 + int(28 * (idx + 1) / max(1, len(discovered)))
                        progress_callback(f"Đang ghép PDF [{idx + 1}/{len(discovered)}]: #{item['id']}...", pct)
                    reader = PdfReader(str(pfile))
                    start_page = current_page
                    for page in reader.pages:
                        writer.add_page(page)
                    writer.add_outline_item(f"#{item['id']} - {item['title']}", start_page)
                    current_page += len(reader.pages)

                with open(bundle_pdf_path, "wb") as out_f:
                    writer.write(out_f)
                writer.close()

                for tmp_f in (cover_html_path, cover_pdf_path):
                    try:
                        if tmp_f.exists():
                            tmp_f.unlink()
                    except Exception:
                        pass

                produced_files.append(str(bundle_pdf_path))
                logger.info("Combined PDF bundle merged to %s (%d pages)", bundle_pdf_path, current_page)
            except Exception as merge_err:
                logger.error("Failed to merge PDF bundle: %s", merge_err)
                return {
                    "status": "partial" if produced_files else "error",
                    "workshops_count": len(discovered),
                    "message": f"Không thể ghép PDF tổng hợp: {merge_err}",
                    "files": produced_files,
                }
        else:
            if gen.convert_html_to_pdf(
                bundle_html_path,
                bundle_pdf_path,
                title=f"FCAJ Cloud Journey ({lang.upper()}) — {len(discovered)} Workshops",
            ):
                produced_files.append(str(bundle_pdf_path))
                logger.info("Combined PDF bundle written to %s", bundle_pdf_path)
            else:
                return {
                    "status": "partial" if produced_files else "error",
                    "workshops_count": len(discovered),
                    "message": f"Không thể tạo PDF tổng hợp: {gen.last_error or 'Lỗi trình duyệt'}",
                    "files": produced_files,
                }

    if progress_callback:
        progress_callback(f"Đã tạo xong tệp tổng hợp ({len(discovered)} workshop)!", 100)

    return {
        "status": "success",
        "workshops_count": len(discovered),
        "chapters_count": total_chapters,
        "files": produced_files,
    }


def create_markdown_zip_bytes(md_path: Path, base_output_dir: Path) -> io.BytesIO:
    """
    Packages a Markdown file (.md) together with its referenced local images
    into an in-memory .zip archive so it can be moved to another machine with
    all images intact.
    """
    buf = io.BytesIO()
    md_abs = md_path.resolve()
    base_abs = base_output_dir.resolve()
    md_text = md_abs.read_text(encoding="utf-8", errors="replace")

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(md_abs.name, md_text.encode("utf-8"))

        if md_abs.parent == base_abs:
            # Root-level bundle file (e.g. FCAJ_ALL_VI.md) referencing workshops/<folder>/images/...
            ws_root = base_abs / "workshops"
            if ws_root.is_dir():
                matched_folders = {
                    m.replace("%28", "(").replace("%29", ")")
                    for m in re.findall(r"workshops/([^/\s)]+)/images/", md_text)
                }
                for ws_dir in sorted(p for p in ws_root.iterdir() if p.is_dir()):
                    if matched_folders and ws_dir.name not in matched_folders:
                        continue
                    img_dir = ws_dir / "images"
                    if img_dir.is_dir():
                        for img_file in sorted(img_dir.iterdir()):
                            if img_file.is_file():
                                arcname = f"workshops/{ws_dir.name}/images/{img_file.name}"
                                zf.write(img_file, arcname=arcname)
        else:
            # Single-workshop Markdown file referencing images/...
            img_dir = md_abs.parent / "images"
            if img_dir.is_dir():
                for img_file in sorted(img_dir.iterdir()):
                    if img_file.is_file():
                        zf.write(img_file, arcname=f"images/{img_file.name}")

    buf.seek(0)
    return buf

