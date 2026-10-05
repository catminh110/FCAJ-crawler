"""
Markdown exporter: converts crawled workshop chapters into clean, portable Markdown.

Output layout per workshop (inside output_fcaj/workshops/<id>_<title>/):

    README.md                 -> Index: metadata + table of contents linking to chapters
    <id>_<title>_<LANG>.md    -> Whole workshop in ONE markdown file
    chapters_<lang>/
        00-<slug>.md          -> One file per chapter
        01-<slug>.md
    images/                   -> Shared images (already downloaded by the crawler)

A global index is also written at output_fcaj/INDEX.md listing every exported workshop.
"""

import datetime
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Dict, List

from bs4 import BeautifulSoup
from markdownify import MarkdownConverter

logger = logging.getLogger(__name__)


class _FCAJConverter(MarkdownConverter):
    """markdownify converter tuned for the Hugo 'learn' theme used by awsstudygroup.com."""

    def __init__(self, image_prefix: str = "", **options):
        self.image_prefix = image_prefix
        super().__init__(**options)

    def convert_img(self, el, text, *args, **kwargs):
        src = el.get("src") or ""
        alt = (el.get("alt") or "").replace("\n", " ").strip()
        if src.startswith("images/") and self.image_prefix:
            src = self.image_prefix + src
        return f"\n\n![{alt}]({src})\n\n"


def _code_language(el):
    """Detect fenced-code language from class="language-xxx" on <pre> or nested <code>."""
    candidates = [el] + el.find_all("code", limit=1)
    for node in candidates:
        for cls in node.get("class", []) or []:
            if cls.startswith("language-"):
                return cls[len("language-"):]
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

    # Drop heading anchor ids noise isn't needed; markdownify ignores ids anyway.
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
        safe_title = re.sub(r'[\\/*?:"<>|]', "", title)
        safe_title = re.sub(r"\s+", "_", safe_title).strip(" ._")[:60]
        full_name = f"{ws_id}_{safe_title}_{self.lang.upper()}.md"
        readme_text = (
            f"# {title}\n\n{meta_block}\n"
            f"📄 Bản gộp 1 file: " +
            " · ".join(f"[{l.upper()}]({ws_id}_{safe_title}_{l.upper()}.md)" for l in sorted(existing_sections)) +
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
            title_line = readme.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
            category, chapters = "", ""
            for meta_file in sorted(d.glob("metadata_*.json")):
                try:
                    m = json.loads(meta_file.read_text(encoding="utf-8"))
                    category = m.get("category", category)
                    chapters = m.get("chapters_count", chapters)
                except Exception:
                    pass
            files = sorted(f.name for f in d.glob(f"{ws_id}_*.md"))
            pdfs = sorted(f.name for f in d.glob("*.pdf"))
            links = " ".join(f"[MD-{f.rsplit('_', 1)[-1][:-3]}](workshops/{d.name}/{f})" for f in files)
            links += " " + " ".join(f"[PDF-{f.rsplit('_', 1)[-1][:-4]}](workshops/{d.name}/{f})" for f in pdfs)
            rows.append(f"| `{ws_id}` | [{title_line}](workshops/{d.name}/README.md) | {category} | {chapters} | {links.strip()} |")

    text = (
        "# FCAJ – Kho tài liệu đã thu thập\n\n"
        f"Cập nhật: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} · Tổng: **{len(rows)}** workshop\n\n"
        "| ID | Workshop | Danh mục | Chương | Tệp |\n|---|---|---|---|---|\n" +
        "\n".join(rows) + "\n"
    )
    path = output_dir / "INDEX.md"
    path.write_text(text, encoding="utf-8")
    return path
