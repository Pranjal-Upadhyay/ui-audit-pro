#!/usr/bin/env python3
"""
Screenshot Capture — Captures full-page screenshots from live instances.

Uses Playwright or Selenium for browser automation.
Falls back to basic HTTP requests if neither is available.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse


class ScreenshotCapture:
    """Captures screenshots and crawls routes from a live instance."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._browser = None

    def crawl_routes(self, base_url: str) -> List[Dict]:
        """Crawl a live instance to discover routes."""
        routes = []
        visited = set()
        queue = [base_url]

        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError:
            print("  Warning: requests/beautifulsoup4 not installed. Using basic crawl.")
            return self._basic_crawl(base_url)

        while queue and len(visited) < 100:  # Limit crawl depth
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code != 200:
                    continue

                routes.append({
                    "url": url,
                    "status": resp.status_code,
                    "content_type": resp.headers.get("content-type", ""),
                })

                # Parse links
                soup = BeautifulSoup(resp.text, "html.parser")
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    full_url = urljoin(url, href)
                    parsed = urlparse(full_url)

                    # Only crawl same-origin
                    if parsed.netloc == urlparse(base_url).netloc:
                        if full_url not in visited:
                            queue.append(full_url)

            except Exception as e:
                print(f"  Warning: Failed to crawl {url}: {e}")
                continue

        return routes

    def _basic_crawl(self, base_url: str) -> List[Dict]:
        """Basic crawl using just urllib."""
        import urllib.request
        from html.parser import HTMLParser

        routes = []
        visited = set()
        queue = [base_url]

        class LinkExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.links = []

            def handle_starttag(self, tag, attrs):
                if tag == "a":
                    for attr, value in attrs:
                        if attr == "href" and value:
                            self.links.append(value)

        while queue and len(visited) < 50:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            try:
                req = urllib.request.Request(url, headers={"User-Agent": "UIAuditPro/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    content = resp.read().decode("utf-8", errors="replace")
                    routes.append({"url": url, "status": resp.status})

                    extractor = LinkExtractor()
                    extractor.feed(content)

                    parsed_base = urlparse(base_url)
                    for link in extractor.links:
                        full_url = urljoin(url, link)
                        parsed = urlparse(full_url)
                        if parsed.netloc == parsed_base.netloc and full_url not in visited:
                            queue.append(full_url)

            except Exception:
                continue

        return routes

    def capture(self, url: str) -> Optional[Path]:
        """Capture a full-page screenshot of a URL."""
        # Try Playwright first
        screenshot_path = self._capture_playwright(url)
        if screenshot_path:
            return screenshot_path

        # Try Selenium
        screenshot_path = self._capture_selenium(url)
        if screenshot_path:
            return screenshot_path

        # Fallback: just save the URL for manual capture
        url_file = self.output_dir / f"{self._url_to_filename(url)}.url.txt"
        url_file.write_text(url)
        return url_file

    def _capture_playwright(self, url: str) -> Optional[Path]:
        """Capture using Playwright."""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.goto(url, wait_until="networkidle", timeout=30000)

                screenshot_path = self.output_dir / f"{self._url_to_filename(url)}.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                browser.close()

                return screenshot_path
        except ImportError:
            return None
        except Exception as e:
            print(f"  Warning: Playwright capture failed for {url}: {e}")
            return None

    def _capture_selenium(self, url: str) -> Optional[Path]:
        """Capture using Selenium."""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options

            options = Options()
            options.add_argument("--headless")
            options.add_argument("--window-size=1440,900")
            options.add_argument("--no-sandbox")

            driver = webdriver.Chrome(options=options)
            driver.get(url)

            import time
            time.sleep(2)  # Wait for page load

            screenshot_path = self.output_dir / f"{self._url_to_filename(url)}.png"
            driver.save_screenshot(str(screenshot_path))
            driver.quit()

            return screenshot_path
        except ImportError:
            return None
        except Exception as e:
            print(f"  Warning: Selenium capture failed for {url}: {e}")
            return None

    def _url_to_filename(self, url: str) -> str:
        """Convert a URL to a safe filename."""
        parsed = urlparse(url)
        path = parsed.path.strip("/").replace("/", "_") or "index"
        return f"{parsed.netloc}_{path}"
