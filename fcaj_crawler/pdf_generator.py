import html
import logging
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright

from fcaj_crawler.config import (
    PDF_MARGIN,
    PDF_PAGE_FORMAT,
    PDF_PRINT_BACKGROUND,
    find_system_chromium,
)

logger = logging.getLogger(__name__)


class PDFGenerator:
    """Renders HTML into A4 PDF using headless Chromium (Playwright bundled or system Chrome/Edge fallback)."""

    def __init__(self):
        self.last_error: Optional[str] = None

    @staticmethod
    def _launch_browser(playwright_instance):
        launch_args = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        try:
            return playwright_instance.chromium.launch(headless=True, args=launch_args)
        except Exception as primary_err:
            sys_browser = find_system_chromium()
            if sys_browser:
                logger.info("Using system browser for PDF generation: %s", sys_browser)
                return playwright_instance.chromium.launch(
                    headless=True,
                    executable_path=sys_browser,
                    args=launch_args,
                )
            raise primary_err

    def convert_html_to_pdf(
        self,
        html_file_path: Path,
        pdf_output_path: Path,
        title: Optional[str] = None
    ) -> bool:
        """
        Converts a local HTML file to PDF via Playwright.
        Waits for all local images and styles to settle.
        """
        self.last_error = None
        html_abs_path = html_file_path.resolve()
        pdf_abs_path = pdf_output_path.resolve()
        pdf_abs_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Converting HTML to PDF: %s -> %s", html_abs_path, pdf_abs_path)

        header_title = html.escape(title or "AWS Study Group • The First Cloud Journey")
        header_template = f"""
        <div style="font-size: 8px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #94A3B8; width: 100%; padding: 0 15mm; display: flex; justify-content: space-between;">
            <span>{header_title}</span>
            <span></span>
        </div>
        """

        footer_template = """
        <div style="font-size: 8px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #94A3B8; width: 100%; padding: 0 15mm; display: flex; justify-content: space-between;">
            <span>https://cloudjourney.awsstudygroup.com</span>
            <span>Trang <span class="pageNumber"></span> / <span class="totalPages"></span></span>
        </div>
        """

        try:
            with sync_playwright() as p:
                browser = self._launch_browser(p)
                try:
                    page = browser.new_page()

                    # Block external http/https requests so broken remote images or iframes
                    # never hang local HTML -> PDF rendering.
                    page.route("http://**", lambda route: route.abort())
                    page.route("https://**", lambda route: route.abort())

                    # Navigate to the local file using standard RFC 8089 file:/// URI (cross-platform)
                    file_url = html_abs_path.as_uri()
                    page.goto(file_url, wait_until="domcontentloaded", timeout=120000)

                    # Wait for local images to finish loading (bounded to 15s max)
                    page.evaluate("""
                        () => Promise.race([
                            Promise.all(
                                Array.from(document.images)
                                    .filter(img => !img.complete)
                                    .map(img => new Promise(resolve => {
                                        img.onload = img.onerror = resolve;
                                    }))
                            ),
                            new Promise(resolve => setTimeout(resolve, 15000))
                        ])
                    """)

                    # Render to PDF
                    page.pdf(
                        path=str(pdf_abs_path),
                        format=PDF_PAGE_FORMAT,
                        print_background=PDF_PRINT_BACKGROUND,
                        margin=PDF_MARGIN,
                        display_header_footer=True,
                        header_template=header_template,
                        footer_template=footer_template,
                        prefer_css_page_size=False
                    )
                finally:
                    browser.close()

            logger.info("PDF generated successfully: %s (%d bytes)", pdf_abs_path, pdf_abs_path.stat().st_size)
            return True

        except Exception as e:
            err_msg = str(e).splitlines()[0] if str(e) else repr(e)
            if "Executable doesn't exist" in str(e):
                err_msg = "Chưa tìm thấy trình duyệt Chromium/Chrome. Hãy chạy lệnh: playwright install chromium"
            self.last_error = err_msg
            logger.error("Failed to generate PDF for %s: %s", html_abs_path, err_msg)
            return False
