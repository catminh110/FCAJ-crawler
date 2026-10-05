import json
import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Dict

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_file,
    send_from_directory,
)

from fcaj_crawler.config import CATALOG_CACHE_FILE, OUTPUT_DIR, STATE_FILE
from fcaj_crawler.runner import CrawlManager
from fcaj_crawler.scanner import CatalogScanner

logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static")
)

# Global manager instance
manager = CrawlManager(output_dir=OUTPUT_DIR)
event_listeners = []


def broadcast_event(data: dict):
    msg = f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    dead = []
    for q in event_listeners:
        try:
            q.put_nowait(msg)
        except Exception:
            dead.append(q)
    for q in dead:
        if q in event_listeners:
            event_listeners.remove(q)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/catalog", methods=["GET"])
def get_catalog():
    scanner = CatalogScanner(force_refresh=False)
    catalog = scanner.scan()
    return jsonify(catalog)


@app.route("/api/scan", methods=["POST"])
def trigger_scan():
    def do_scan():
        broadcast_event({"type": "log", "message": "Bắt đầu quét lại toàn bộ catalog từ cloudjourney..."})
        scanner = CatalogScanner(force_refresh=True)
        catalog = scanner.scan(progress_callback=lambda msg, pct: broadcast_event({
            "type": "scan_progress",
            "message": msg,
            "percent": pct
        }))
        broadcast_event({"type": "scan_complete", "total": len(catalog.get("workshops", []))})

    threading.Thread(target=do_scan, daemon=True).start()
    return jsonify({"status": "started", "message": "Quá trình quét catalog đã bắt đầu"})


@app.route("/api/crawl", methods=["POST"])
def start_crawl():
    if manager.is_running:
        return jsonify({"status": "error", "message": "Tiến trình cào đang chạy!"}), 400

    data = request.get_json() or {}
    ids = data.get("ids", [])
    category = data.get("category")
    keyword = data.get("keyword")
    lang = data.get("lang", "vi")
    output_format = data.get("format", "both")
    if output_format not in ("md", "pdf", "both"):
        output_format = "both"

    langs = ["vi", "en"] if lang == "both" else [lang]

    def runner_worker():
        def on_progress(p_info):
            broadcast_event({"type": "progress", "data": p_info})

        manager.run_workshops(
            workshop_ids=ids if ids else None,
            category_slug=category,
            keyword=keyword,
            languages=langs,
            output_format=output_format,
            progress_callback=on_progress
        )
        broadcast_event({"type": "crawl_finished"})

    threading.Thread(target=runner_worker, daemon=True).start()
    return jsonify({"status": "started", "message": "Đã bắt đầu thu thập dữ liệu và xuất PDF!"})


@app.route("/api/stop", methods=["POST"])
def stop_crawl():
    manager.stop()
    return jsonify({"status": "stopping", "message": "Đã gửi tín hiệu dừng tiến trình."})


@app.route("/api/status", methods=["GET"])
def get_status():
    state = manager.get_state()
    return jsonify(state)


@app.route("/api/downloads", methods=["GET"])
def list_downloads():
    workshops_dir = OUTPUT_DIR / "workshops"
    pdfs = []
    if workshops_dir.exists():
        candidates = list(workshops_dir.glob("*/*.pdf"))
        for d in workshops_dir.iterdir():
            if d.is_dir():
                ws_prefix = d.name.split("_")[0]
                candidates += list(d.glob(f"{ws_prefix}_*.md"))
        for pdf_file in candidates:
            rel_path = pdf_file.relative_to(OUTPUT_DIR)
            folder_name = pdf_file.parent.name
            ws_id = folder_name.split("_")[0]
            size_mb = round(pdf_file.stat().st_size / (1024 * 1024), 2)
            pdfs.append({
                "id": ws_id,
                "filename": pdf_file.name,
                "relative_path": str(rel_path),
                "folder": folder_name,
                "size_mb": size_mb,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(pdf_file.stat().st_mtime))
            })
    pdfs.sort(key=lambda x: x["updated_at"], reverse=True)
    return jsonify({"files": pdfs})


@app.route("/download/<path:filepath>")
def download_pdf(filepath):
    target = (OUTPUT_DIR / filepath).resolve()
    # Security check: must reside inside OUTPUT_DIR
    if not str(target).startswith(str(OUTPUT_DIR.resolve())):
        return "Truy cập bị từ chối", 403
    if not target.exists():
        return "File không tồn tại", 404
    return send_file(target, as_attachment=True, download_name=target.name)


@app.route("/preview/<path:filepath>")
def preview_pdf(filepath):
    target = (OUTPUT_DIR / filepath).resolve()
    if not str(target).startswith(str(OUTPUT_DIR.resolve())):
        return "Truy cập bị từ chối", 403
    if not target.exists():
        return "File không tồn tại", 404
    if target.suffix == ".md":
        return send_file(target, mimetype="text/markdown; charset=utf-8")
    return send_file(target, mimetype="application/pdf")


@app.route("/api/stream")
def sse_stream():
    """Server-Sent Events endpoint for real-time live terminal streaming."""
    def event_generator():
        client_q = queue.Queue(maxsize=100)
        event_listeners.append(client_q)
        try:
            # Send initial state
            initial = json.dumps({"type": "init", "state": manager.get_state()})
            yield f"data: {initial}\n\n"
            while True:
                msg = client_q.get()
                yield msg
        except GeneratorExit:
            if client_q in event_listeners:
                event_listeners.remove(client_q)

    return Response(event_generator(), mimetype="text/event-stream")


def create_app():
    return app
