import logging
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright

from fcaj_crawler.config import PDF_MARGIN, PDF_PAGE_FORMAT, PDF_PRINT_BACKGROUND

logger = logging.getLogger(__name__)


class PDFGenerator:
    """Renders HTML into pixel-perfect, publication-grade PDF using headless Chromium."""

    def __init__(self):
        pass

    def convert_html_to_pdf(
        self,
        html_file_path: Path,
        pdf_output_path: Path,
        title: Optional[str] = None
    ) -> bool:
        """
        Converts a local HTML file to PDF via Playwright.
        Waits for all local images, fonts, and styles to settle.
        """
        html_abs_path = html_file_path.resolve()
        pdf_abs_path = pdf_output_path.resolve()
        pdf_abs_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Converting HTML to PDF: %s -> %s", html_abs_path, pdf_abs_path)

        header_title = title or "AWS Study Group • The First Cloud Journey"
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
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
                page = browser.new_page()
                
                # Navigate to the local file
                file_url = f"file://{html_abs_path}"
                page.goto(file_url, wait_until="networkidle", timeout=60000)

                # Wait for any lazy images to fully load
                page.evaluate("""
                    () => Promise.all(
                        Array.from(document.images)
                            .filter(img => !img.complete)
                            .map(img => new Promise(resolve => {
                                img.onload = img.onerror = resolve;
                            }))
                    )
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

                browser.close()

            logger.info("PDF generated successfully: %s (%d bytes)", pdf_abs_path, pdf_abs_path.stat().st_size)
            return True

        except Exception as e:
            logger.error("Failed to generate PDF for %s: %s", html_abs_path, e)
            return False
