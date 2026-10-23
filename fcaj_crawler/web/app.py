import html
import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_file,
)

from fcaj_crawler import __version__
from fcaj_crawler.config import OUTPUT_DIR
from fcaj_crawler.runner import CrawlManager
from fcaj_crawler.scanner import CatalogScanner

logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static")
)

# Global manager instance
manager = CrawlManager()
event_listeners = []
_listeners_lock = threading.Lock()


def broadcast_event(data: dict):
    msg = f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    with _listeners_lock:
        listeners_snapshot = list(event_listeners)
    for q in listeners_snapshot:
        try:
            q.put_nowait(msg)
        except queue.Full:
            pass


# Stream every crawler log line to connected dashboards
manager.log_listener = lambda line: broadcast_event({"type": "log", "message": line})


def _resolve_safe_output_file(filepath: str) -> tuple[Optional[Path], Optional[tuple[str, int]]]:
    """Resolves a relative path inside manager.output_dir safely, preventing path traversal."""
    base_dir = manager.output_dir.resolve()
    target = (base_dir / filepath).resolve()
    if not target.is_relative_to(base_dir):
        return None, ("Truy cập bị từ chối", 403)
    if not target.exists() or not target.is_file():
        return None, ("File không tồn tại", 404)
    return target, None


@app.route("/")
def index():
    return render_template("index.html", version=__version__, output_dir=str(manager.output_dir.resolve()))


@app.route("/api/catalog", methods=["GET"])
def get_catalog():
    scanner = CatalogScanner(force_refresh=False)
    catalog = scanner.scan()
    return jsonify(catalog)


@app.route("/api/scan", methods=["POST"])
def trigger_scan():
    def do_scan():
        try:
            broadcast_event({"type": "log", "message": "Bắt đầu quét lại danh mục từ cloudjourney.awsstudygroup.com..."})
            scanner = CatalogScanner(force_refresh=True)
            catalog = scanner.scan(progress_callback=lambda msg, pct: broadcast_event({
                "type": "scan_progress",
                "message": msg,
                "percent": pct
            }))
            broadcast_event({"type": "scan_complete", "total": len(catalog.get("workshops", []))})
        except Exception as e:
            logger.error("Catalog scan failed: %s", e)
            broadcast_event({"type": "log", "message": f"[LỖI] Quét danh mục thất bại: {e}"})
            broadcast_event({"type": "scan_error", "error": str(e)})

    threading.Thread(target=do_scan, daemon=True).start()
    return jsonify({"status": "started", "message": "Quá trình quét danh mục đã bắt đầu"})


@app.route("/api/crawl", methods=["POST"])
def start_crawl():
    if manager.is_running:
        return jsonify({"status": "error", "message": "Tiến trình đang chạy!"}), 400

    data = request.get_json(silent=True) or {}
    custom_dir = (data.get("output_dir") or "").strip()
    if custom_dir:
        try:
            manager.set_output_dir(custom_dir)
        except Exception as e:
            return jsonify({"status": "error", "message": f"Thư mục không hợp lệ: {e}"}), 400

    ids = data.get("ids", [])
    category = data.get("category")
    keyword = data.get("keyword")
    lang = data.get("lang", "vi")
    if lang not in ("vi", "en", "both"):
        lang = "vi"
    output_format = data.get("format", "both")
    if output_format not in ("md", "pdf", "both"):
        output_format = "both"
    bundle_all = bool(data.get("bundle", False))

    langs = ["vi", "en"] if lang == "both" else [lang]

    def runner_worker():
        def on_progress(p_info):
            broadcast_event({"type": "progress", "data": p_info})

        summary = manager.run_workshops(
            workshop_ids=ids if ids else None,
            category_slug=category,
            keyword=keyword,
            languages=langs,
            output_format=output_format,
            bundle_all=bundle_all,
            progress_callback=on_progress
        )
        broadcast_event({"type": "crawl_finished", "summary": summary})

    threading.Thread(target=runner_worker, daemon=True).start()
    labels = {"md": "Markdown", "pdf": "PDF", "both": "Markdown + PDF"}
    bundle_note = " + Gộp 1 file" if bundle_all else ""
    return jsonify({
        "status": "started",
        "output_dir": str(manager.output_dir.resolve()),
        "message": f"Đã bắt đầu tải dữ liệu ({labels[output_format]}{bundle_note}) vào {manager.output_dir.resolve()}.",
    })


