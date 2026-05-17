"""
Web crawler module for fetching HTML pages.

Handles fetching HTML content using requests or Playwright.
"""

from time import sleep
from typing import Optional

import requests


class Crawler:
    """Handles fetching HTML pages from target URLs."""

    def __init__(
        self,
        timeout: int = 30,
        use_playwright: bool = False,
        max_retries: int = 3,
    ):
        """
        Initialize the crawler.

        Args:
            timeout: Request timeout in seconds
            use_playwright: If True, use Playwright for JavaScript rendering
            max_retries: Number of fetch attempts before failing
        """
        self.timeout = timeout
        self.use_playwright = use_playwright
        self.max_retries = max(1, max_retries)
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; SchemaMarkupAuditor/1.0; "
                "+https://github.com/rknoncoder/schema-markup-auditor)"
            )
        }

    def fetch(self, url: str) -> Optional[str]:
        """
        Fetch HTML content from a URL.

        Args:
            url: The URL to fetch

        Returns:
            HTML content as string, or None if fetch fails
        """
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                if self.use_playwright:
                    return self._fetch_with_playwright(url)
                return self._fetch_with_requests(url)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    sleep(min(attempt * 2, 10))

        print(f"Error fetching {url}: {last_error}")
        return None

    def _fetch_with_requests(self, url: str) -> Optional[str]:
        """Fetch HTML using requests library."""
        response = requests.get(url, headers=self.headers, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def _fetch_with_playwright(self, url: str) -> Optional[str]:
        """Fetch HTML using Playwright (requires installation)."""
        from playwright.sync_api import sync_playwright

        timeout_ms = self.timeout * 1000
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(extra_http_headers=self.headers)
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                return page.content()
            finally:
                browser.close()
