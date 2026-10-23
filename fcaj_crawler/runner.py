import datetime
import json
import logging
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

from fcaj_crawler.config import DATA_DIR, OUTPUT_DIR, STATE_FILE
from fcaj_crawler.crawler import WorkshopCrawler
from fcaj_crawler.markdown_exporter import (
    MarkdownExporter,
    build_combined_bundle,
    build_global_index,
)
from fcaj_crawler.pdf_generator import PDFGenerator
from fcaj_crawler.processor import WorkshopProcessor
from fcaj_crawler.scanner import CatalogScanner

logger = logging.getLogger(__name__)


class CrawlManager:
    """Orchestrates the scraping, Markdown export, PDF generation, and single-file bundling pipeline."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = Path(output_dir) if output_dir else self._load_saved_output_dir()
        self.pdf_generator = PDFGenerator()
        self.is_running = False
        self.stop_requested = False
        self.current_task_info = {}
        self.logs: List[str] = []
        self._lock = threading.Lock()
        self.log_listener: Optional[Callable[[str], None]] = None

    @staticmethod
    def _load_saved_output_dir() -> Path:
        if STATE_FILE.exists():
            try:
                saved = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                custom_dir = saved.get("output_dir")
                if custom_dir:
                    p = Path(custom_dir).expanduser()
                    p.mkdir(parents=True, exist_ok=True)
                    return p
            except Exception:
                pass
        return OUTPUT_DIR

    def set_output_dir(self, new_dir: str | Path) -> Path:
        """Sets and persists a new output directory for exported files."""
        raw = str(new_dir).strip()
        if not raw:
            raise ValueError("Đường dẫn thư mục không được để trống.")
        resolved = Path(raw).expanduser().resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.output_dir = resolved
            saved = {"completed_workshops": [], "stats": {}}
            if STATE_FILE.exists():
                try:
                    saved = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                except Exception:
                    pass
            saved["output_dir"] = str(resolved)
            try:
                STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                STATE_FILE.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                logger.error("Failed to save output_dir to state file: %s", e)
        self.log(f"Đã đặt thư mục lưu trữ: {resolved}")
        return resolved

    def log(self, message: str, level: str = "INFO"):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] [{level}] {message}"
        with self._lock:
            self.logs.append(formatted)
            if len(self.logs) > 500:
                self.logs.pop(0)
        if self.log_listener:
            try:
                self.log_listener(formatted)
            except Exception:
                pass
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)

    def get_state(self) -> Dict:
        """Returns the current state and progress of the crawler."""
        with self._lock:
            state_data = {
                "is_running": self.is_running,
                "current_task": self.current_task_info,
                "recent_logs": self.logs[-50:],
                "output_dir": str(self.output_dir.resolve()),
            }
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    state_data["completed_workshops"] = saved.get("completed_workshops", [])
                    state_data["stats"] = saved.get("stats", {})
            except Exception:
                pass
        return state_data

    def _save_completed_workshop(self, ws_id: str, ws_title: str, lang: str, pdf_path: str):
        with self._lock:
            saved = {"completed_workshops": [], "stats": {}}
            if STATE_FILE.exists():
                try:
                    with open(STATE_FILE, "r", encoding="utf-8") as f:
                        saved = json.load(f)
                except Exception:
                    pass
            completed = saved.get("completed_workshops", [])
            exists = False
            for item in completed:
                if item.get("id") == ws_id and item.get("lang") == lang:
                    item["title"] = ws_title
                    item["pdf_path"] = str(pdf_path)
                    item["updated_at"] = datetime.datetime.now().isoformat()
                    exists = True
                    break
            if not exists:
                completed.append({
                    "id": ws_id,
                    "title": ws_title,
                    "lang": lang,
                    "pdf_path": str(pdf_path),
                    "created_at": datetime.datetime.now().isoformat()
                })
            saved["completed_workshops"] = completed
            saved["stats"] = {
                "total_completed": len(completed),
                "last_run": datetime.datetime.now().isoformat()
            }
            try:
                STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(STATE_FILE, "w", encoding="utf-8") as f:
                    json.dump(saved, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error("Failed to save state file: %s", e)

    def stop(self):
        """Signals the crawler to gracefully stop."""
        self.stop_requested = True
        self.log("Đã nhận yêu cầu dừng tiến trình...", "WARNING")

    @staticmethod
    def _filter_workshops(
        all_workshops: List[Dict],
        categories: List[Dict],
        workshop_ids: Optional[List[str]] = None,
        category_slug: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> List[Dict]:
        """Filters workshops by IDs, category title/slug, and/or keyword."""
        targets = list(all_workshops)

        if workshop_ids:
            norm_ids = {wid.strip() for wid in workshop_ids if wid.strip()}
            targets = [w for w in targets if w["id"] in norm_ids]

        if category_slug:
            cat_q = category_slug.strip().lower()
            matched_cat_titles = {
                c.get("title", "").lower()
                for c in categories
                if cat_q in c.get("slug", "").lower() or cat_q in c.get("title", "").lower()
            }
            targets = [
                w for w in targets
                if cat_q in w.get("category", "").lower()
                or cat_q in w.get("category_slug", "").lower()
                or w.get("category", "").lower() in matched_cat_titles
            ]

        if keyword:
            kw = keyword.strip().lower()
            targets = [
                w for w in targets
                if kw in w.get("title", "").lower()
                or kw in w.get("id", "").lower()
                or kw in (w.get("subcategory") or "").lower()
            ]

        return targets

    def run_bundle(
        self,
        languages: Optional[List[str]] = None,
        output_format: str = "both",
        workshop_ids: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> Dict:
        """Combines already-downloaded workshops into a single Markdown and/or PDF file."""
        with self._lock:
            if self.is_running:
                return {"status": "error", "message": "Tiến trình đang chạy. Vui lòng đợi."}
            self.is_running = True
            self.stop_requested = False

        langs = languages or ["vi"]
        all_files: List[str] = []
        processed_langs = 0
        failed_langs = 0
        total_ws_bundled = 0

        try:
            for idx, lang in enumerate(langs):
                self.log(f"Đang gộp tài liệu thành 1 file duy nhất ({lang.upper()}, định dạng: {output_format.upper()})...")

                def on_bundle_prog(msg: str, pct: int):
                    self.log(msg)
                    self.current_task_info = {
                        "workshop_id": "ALL",
                        "title": f"Gộp file tổng hợp ({lang.upper()})",
                        "lang": lang,
                        "index": idx + 1,
                        "total": len(langs),
                        "progress": pct,
                        "step": msg,
                    }
                    if progress_callback:
                        progress_callback(self.current_task_info)

                res = build_combined_bundle(
                    output_dir=self.output_dir,
                    lang=lang,
                    output_format=output_format,
                    workshop_ids=workshop_ids,
                    pdf_generator=self.pdf_generator,
                    progress_callback=on_bundle_prog,
                )

                if res.get("status") == "success":
                    processed_langs += 1
                    total_ws_bundled = max(total_ws_bundled, res.get("workshops_count", 0))
                    for f in res.get("files", []):
                        all_files.append(f)
                        self.log(f"Đã tạo file tổng hợp: {Path(f).name} ({res.get('workshops_count', 0)} bài)")
                else:
                    failed_langs += 1
                    for f in res.get("files", []):
                        all_files.append(f)
                    self.log(res.get("message", "Không thể tạo file tổng hợp."), "ERROR")

            return {
                "status": "success" if failed_langs == 0 else "error",
                "processed": total_ws_bundled if processed_langs > 0 else 0,
                "failed": failed_langs,
                "total": total_ws_bundled or len(langs),
                "bundle_files": all_files,
            }
        finally:
            with self._lock:
                self.is_running = False
                self.stop_requested = False

    def run_workshops(
        self,
        workshop_ids: Optional[List[str]] = None,
        category_slug: Optional[str] = None,
        keyword: Optional[str] = None,
        languages: Optional[List[str]] = None,
        force_refresh_catalog: bool = False,
        output_format: str = "both",
        bundle_all: bool = False,
        progress_callback: Optional[Callable[[Dict], None]] = None
    ) -> Dict:
        """
        Executes crawling and export for the selected workshops, and optionally bundles them into 1 file.
        """
        with self._lock:
            if self.is_running:
                return {"status": "error", "message": "Crawler đang chạy. Vui lòng đợi hoặc bấm dừng."}
            self.is_running = True
            self.stop_requested = False

        langs = languages or ["vi"]

        try:
            self.log("Khởi động trình thu thập FCAJ Crawler...")

            # Step 1: Scan / load catalog
            scanner = CatalogScanner(force_refresh=force_refresh_catalog)
            catalog = scanner.scan(progress_callback=lambda msg, pct: self.log(f"{msg} ({pct}%)"))
            all_workshops = catalog.get("workshops", [])
            categories = catalog.get("categories", [])

            # Step 2: Filter targets
            targets = self._filter_workshops(
                all_workshops=all_workshops,
                categories=categories,
                workshop_ids=workshop_ids,
                category_slug=category_slug,
                keyword=keyword,
            )

            total_targets = len(targets)
            self.log(f"Tổng số workshop cần xử lý: {total_targets}")
            if total_targets == 0:
                self.log("Không tìm thấy workshop nào phù hợp điều kiện.", "WARNING")
                return {"status": "success", "processed": 0, "failed": 0, "total": 0}

            success_count = 0
            fail_count = 0

            for ws_idx, ws in enumerate(targets):
                if self.stop_requested:
                    self.log("Tiến trình đã dừng theo yêu cầu của người dùng.", "WARNING")
                    break

                ws_id = ws["id"]
                ws_title = ws["title"]
                self.log(f"--- [{ws_idx + 1}/{total_targets}] #{ws_id} - {ws_title} ---")

                for lang in langs:
                    if self.stop_requested:
                        break

                    self.current_task_info = {
                        "workshop_id": ws_id,
                        "title": ws_title,
                        "lang": lang,
                        "index": ws_idx + 1,
                        "total": total_targets,
                        "progress": 0,
                        "step": f"Đang cào dữ liệu ({lang.upper()})..."
                    }
                    if progress_callback:
                        progress_callback(self.current_task_info)

                    try:
                        # 1. Crawl
                        crawler = WorkshopCrawler(ws, lang=lang, output_dir=self.output_dir)

                        def on_crawl_progress(msg, pct):
                            self.log(msg)
                            self.current_task_info["progress"] = int(pct * 0.6)  # 0 - 60%
                            self.current_task_info["step"] = msg
                            if progress_callback:
                                progress_callback(self.current_task_info)

                        chapters = crawler.crawl_all(progress_callback=on_crawl_progress)

                        if not chapters:
                            self.log(f"[{ws_id}] Không tìm thấy nội dung cho ngôn ngữ {lang}.", "WARNING")
                            fail_count += 1
                            continue

                        produced = []
                        step_failed = False
                        clean_title = crawler._sanitize_filename(ws_title)

                        # 2. Markdown export
                        if output_format in ("md", "both"):
                            self.log(f"[{ws_id}] Đang xuất Markdown...")
                            self.current_task_info["progress"] = 65
                            self.current_task_info["step"] = "Đang xuất Markdown..."
                            if progress_callback:
                                progress_callback(self.current_task_info)
                            md_path = MarkdownExporter(ws, chapters, crawler.workshop_dir, lang=lang).export()
                            self.log(f"[{ws_id}] Đã tạo Markdown: {md_path.name}")
                            produced.append(str(md_path))

                        # 3. Book HTML + PDF
                        if output_format in ("pdf", "both"):
                            self.log(f"[{ws_id}] Đang biên soạn HTML tổng hợp...")
                            self.current_task_info["progress"] = 75
                            self.current_task_info["step"] = "Đang biên soạn HTML..."
                            if progress_callback:
                                progress_callback(self.current_task_info)

                            processor = WorkshopProcessor(ws, chapters, lang=lang, output_dir=self.output_dir)
                            book_html_path = processor.generate_book_html()

                            pdf_filename = f"{ws_id}_{clean_title}_{lang.upper()}.pdf"
                            pdf_path = crawler.workshop_dir / pdf_filename
                            self.log(f"[{ws_id}] Đang xuất PDF: {pdf_filename}...")
                            self.current_task_info["progress"] = 85
                            self.current_task_info["step"] = "Đang xuất PDF..."
                            if progress_callback:
                                progress_callback(self.current_task_info)

                            if self.pdf_generator.convert_html_to_pdf(
                                book_html_path, pdf_path, title=f"Workshop #{ws_id}: {ws_title}"
                            ):
                                self.log(f"[{ws_id}] Đã tạo PDF: {pdf_path.name} ({pdf_path.stat().st_size // 1024} KB)")
                                produced.append(str(pdf_path))
                            else:
                                reason = self.pdf_generator.last_error or "Không rõ nguyên nhân"
                                self.log(f"[{ws_id}] Không thể tạo file PDF: {reason}", "ERROR")
                                step_failed = True

                        if produced:
                            self._save_completed_workshop(ws_id, ws_title, lang, ";".join(produced))
                        if step_failed or not produced:
                            fail_count += 1
                        else:
                            success_count += 1

                    except Exception as ex:
                        self.log(f"[{ws_id}] Lỗi khi xử lý ({lang}): {ex}", "ERROR")
                        fail_count += 1

            try:
                idx_path = build_global_index(self.output_dir)
                self.log(f"Đã cập nhật mục lục tổng: {idx_path}")
            except Exception as ex:
                self.log(f"Không tạo được INDEX.md: {ex}", "WARNING")

            bundle_files: List[str] = []
            if bundle_all and not self.stop_requested and success_count > 0:
                target_ids_for_bundle = [w["id"] for w in targets] if (workshop_ids or category_slug or keyword) else None
                for lang in langs:
                    self.log(f"Đang gộp tất cả vào 1 file duy nhất ({lang.upper()})...")
                    b_res = build_combined_bundle(
                        output_dir=self.output_dir,
                        lang=lang,
                        output_format=output_format,
                        workshop_ids=target_ids_for_bundle,
                        pdf_generator=self.pdf_generator,
                        progress_callback=lambda msg, pct: self.log(msg),
                    )
                    for bf in b_res.get("files", []):
                        bundle_files.append(bf)
                        self.log(f"Đã tạo file tổng hợp duy nhất: {Path(bf).name}")
                    if b_res.get("status") not in ("success", "empty"):
                        self.log(b_res.get("message", "Lỗi khi gộp file tổng hợp."), "ERROR")
                        fail_count += 1

            self.current_task_info = {
                "step": "Hoàn tất.",
                "progress": 100,
                "is_done": True
            }
            if progress_callback:
                progress_callback(self.current_task_info)

            summary = {
                "status": "success",
                "processed": success_count,
                "failed": fail_count,
                "total": total_targets,
                "bundle_files": bundle_files,
            }
            level = "WARNING" if fail_count > 0 else "INFO"
            self.log(f"Hoàn tất thu thập. Thành công: {success_count}, Thất bại: {fail_count}", level)
            return summary

        finally:
            with self._lock:
                self.is_running = False
                self.stop_requested = False
