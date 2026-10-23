# FCAJ Crawler

Công cụ thu thập dữ liệu từ cổng **Cloud Journey (AWS Study Group)** tại [https://cloudjourney.awsstudygroup.com](https://cloudjourney.awsstudygroup.com) và các trang workshop con (`000001.awsstudygroup.com`, `000002.awsstudygroup.com`,...), tải hình ảnh đi kèm và xuất ra **Markdown** hoặc **PDF khổ A4** có trang bìa, mục lục và đánh số trang.

---

## Tính năng chính

1. **Quét danh mục tự động**:
   - Phát hiện các subdomain workshop thuộc AWS Study Group theo từng danh mục (*Explore AWS Services, Migrate, Optimize, Modernize, Container, Data & Analytics, AI/ML, FCJ Workforce*).
2. **Thu thập chương bài theo thứ tự**:
   - Đọc cây điều hướng sidebar của Hugo và đối chiếu với `sitemap.xml` (`/sitemap.xml`, `/vi/sitemap.xml`).
   - Loại bỏ các trang phân loại rác (`Tags`, `Categories`).
3. **Tải hình ảnh phục vụ xem ngoại tuyến**:
   - Lưu trữ cục bộ toàn bộ ảnh minh họa trong thư mục `images/` của từng workshop.
4. **Xuất Markdown & PDF (từng bài hoặc gộp 1 file duy nhất)**:
   - **Markdown**: Xuất bản tách từng chương, bản gộp từng bài (có hỗ trợ tải gói `.zip` kèm ảnh) và bản gộp toàn bộ hệ thống (`FCAJ_ALL_VI.md`).
   - **PDF**: Kết xuất qua trình duyệt Chromium/Chrome headless khổ A4 kèm trang bìa, mục lục và hỗ trợ ghép toàn bộ bài thành 1 cuốn PDF duy nhất (`FCAJ_ALL_VI.pdf`) có cây Bookmark.
5. **Giao diện Web & CLI**:
   - Hỗ trợ bảng điều khiển Web trực quan (cho phép chọn thư mục lưu bất kỳ trên máy) và công cụ dòng lệnh (CLI).

---

## Cài đặt

```bash
# 1. Tạo và kích hoạt môi trường ảo
python -m venv .venv
# Trên Windows:
.\.venv\Scripts\activate
# Trên Linux/macOS:
source .venv/bin/activate

# 2. Cài đặt thư viện
pip install -r requirements.txt

# 3. Cài đặt trình duyệt Chromium cho Playwright (hoặc sử dụng Google Chrome/Edge sẵn có trên máy)
playwright install chromium
```

---

## Cách sử dụng

### 1. Giao diện Web

```bash
python run_web.py
```

Mở trình duyệt tại **`http://127.0.0.1:5000`** để tìm kiếm, lọc theo danh mục, chọn định dạng (`Markdown`, `PDF`, hoặc `Cả hai`) và tải tài liệu.

### 2. Dòng lệnh (CLI)

```bash
# Quét và liệt kê danh sách workshop
python run_crawler.py scan
python run_crawler.py list

# Cào 1 hoặc nhiều workshop theo ID
python run_crawler.py crawl --id 000001 --lang vi
python run_crawler.py crawl --id 000001,000002 --lang vi --format both

# Cào theo danh mục hoặc từ khóa
python run_crawler.py crawl --category 1-explore --lang vi --format md
python run_crawler.py crawl --search ec2 --lang vi --format pdf

# Cào toàn bộ hệ thống và tự động gộp thành 1 file duy nhất
python run_crawler.py crawl --all --lang vi --bundle

# Gộp các workshop đã tải sẵn trên máy thành 1 file FCAJ_ALL duy nhất (không cần tải lại)
python run_crawler.py bundle --lang vi --format both

# Tuỳ chọn lưu vào thư mục bất kỳ với cờ -o / --output
python run_crawler.py crawl --id 000001 -o "D:\AWS_Workshops"
```

---

## Cấu trúc thư mục xuất (`output_fcaj/`)

```text
output_fcaj/
├── INDEX.md                              # Mục lục tổng hợp các workshop đã tải
├── FCAJ_ALL_VI.md                        # Bản Markdown gộp toàn bộ các workshop
├── FCAJ_ALL_VI.pdf                       # Bản PDF gộp toàn bộ các workshop (kèm Bookmark)
└── workshops/
    └── 000001_Creating_Your_First_AWS_Account/
        ├── README.md                     # Thông tin & mục lục của workshop
        ├── 000001_..._VI.md              # Bản Markdown gộp 1 file
        ├── 000001_..._VI.pdf             # Bản PDF khổ A4
        ├── book_vi.html                  # Bản HTML tổng hợp
        ├── chapters_vi/                  # Thư mục chứa từng chương rời (.md)
        ├── images/                       # Hình ảnh đã tải về
        └── metadata_vi.json              # Metadata của workshop
```

---

## Kiểm thử

```bash
pytest -v
```
