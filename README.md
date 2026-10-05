# 🚀 FCAJ Crawler & PDF Studio

Phần mềm tự động thu thập (cào) toàn bộ dữ liệu từ cổng **Cloud Journey (AWS Study Group)** tại [https://cloudjourney.awsstudygroup.com](https://cloudjourney.awsstudygroup.com) và **toàn bộ 127+ trang web con / workshop** (như `000001.awsstudygroup.com`, `000002.awsstudygroup.com`,...), tải toàn bộ ảnh hướng dẫn và xuất ra **Markdown** (dễ đọc, dễ tìm kiếm, dễ đưa vào Obsidian/Notion/GitHub) và/hoặc **PDF chuẩn sách A4** có trang bìa, mục lục và đánh số trang.

---

## 🌟 Tính Năng Nổi Bật

1. **Quét tự động toàn bộ 127+ Web Con**:
   - Tự động nhận diện toàn bộ các subdomain workshop thuộc AWS Study Group (`000001` đến `000200`+).
   - Khám phá toàn bộ danh mục: *1. Explore AWS Services, 2. Migrate, 3. Optimize, 4. Modernize, 5. Container, 6. Data & Analytics, 7. AI/ML, 8. FCJ Workforce*.
2. **Thu thập từng chương & trang con chi tiết**:
   - Đọc cây điều hướng sidebar của theme Hugo và sitemap (`/sitemap.xml`, `/vi/sitemap.xml`).
   - Cào tuần tự đúng thứ tự bài học từ Chương 1 đến Chương cuối cùng.
3. **Tải toàn bộ hình ảnh ngoại tuyến (Full Offline Assets)**:
   - Tự động tải về hàng chục ảnh chụp màn hình từng bước (screenshots) của mỗi bài.
   - Lưu trữ cục bộ trong thư mục `images/` của từng workshop.
4. **Biên soạn sách PDF chuyên nghiệp (Publication-grade PDF)**:
   - **Trang bìa (Cover Page)**: Thiết kế gradient hiện đại, logo chủ đề, tên workshop, tác giả, ngày tạo.
   - **Mục lục (Table of Contents)**: Tự động đánh số chương và liên kết nhảy nhanh.
   - **Định dạng code & bảng biểu**: Giữ nguyên syntax highlighting, callout box (chú thích/cảnh báo) và font chữ Inter/JetBrains Mono.
   - **Đánh số trang chân trang**: Hiển thị "Trang X / Y" và nguồn link bài gốc.
5. **Đa dạng giao diện sử dụng**:
   - **Giao diện Web Dashboard**: Trực quan, hiển thị thanh tiến trình thời gian thực, bảng chọn lọc workshop, tải và xem file PDF trực tiếp.
   - **Giao diện dòng lệnh CLI**: Thích hợp cho việc chạy script tự động hoặc cào hàng loạt.

---

## 📁 Cấu Trúc Dự Án

```
FCAJ crawler/
├── fcaj_crawler/                 # Mã nguồn lõi của phần mềm
│   ├── config.py                 # Cấu hình đường dẫn, thời gian timeout, thiết lập PDF
│   ├── scanner.py                # Quét và trích xuất danh sách 127+ workshop từ cổng chính
│   ├── crawler.py                # Cào nội dung từng chương, trang con và tải toàn bộ ảnh
│   ├── processor.py              # Xử lý HTML, làm sạch và biên soạn thành sách (Cover + TOC)
│   ├── pdf_generator.py          # Render PDF chuẩn A4 bằng Playwright Chromium
│   ├── runner.py                 # Điều phối tiến trình (CrawlManager), lưu trạng thái
│   └── web/                      # Giao diện Web Dashboard
│       ├── app.py                # Flask server, API & Server-Sent Events (SSE)
│       ├── templates/index.html  # Giao diện người dùng hiện đại
│       └── static/               # CSS Slate/Dark theme & JavaScript điều khiển
├── output_fcaj/                  # Thư mục lưu trữ kết quả cào & file PDF
│   └── workshops/
│       └── 000001_Creating_Your_First_AWS_Account/
│           ├── 000001_Creating_Your_First_AWS_Account_VI.pdf   <-- File PDF hoàn chỉnh
│           ├── book_vi.html                                    <-- Bản HTML tổng hợp
│           ├── metadata_vi.json                                <-- Thông tin bài học
│           └── images/                                         <-- Toàn bộ ảnh hướng dẫn
├── run_web.py                    # Khởi động Giao diện Web Dashboard
├── run_crawler.py                # Khởi động Giao diện Dòng lệnh (CLI)
├── requirements.txt              # Danh sách thư viện Python
└── README.md
```

---

## 🛠 Hướng Dẫn Cài Đặt

### 1. Chuẩn bị môi trường Python

Khởi tạo môi trường ảo và cài đặt thư viện cần thiết:

```bash
# Tạo môi trường ảo
python3 -m venv .venv
source .venv/bin/activate

# Cài đặt các gói phụ thuộc
pip install -r requirements.txt

# Cài đặt trình duyệt Chromium cho Playwright
playwright install chromium
```

---

## 🚀 Cách Sử Dụng

### Cách 1: Sử dụng Giao Diện Web Dashboard (Khuyên Dùng)

Chạy lệnh sau:

```bash
python run_web.py
```

Dashboard sẽ tự động mở trên trình duyệt tại: **`http://127.0.0.1:5000`**

Tại đây bạn có thể:
1. Tìm kiếm và chọn lọc bất kỳ workshop nào trong 127 workshop.
2. Chọn ngôn ngữ (*Tiếng Việt* hoặc *English* hoặc *Cả hai*).
3. Nhấn **"Bắt đầu cào PDF"** và xem tiến trình cùng log trực tiếp.
4. Xem trước hoặc tải trực tiếp file PDF đã xuất ngay trên trang web.

---

### Cách 2: Sử dụng Dòng Lệnh (CLI)

#### 1. Quét danh mục và xem toàn bộ workshop
```bash
python run_crawler.py scan
python run_crawler.py list
```

#### 2. Cào thử nghiệm 1 workshop cụ thể (Ví dụ ID `000001`):
```bash
python run_crawler.py crawl --id 000001 --lang vi
```

#### 3. Cào nhiều workshop cùng lúc:
```bash
python run_crawler.py crawl --id 000001,000002,000003 --lang vi
```

#### 4. Cào theo Danh mục (Category):
```bash
# Cào toàn bộ các bài trong danh mục "Explore AWS Services"
python run_crawler.py crawl --category 1-explore --lang vi

# Cào toàn bộ danh mục Migrate
python run_crawler.py crawl --category 2-migrate --lang vi
```

#### 5. Cào theo từ khóa:
```bash
python run_crawler.py crawl --search ec2 --lang vi
python run_crawler.py crawl --search dynamodb --lang vi
```

#### 6. Cào TOÀN BỘ 127+ workshop trên toàn bộ hệ thống:
```bash
python run_crawler.py crawl --all --lang vi
```

*Mẹo*: Để cào cả tiếng Anh và tiếng Việt, thêm cờ `--lang both`.

#### 7. Chọn định dạng xuất (`--format`)
```bash
python run_crawler.py crawl --all --lang vi --format md     # chỉ Markdown (nhanh nhất)
python run_crawler.py crawl --all --lang vi --format pdf    # chỉ PDF
python run_crawler.py crawl --all --lang vi --format both   # cả hai (mặc định)
```

---

## 📝 Dữ Liệu Markdown

Mỗi workshop được lưu trong `output_fcaj/workshops/<ID>_<Tên>/`:

```
000004_Compute_Essentials_with_Amazon_Elastic_Compute_Cloud_(EC2)/
├── README.md                        # Thông tin + mục lục (có phân cấp chương cha/con)
├── 000004_..._VI.md                 # Toàn bộ workshop gộp trong 1 file
├── chapters_vi/                     # Mỗi chương 1 file, có nút ← Bài trước / Bài tiếp →
│   ├── 00-gioi-thieu-ve-amazon-ec2.md
│   ├── 01-gioi-thieu.md
│   └── ...
├── images/                          # Ảnh dùng chung (link tương đối, xem offline được)
├── metadata_vi.json                 # Danh sách chương, URL gốc, thời gian cào
└── 000004_..._VI.pdf                # (nếu xuất PDF)
```

Mục lục tổng của mọi workshop đã cào: **`output_fcaj/INDEX.md`** (tự cập nhật sau mỗi lần chạy).

Xử lý khi chuyển sang Markdown:
- Khối code giữ ngôn ngữ (` ```bash `, ` ```json `...).
- Hộp ghi chú của Hugo (info/note/tip/warning) → blockquote có nhãn.
- Bỏ trang rác `Tags` / `Categories`; trang chỉ có trong sitemap được chèn đúng sau chương cha.

---

## 📑 File PDF Kết Quả

Tất cả các file PDF được xuất vào thư mục:
`output_fcaj/workshops/<ID>_<Tên Workshop>/<ID>_<Tên>_<NGÔN_NGỮ>.pdf`

Ví dụ:
- `output_fcaj/workshops/000001_Creating_Your_First_AWS_Account/000001_Creating_Your_First_AWS_Account_VI.pdf` (khoảng 15 MB, chứa trọn vẹn 13 chương và 98 ảnh hướng dẫn chất lượng cao).
