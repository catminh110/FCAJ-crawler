import datetime
import json
import logging
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

from fcaj_crawler.config import DATA_DIR, OUTPUT_DIR, STATE_FILE
from fcaj_crawler.crawler import WorkshopCrawler
from fcaj_crawler.pdf_generator import PDFGenerator
from fcaj_crawler.processor import WorkshopProcessor
from fcaj_crawler.scanner import CatalogScanner

logger = logging.getLogger(__name__)


class CrawlManager:
    """Orchestrates the entire scraping and PDF generation pipeline for FCAJ workshops."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or OUTPUT_DIR
        self.pdf_generator = PDFGenerator()
        self.is_running = False
        self.stop_requested = False
        self.current_task_info = {}
        self.logs: List[str] = []
        self._lock = threading.Lock()

    def log(self, message: str, level: str = "INFO"):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] [{level}] {message}"
        with self._lock:
            self.logs.append(formatted)
            # Keep max 500 log messages in memory
            if len(self.logs) > 500:
                self.logs.pop(0)
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
                "recent_logs": self.logs[-50:]
            }
        # Also include persisted stats if file exists
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
            # check if exists
            exists = False
            for item in completed:
                if item.get("id") == ws_id and item.get("lang") == lang:
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
                with open(STATE_FILE, "w", encoding="utf-8") as f:
                    json.dump(saved, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error("Failed to save state file: %s", e)

    def stop(self):
        """Signals the crawler to gracefully stop."""
        self.stop_requested = True
        self.log("Yêu cầu dừng tiến trình...", "WARNING")

    def run_workshops(
        self,
        workshop_ids: Optional[List[str]] = None,
        category_slug: Optional[str] = None,
        keyword: Optional[str] = None,
        languages: Optional[List[str]] = None,
        force_refresh_catalog: bool = False,
        progress_callback: Optional[Callable[[Dict], None]] = None
    ) -> Dict:
        """
        Executes crawling and PDF generation for the selected workshops.
        """
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

            # Step 2: Filter targets
            targets = []
            if workshop_ids:
                norm_ids = set([wid.strip() for wid in workshop_ids if wid.strip()])
                targets = [w for w in all_workshops if w["id"] in norm_ids]
            elif category_slug:
                targets = [w for w in all_workshops if category_slug.lower() in w.get("category", "").lower()]
            elif keyword:
                kw = keyword.lower()
                targets = [w for w in all_workshops if kw in w["title"].lower() or kw in w["id"].lower()]
            else:
                targets = all_workshops

            total_targets = len(targets)
            self.log(f"Tổng số workshop cần xử lý: {total_targets}")
            if total_targets == 0:
                self.log("Không tìm thấy workshop nào phù hợp điều kiện!", "WARNING")
                return {"status": "success", "processed": 0, "total": 0}

            success_count = 0
            fail_count = 0

            for ws_idx, ws in enumerate(targets):
                if self.stop_requested:
                    self.log("Tiến trình đã được dừng theo yêu cầu của người dùng.", "WARNING")
                    break

                ws_id = ws["id"]
                ws_title = ws["title"]
                self.log(f"\n==========================================")
                self.log(f"Bắt đầu xử lý [{ws_idx + 1}/{total_targets}]: #{ws_id} - {ws_title}")

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
                            self.log(f"[{ws_id}] Không tìm thấy nội dung cho ngôn ngữ {lang}!", "WARNING")
                            continue

                        # 2. Process to Book HTML
                        self.log(f"[{ws_id}] Đang biên soạn sách HTML tổng hợp...")
                        self.current_task_info["progress"] = 70
                        self.current_task_info["step"] = "Đang biên soạn sách HTML..."
                        if progress_callback:
                            progress_callback(self.current_task_info)

                        processor = WorkshopProcessor(ws, chapters, lang=lang, output_dir=self.output_dir)
                        book_html_path = processor.generate_book_html()

                        # 3. Generate PDF
                        clean_title = crawler._sanitize_filename(ws_title)
                        pdf_filename = f"{ws_id}_{clean_title}_{lang.upper()}.pdf"
                        pdf_path = crawler.workshop_dir / pdf_filename

                        self.log(f"[{ws_id}] Đang xuất PDF: {pdf_filename}...")
                        self.current_task_info["progress"] = 85
                        self.current_task_info["step"] = "Đang kết xuất PDF bằng Playwright..."
                        if progress_callback:
                            progress_callback(self.current_task_info)

                        pdf_success = self.pdf_generator.convert_html_to_pdf(
                            book_html_path,
                            pdf_path,
                            title=f"Workshop #{ws_id}: {ws_title}"
                        )

                        if pdf_success:
                            self.log(f"✅ Hoàn tất xuất PDF: {pdf_path.name} ({pdf_path.stat().st_size // 1024} KB)")
                            self._save_completed_workshop(ws_id, ws_title, lang, str(pdf_path))
                            success_count += 1
                        else:
                            self.log(f"❌ Thất bại khi tạo file PDF cho workshop {ws_id}", "ERROR")
                            fail_count += 1

                    except Exception as ex:
                        self.log(f"❌ Lỗi khi xử lý workshop {ws_id} ({lang}): {ex}", "ERROR")
                        fail_count += 1

            self.current_task_info = {
                "step": "Hoàn tất toàn bộ!",
                "progress": 100,
                "is_done": True
            }
            if progress_callback:
                progress_callback(self.current_task_info)

            summary = {
                "status": "success",
                "processed": success_count,
                "failed": fail_count,
                "total": total_targets
            }
            self.log(f"🎉 Hoàn tất thu thập! Thành công: {success_count}, Thất bại: {fail_count}")
            return summary

        finally:
            self.is_running = False
            self.stop_requested = False
