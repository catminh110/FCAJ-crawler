#!/usr/bin/env python3
"""
Web UI entry point for FCAJ Crawler & PDF Studio.
Usage:
    python run_web.py
    python run_web.py --port 5000 --host 0.0.0.0
"""

import argparse
import sys
import webbrowser
from fcaj_crawler.web.app import app

def main():
    parser = argparse.ArgumentParser(description="FCAJ Crawler Web Dashboard")
    parser.add_argument("--port", type=int, default=5000, help="Cổng mạng (mặc định: 5000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Địa chỉ host (mặc định: 127.0.0.1)")
    parser.add_argument("--no-browser", action="store_true", help="Không tự động mở trình duyệt")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    print("\n" + "=" * 65)
    print("🚀  FCAJ CRAWLER & PDF STUDIO - GIAO DIỆN QUẢN TRỊ TRỰC QUAN")
    print("=" * 65)
    print(f"👉  Đang khởi chạy dashboard tại: {url}")
    print("👉  Mở link trên trên trình duyệt để chọn cào và tải file PDF!")
    print("=" * 65 + "\n")

    if not args.no_browser and args.host in ("127.0.0.1", "localhost"):
        try:
            webbrowser.open(url)
        except Exception:
            pass

    app.run(host=args.host, port=args.port, debug=False, threaded=True)

if __name__ == "__main__":
    main()
