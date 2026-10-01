import datetime
import html
import json
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


BOOK_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  --primary: #FF9900;
  --primary-dark: #EC7211;
  --secondary: #232F3E;
  --dark-bg: #0F172A;
  --text-main: #1E293B;
  --text-muted: #64748B;
  --border-color: #E2E8F0;
  --code-bg: #1E293B;
  --callout-bg: #F8FAFC;
}

@page {
  size: A4;
  margin: 18mm 15mm 20mm 15mm;
  @bottom-right {
    content: "Trang " counter(page);
    font-family: 'Inter', sans-serif;
    font-size: 8pt;
    color: #64748B;
  }
  @bottom-left {
    content: "AWS Study Group - The First Cloud Journey";
    font-family: 'Inter', sans-serif;
    font-size: 8pt;
    color: #94A3B8;
  }
}

* {
  box-sizing: border-box;
}

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: var(--text-main);
  background: #FFFFFF;
  line-height: 1.65;
  font-size: 10.5pt;
  margin: 0;
  padding: 0;
}

/* Page break utilities */
.page-break {
  page-break-after: always;
  break-after: page;
}

.no-break {
  page-break-inside: avoid;
  break-inside: avoid;
}

/* Cover Page */
.cover-page {
  min-height: 250mm;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  padding: 40px 20px;
  background: linear-gradient(135deg, #0F172A 0%, #1E293B 50%, #232F3E 100%);
  color: #FFFFFF;
  border-radius: 8px;
  margin-bottom: 20px;
  page-break-after: always;
  break-after: page;
}

.cover-badge {
  display: inline-block;
  background: rgba(255, 153, 0, 0.15);
  border: 1px solid #FF9900;
  color: #FF9900;
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 11pt;
  font-weight: 600;
  letter-spacing: 1px;
  text-transform: uppercase;
  margin-bottom: 24px;
}

.cover-title {
  font-size: 26pt;
  font-weight: 800;
  line-height: 1.25;
  color: #FFFFFF;
  margin: 0 0 20px 0;
  max-width: 90%;
}

.cover-subtitle {
  font-size: 14pt;
  font-weight: 400;
  color: #94A3B8;
  margin-bottom: 40px;
  max-width: 80%;
}

.cover-meta {
  margin-top: 50px;
  padding-top: 30px;
  border-top: 1px solid rgba(255, 255, 255, 0.15);
  display: flex;
  justify-content: space-between;
  width: 80%;
  font-size: 10pt;
  color: #CBD5E1;
}

.cover-meta-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.cover-meta-label {
  font-size: 8pt;
  text-transform: uppercase;
  color: #64748B;
  letter-spacing: 0.5px;
}

/* Table of Contents */
.toc-container {
  padding: 20px 0;
  page-break-after: always;
  break-after: page;
}

.toc-title {
  font-size: 20pt;
  font-weight: 800;
  color: var(--secondary);
  border-bottom: 3px solid var(--primary);
  padding-bottom: 8px;
  margin-bottom: 25px;
}

.toc-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.toc-item {
  margin-bottom: 12px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  border-bottom: 1px dotted #CBD5E1;
  padding-bottom: 4px;
}

.toc-item a {
  text-decoration: none;
  color: #1E293B;
  font-weight: 600;
  font-size: 11pt;
  transition: color 0.2s;
}

.toc-item.level-2 {
  padding-left: 20px;
}

.toc-item.level-2 a {
  font-weight: 400;
  font-size: 10pt;
  color: #475569;
}

/* Main Content Styling */
.chapter {
  margin-bottom: 40px;
  page-break-after: always;
  break-after: page;
}

.chapter-header {
  border-left: 5px solid var(--primary);
  padding-left: 15px;
  margin: 30px 0 20px 0;
}

.chapter-badge {
  font-size: 9pt;
  font-weight: 700;
  color: var(--primary-dark);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.chapter-title {
  font-size: 18pt;
  font-weight: 800;
  color: var(--secondary);
  margin: 4px 0;
}

.chapter-source {
  font-size: 8.5pt;
  color: var(--text-muted);
}

.chapter-source a {
  color: var(--text-muted);
  text-decoration: none;
}

/* Typography & Markdown inside body */
h1, h2, h3, h4, h5, h6 {
  color: var(--secondary);
  font-weight: 700;
  margin-top: 1.5em;
  margin-bottom: 0.5em;
  page-break-after: avoid;
  break-after: avoid;
}

h1 { font-size: 16pt; border-bottom: 1px solid var(--border-color); padding-bottom: 6px; }
h2 { font-size: 14pt; }
h3 { font-size: 12pt; }
h4 { font-size: 11pt; }

p {
  margin: 0.8em 0;
}

a {
  color: #0284C7;
  text-decoration: underline;
  word-break: break-all;
}

/* Blockquotes & Callouts */
blockquote {
  margin: 1.2em 0;
  padding: 12px 18px;
  background-color: var(--callout-bg);
  border-left: 4px solid var(--primary);
  border-radius: 4px;
  font-size: 10pt;
  page-break-inside: avoid;
  break-inside: avoid;
}

blockquote p {
  margin: 0.4em 0;
}

/* Code Blocks */
pre {
  background-color: #1E293B !important;
  color: #F8FAFC !important;
  padding: 12px 16px;
  border-radius: 6px;
  overflow-x: auto;
  font-family: 'JetBrains Mono', Consolas, Monaco, monospace;
  font-size: 9pt;
  line-height: 1.5;
  border: 1px solid #334155;
  page-break-inside: avoid;
  break-inside: avoid;
  margin: 1.2em 0;
  white-space: pre-wrap;
  word-break: break-word;
}

code {
  font-family: 'JetBrains Mono', Consolas, Monaco, monospace;
  font-size: 9pt;
  background-color: #F1F5F9;
  color: #E11D48;
  padding: 2px 6px;
  border-radius: 4px;
}

pre code {
  background-color: transparent !important;
  color: inherit !important;
  padding: 0;
}

/* Tables */
table {
  width: 100%;
  border-collapse: collapse;
  margin: 1.5em 0;
  font-size: 9.5pt;
  page-break-inside: avoid;
  break-inside: avoid;
}

th, td {
  border: 1px solid var(--border-color);
  padding: 8px 12px;
  text-align: left;
  vertical-align: top;
}

th {
  background-color: #F1F5F9;
  color: var(--secondary);
  font-weight: 700;
}

tr:nth-child(even) {
  background-color: #F8FAFC;
}

/* Images */
img {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 16px auto;
  border-radius: 6px;
  border: 1px solid var(--border-color);
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  page-break-inside: avoid;
  break-inside: avoid;
}

/* Lists */
ul, ol {
  padding-left: 24px;
  margin: 0.8em 0;
}

li {
  margin-bottom: 0.4em;
}

/* Notepads and tips from Hugo learn theme */
.notices {
  margin: 1.2em 0;
  padding: 12px 18px;
  border-radius: 6px;
  border-left: 4px solid #3B82F6;
  background: #EFF6FF;
  page-break-inside: avoid;
  break-inside: avoid;
}

.notices.warning {
  border-color: #EF4444;
  background: #FEF2F2;
}

.notices.tip {
  border-color: #10B981;
  background: #ECFDF5;
}

.notices.note {
  border-color: #F59E0B;
  background: #FFFBEB;
}
"""


class WorkshopProcessor:
    """Assembles crawled chapters into a comprehensive, beautifully styled e-book HTML."""

    def __init__(self, workshop_info: Dict, chapters: List[Dict], lang: str = "vi", output_dir: Path = None):
        self.workshop = workshop_info
        self.chapters = chapters
        self.lang = lang.lower()
        self.output_dir = output_dir or Path("output_fcaj")
        self.ws_dir = self.output_dir / "workshops" / f"{self.workshop['id']}_{self._sanitize(self.workshop['title'])}"
        self.ws_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize(self, name: str) -> str:
        import re
        clean = re.sub(r'[\\/*?:"<>|]', "", name)
        clean = re.sub(r'\s+', "_", clean).strip(" ._")
        return clean[:60] if clean else "workshop"

    def generate_book_html(self) -> Path:
        """Builds the full multi-chapter HTML document with cover page and TOC."""
        ws_id = self.workshop["id"]
        title = self.workshop["title"]
        category = self.workshop.get("category", "The First Cloud Journey")
        source_url = self.workshop.get("url", f"https://{ws_id}.awsstudygroup.com")
        now_str = datetime.datetime.now().strftime("%d/%m/%Y")
        lang_label = "Tiếng Việt" if self.lang == "vi" else "English"

        # Build TOC items
        toc_items_html = []
        for idx, ch in enumerate(self.chapters):
            anchor = f"ch-{idx+1}"
            ch_title = html.escape(ch.get("title", f"Bài {idx+1}"))
            level_cls = f"level-{ch.get('level', 1)}"
            toc_items_html.append(
                f'<li class="toc-item {level_cls}">'
                f'  <a href="#{anchor}">{ch_title}</a>'
                f'</li>'
            )
        toc_html = "\n".join(toc_items_html)

        # Build Chapter contents
        chapters_content_html = []
        for idx, ch in enumerate(self.chapters):
            anchor = f"ch-{idx+1}"
            ch_title = html.escape(ch.get("title", f"Bài {idx+1}"))
            ch_url = ch.get("url", "")
            raw_html = ch.get("html", "")

            chapter_block = f"""
            <section class="chapter" id="{anchor}">
              <div class="chapter-header">
                <div class="chapter-badge">CHƯƠNG {idx+1}</div>
                <h2 class="chapter-title">{ch_title}</h2>
                <div class="chapter-source">Nguồn: <a href="{ch_url}" target="_blank">{ch_url}</a></div>
              </div>
              <div class="chapter-body">
                {raw_html}
              </div>
            </section>
            """
            chapters_content_html.append(chapter_block)

        all_chapters_html = "\n".join(chapters_content_html)

        # Full HTML template
        full_html = f"""<!DOCTYPE html>
<html lang="{self.lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)} - Workshop {ws_id}</title>
  <style>
    {BOOK_CSS}
  </style>
</head>
<body>

  <!-- Cover Page -->
  <div class="cover-page">
    <div class="cover-badge">{html.escape(category)}</div>
    <h1 class="cover-title">{html.escape(title)}</h1>
    <div class="cover-subtitle">Tài liệu hướng dẫn thực hành AWS Study Group • Workshop #{ws_id}</div>
    
    <div class="cover-meta">
      <div class="cover-meta-item">
        <span class="cover-meta-label">Ngôn ngữ</span>
        <span>{lang_label}</span>
      </div>
      <div class="cover-meta-item">
        <span class="cover-meta-label">Tổng số chương</span>
        <span>{len(self.chapters)} bài học</span>
      </div>
      <div class="cover-meta-item">
        <span class="cover-meta-label">Ngày xuất bản</span>
        <span>{now_str}</span>
      </div>
      <div class="cover-meta-item">
        <span class="cover-meta-label">Trang gốc</span>
        <span><a href="{source_url}" style="color: #FF9900; text-decoration: none;">{ws_id}.awsstudygroup.com</a></span>
      </div>
    </div>
  </div>

  <!-- Table of Contents -->
  <div class="toc-container">
    <h2 class="toc-title">Mục Lục</h2>
    <ul class="toc-list">
      {toc_html}
    </ul>
  </div>

  <!-- Chapters Content -->
  <main class="content-body">
    {all_chapters_html}
  </main>

</body>
</html>
"""

        book_path = self.ws_dir / f"book_{self.lang}.html"
        with open(book_path, "w", encoding="utf-8") as f:
            f.write(full_html)

        # Save metadata
        meta_path = self.ws_dir / f"metadata_{self.lang}.json"
        metadata = {
            "id": ws_id,
            "title": title,
            "category": category,
            "source_url": source_url,
            "language": self.lang,
            "chapters_count": len(self.chapters),
            "generated_at": datetime.datetime.now().isoformat(),
            "chapters": [{"title": c.get("title"), "url": c.get("url")} for c in self.chapters]
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        logger.info("[%s] Generated book HTML at: %s", ws_id, book_path)
        return book_path