@app.route("/api/bundle", methods=["POST"])
def start_bundle():
    """Combines already-downloaded workshops (or crawls missing selected ones) into a single MD/PDF file."""
    if manager.is_running:
        return jsonify({"status": "error", "message": "Tiến trình đang chạy!"}), 400

    data = request.get_json(silent=True) or {}
    custom_dir = (data.get("output_dir") or "").strip()
    if custom_dir:
        try:
            manager.set_output_dir(custom_dir)
        except Exception as e:
            return jsonify({"status": "error", "message": f"Thư mục không hợp lệ: {e}"}), 400

    ids = data.get("ids") or None
    lang = data.get("lang", "vi")
    if lang not in ("vi", "en", "both"):
        lang = "vi"
    output_format = data.get("format", "both")
    if output_format not in ("md", "pdf", "both"):
        output_format = "both"
    crawl_if_missing = bool(data.get("crawl_if_missing", False))

    langs = ["vi", "en"] if lang == "both" else [lang]

    def bundle_worker():
        def on_progress(p_info):
            broadcast_event({"type": "progress", "data": p_info})

        if crawl_if_missing:
            summary = manager.run_workshops(
                workshop_ids=ids if ids else None,
                languages=langs,
                output_format=output_format,
                bundle_all=True,
                progress_callback=on_progress,
            )
        else:
            summary = manager.run_bundle(
                languages=langs,
                output_format=output_format,
                workshop_ids=ids if ids else None,
                progress_callback=on_progress,
            )
        broadcast_event({"type": "crawl_finished", "summary": summary})

    threading.Thread(target=bundle_worker, daemon=True).start()
    return jsonify({"status": "started", "message": "Đang gộp tài liệu thành 1 file duy nhất..."})


@app.route("/api/stop", methods=["POST"])
def stop_crawl():
    manager.stop()
    return jsonify({"status": "stopping", "message": "Đã gửi tín hiệu dừng tiến trình."})


@app.route("/api/status", methods=["GET"])
def get_status():
    state = manager.get_state()
    return jsonify(state)


@app.route("/api/output-dir", methods=["GET", "POST"])
def api_output_dir():
    if request.method == "GET":
        return jsonify({"output_dir": str(manager.output_dir.resolve())})

    if manager.is_running:
        return jsonify({"status": "error", "message": "Không thể đổi thư mục khi đang tải dữ liệu!"}), 400

    data = request.get_json(silent=True) or {}
    new_dir = (data.get("output_dir") or "").strip()
    if not new_dir:
        return jsonify({"status": "error", "message": "Vui lòng nhập đường dẫn thư mục."}), 400
    try:
        resolved = manager.set_output_dir(new_dir)
        return jsonify({
            "status": "ok",
            "output_dir": str(resolved),
            "message": f"Đã chuyển thư mục lưu sang: {resolved}",
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Không thể tạo hoặc mở thư mục: {e}"}), 400


@app.route("/api/output-dir/browse", methods=["POST"])
def browse_output_dir():
    """Opens native OS folder selection dialog so the user can pick a destination directory."""
    if manager.is_running:
        return jsonify({"status": "error", "message": "Không thể đổi thư mục khi đang tải dữ liệu!"}), 400
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        current_dir = str(manager.output_dir.resolve())
        chosen = filedialog.askdirectory(
            initialdir=current_dir if os.path.isdir(current_dir) else os.path.expanduser("~"),
            title="Chọn thư mục lưu tài liệu FCAJ",
        )
        root.destroy()

        if not chosen:
            return jsonify({
                "status": "cancelled",
                "output_dir": current_dir,
            })

        resolved = manager.set_output_dir(chosen)
        return jsonify({
            "status": "ok",
            "output_dir": str(resolved),
            "message": f"Đã chọn thư mục lưu: {resolved}",
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Không thể mở cửa sổ chọn thư mục (bạn có thể gõ đường dẫn trực tiếp): {e}",
        }), 500


@app.route("/api/output-dir/open", methods=["POST"])
def open_output_dir():
    """Opens the current output directory in the system file explorer."""
    try:
        target_dir = manager.output_dir.resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(target_dir))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target_dir)])
        else:
            subprocess.Popen(["xdg-open", str(target_dir)])
        return jsonify({"status": "ok", "output_dir": str(target_dir)})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Không thể mở thư mục: {e}"}), 500


