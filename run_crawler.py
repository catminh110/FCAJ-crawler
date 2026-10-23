#!/usr/bin/env python3
"""
CLI entry point for FCAJ Crawler & PDF Generator.
Usage:
    python run_crawler.py scan
    python run_crawler.py list
    python run_crawler.py crawl --id 000001 --lang vi
    python run_crawler.py crawl --category 1-explore --lang vi --bundle
    python run_crawler.py crawl --all --lang vi --bundle
    python run_crawler.py bundle --lang vi --format both
"""

import argparse
import logging
import sys
from pathlib import Path

from fcaj_crawler.config import OUTPUT_DIR, configure_utf8_console

configure_utf8_console()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

from fcaj_crawler.runner import CrawlManager
from fcaj_crawler.scanner import CatalogScanner


def cmd_scan(args):
    print("Đang quét toàn bộ danh mục và các workshop từ https://cloudjourney.awsstudygroup.com ...")
    scanner = CatalogScanner(force_refresh=args.refresh)
    catalog = scanner.scan()
    workshops = catalog.get("workshops", [])
    categories = catalog.get("categories", [])
    print(f"\nĐã phát hiện tổng cộng {len(workshops)} workshop trên hệ thống.")
    print(f"Danh mục ({len(categories)}):")
    for c in categories:
        print(f"  - {c['title']} ({c['url']})")


def cmd_list(args):
    scanner = CatalogScanner(force_refresh=args.refresh)
    catalog = scanner.scan()
    workshops = catalog.get("workshops", [])
    print(f"\n{'='*75}")
    print(f"{'ID':<10} | {'DANH MỤC':<25} | {'TIÊU ĐỀ WORKSHOP'}")
    print(f"{'='*75}")
    for w in workshops:
        cat = w.get("category", "")[:23]
        title = w.get("title", "")
        print(f"{w['id']:<10} | {cat:<25} | {title}")
    print(f"{'='*75}")
    print(f"Tổng số: {len(workshops)} workshops")


def cmd_crawl(args):
    output_path = Path(args.output) if args.output else OUTPUT_DIR
    manager = CrawlManager(output_dir=output_path)

    langs = ["vi", "en"] if args.lang == "both" else [args.lang]

    workshop_ids = None
    if args.id:
        workshop_ids = [x.strip() for x in args.id.split(",") if x.strip()]

    print(f"Bắt đầu cào và xuất tài liệu vào thư mục: {output_path.resolve()}")
    print(f"Ngôn ngữ: {', '.join(langs).upper()}  |  Định dạng: {args.format.upper()}  |  Gộp 1 file: {'CÓ' if args.bundle else 'KHÔNG'}")

    res = manager.run_workshops(
        workshop_ids=workshop_ids,
        category_slug=args.category,
        keyword=args.search,
        languages=langs,
        force_refresh_catalog=args.refresh,
        output_format=args.format,
        bundle_all=args.bundle,
    )

    print("\n" + "="*50)
    print(f"KẾT QUẢ: Đã xử lý {res.get('processed', 0)} / {res.get('total', 0)} workshop")
    if res.get("bundle_files"):
        print("Tệp tổng hợp duy nhất:")
        for bf in res["bundle_files"]:
            print(f"  -> {bf}")
    print(f"Thư mục lưu trữ: {output_path.resolve()}")
    print("="*50)


def cmd_bundle(args):
    output_path = Path(args.output) if args.output else OUTPUT_DIR
    manager = CrawlManager(output_dir=output_path)
    langs = ["vi", "en"] if args.lang == "both" else [args.lang]
    workshop_ids = [x.strip() for x in args.id.split(",") if x.strip()] if args.id else None

    print(f"Đang gộp các workshop đã tải trong {output_path.resolve()} thành 1 file duy nhất...")
    res = manager.run_bundle(
        languages=langs,
        output_format=args.format,
        workshop_ids=workshop_ids,
    )
    print("\n" + "="*50)
    if res.get("bundle_files"):
        print(f"Đã gộp thành công {res.get('processed', 0)} workshop vào:")
        for bf in res["bundle_files"]:
            print(f"  -> {bf}")
    else:
        print("Không tạo được tệp tổng hợp (kiểm tra xem đã có workshop nào được tải chưa).")
    print("="*50)


def main():
    parser = argparse.ArgumentParser(
        description="FCAJ Crawler - Cào dữ liệu cloudjourney.awsstudygroup.com sang Markdown & PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Lệnh thực hiện")

    # Command: scan
    scan_p = subparsers.add_parser("scan", help="Quét tìm toàn bộ danh mục và các workshop con")
    scan_p.add_argument("--refresh", action="store_true", help="Bắt buộc quét lại trang web thay vì dùng cache")

    # Command: list
    list_p = subparsers.add_parser("list", help="Liệt kê danh sách các workshop kèm ID")
    list_p.add_argument("--refresh", action="store_true", help="Làm mới danh sách")

    # Command: crawl
    crawl_p = subparsers.add_parser("crawl", help="Thực hiện cào nội dung và xuất Markdown/PDF")
    crawl_p.add_argument("--all", action="store_true", help="Cào toàn bộ 127+ workshop trên hệ thống")
    crawl_p.add_argument("--id", type=str, help="ID workshop cần cào (ví dụ: 000001 hoặc 000001,000002)")
    crawl_p.add_argument("--category", type=str, help="Cào theo tên/slug danh mục (ví dụ: 1-explore, migrate)")
    crawl_p.add_argument("--search", type=str, help="Tìm theo từ khóa (ví dụ: ec2, dynamodb, s3)")
    crawl_p.add_argument("--lang", choices=["vi", "en", "both"], default="vi", help="Ngôn ngữ bài viết (mặc định: vi)")
    crawl_p.add_argument("--format", choices=["md", "pdf", "both"], default="both", help="Định dạng xuất (mặc định: both = Markdown + PDF)")
    crawl_p.add_argument("--bundle", action="store_true", help="Gộp tất cả các bài đã cào thành 1 file Markdown/PDF duy nhất (FCAJ_ALL_<LANG>)")
    crawl_p.add_argument("--output", type=str, help="Thư mục xuất kết quả")
    crawl_p.add_argument("--refresh", action="store_true", help="Làm mới cache danh sách")

    # Command: bundle
    bundle_p = subparsers.add_parser("bundle", help="Gộp các workshop đã tải thành 1 file Markdown/PDF duy nhất")
    bundle_p.add_argument("--id", type=str, help="Chỉ gộp các ID cụ thể (cách nhau bởi dấu phẩy), bỏ trống để gộp tất cả bài đã tải")
    bundle_p.add_argument("--lang", choices=["vi", "en", "both"], default="vi", help="Ngôn ngữ cần gộp (mặc định: vi)")
    bundle_p.add_argument("--format", choices=["md", "pdf", "both"], default="both", help="Định dạng file gộp (mặc định: both)")
    bundle_p.add_argument("--output", type=str, help="Thư mục chứa dữ liệu")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "crawl":
        if not (args.all or args.id or args.category or args.search):
            print("Bạn cần chỉ định mục tiêu cần cào: --all, --id <ID>, --category <tên>, hoặc --search <từ khóa>")
            sys.exit(1)
        cmd_crawl(args)
    elif args.command == "bundle":
        cmd_bundle(args)


if __name__ == "__main__":
    main()