@app.route("/api/downloads", methods=["GET"])
def list_downloads():
    base_dir = manager.output_dir
    workshops_dir = base_dir / "workshops"
    files_list = []

    # 1. Include Master Bundle files (FCAJ_ALL_*.md, FCAJ_ALL_*.pdf) at root of output_dir
    if base_dir.exists():
        for bfile in list(base_dir.glob("FCAJ_ALL_*.md")) + list(base_dir.glob("FCAJ_ALL_*.pdf")):
            if not bfile.is_file():
                continue
            rel_path = bfile.relative_to(base_dir).as_posix()
            stat = bfile.stat()
            size_mb = round(stat.st_size / (1024 * 1024), 2)
            ext = bfile.suffix.lstrip(".").lower()
            stem_parts = bfile.stem.rsplit("_", 1)
            lang = stem_parts[-1].upper() if len(stem_parts) > 1 else "VI"
            files_list.append({
                "id": "ALL",
                "is_bundle": True,
                "filename": bfile.name,
                "format": ext,
                "lang": lang,
                "relative_path": rel_path,
                "folder": "",
                "size_mb": size_mb,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                "_mtime": stat.st_mtime,
            })

    # 2. Individual workshop files
    if workshops_dir.exists():
        candidates = list(workshops_dir.glob("*/*.pdf"))
        for d in workshops_dir.iterdir():
            if d.is_dir():
                ws_prefix = d.name.split("_")[0]
                candidates += list(d.glob(f"{ws_prefix}_*.md"))
        for fpath in candidates:
            if not fpath.is_file():
                continue
            rel_path = fpath.relative_to(base_dir).as_posix()
            folder_name = fpath.parent.name
            ws_id = folder_name.split("_")[0]
            stat = fpath.stat()
            size_mb = round(stat.st_size / (1024 * 1024), 2)
            ext = fpath.suffix.lstrip(".").lower()
            stem_parts = fpath.stem.rsplit("_", 1)
            lang = stem_parts[-1].upper() if len(stem_parts) > 1 and stem_parts[-1].lower() in ("vi", "en") else "VI"
            files_list.append({
                "id": ws_id,
                "is_bundle": False,
                "filename": fpath.name,
                "format": ext,
                "lang": lang,
                "relative_path": rel_path,
                "folder": folder_name,
                "size_mb": size_mb,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                "_mtime": stat.st_mtime,
            })

    files_list.sort(key=lambda x: (bool(x["is_bundle"]), x["_mtime"], x["filename"]), reverse=True)
    for item in files_list:
        item.pop("_mtime", None)
    return jsonify({"files": files_list})


@app.route("/api/downloads/<path:filepath>", methods=["DELETE"])
def delete_download(filepath):
    target, err = _resolve_safe_output_file(filepath)
    if err:
        return jsonify({"status": "error", "message": err[0]}), err[1]
    try:
        target.unlink()
        return jsonify({"status": "deleted", "filepath": filepath})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/download/<path:filepath>")
def download_pdf(filepath):
    target, err = _resolve_safe_output_file(filepath)
    if err:
        return err
    return send_file(target, as_attachment=True, download_name=target.name)


@app.route("/download-zip/<path:filepath>")
def download_markdown_zip(filepath):
    target, err = _resolve_safe_output_file(filepath)
    if err:
        return err
    if target.suffix.lower() != ".md":
        return ("Chỉ hỗ trợ đóng gói ZIP kèm ảnh cho tệp Markdown (.md)", 400)
    from fcaj_crawler.markdown_exporter import create_markdown_zip_bytes

    zip_buf = create_markdown_zip_bytes(target, manager.output_dir)
    return send_file(
        zip_buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{target.stem}_kem_anh.zip",
    )


@app.route("/preview/<path:filepath>")
def preview_pdf(filepath):
    target, err = _resolve_safe_output_file(filepath)
    if err:
        return err
    suffix = target.suffix.lower()
    if suffix == ".md":
        if request.args.get("raw") == "1":
            return send_file(target, mimetype="text/markdown; charset=utf-8")
        md_text = target.read_text(encoding="utf-8", errors="replace")
        escaped = html.escape(md_text)
        preview_html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(target.name)}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #F8FAFC;
      color: #0F172A;
      margin: 0;
      padding: 24px;
    }}
    .bar {{
      max-width: 920px;
      margin: 0 auto 12px auto;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 13px;
      color: #475569;
    }}
    .bar a {{
      color: #0F172A;
      text-decoration: none;
      border: 1px solid #CBD5E1;
      background: #FFFFFF;
      padding: 4px 10px;
      border-radius: 4px;
    }}
    pre {{
      max-width: 920px;
      margin: 0 auto;
      background: #FFFFFF;
      border: 1px solid #E2E8F0;
      border-radius: 6px;
      padding: 24px;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 13.5px;
      line-height: 1.6;
    }}
  </style>
</head>
<body>
  <div class="bar">
    <span><strong>{html.escape(target.name)}</strong></span>
    <div>
      <a href="?raw=1">Xem dạng thô</a>
      <a href="/download/{html.escape(filepath)}">Tải .MD</a>
      <a href="/download-zip/{html.escape(filepath)}">Tải kèm ảnh (.ZIP)</a>
    </div>
  </div>
  <pre>{escaped}</pre>
</body>
</html>"""
        return Response(preview_html, mimetype="text/html; charset=utf-8")
    if suffix in (".html", ".htm"):
        return send_file(target, mimetype="text/html; charset=utf-8")
    return send_file(target, mimetype="application/pdf")


@app.route("/api/stream")
def sse_stream():
    """Server-Sent Events endpoint for real-time live terminal streaming."""
    def event_generator():
        client_q = queue.Queue(maxsize=1000)
        with _listeners_lock:
            event_listeners.append(client_q)
        try:
            initial = json.dumps({"type": "init", "state": manager.get_state()}, ensure_ascii=False)
            yield f"data: {initial}\n\n"
            while True:
                try:
                    yield client_q.get(timeout=15)
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            with _listeners_lock:
                if client_q in event_listeners:
                    event_listeners.remove(client_q)

    return Response(
        event_generator(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def create_app():
    return app
