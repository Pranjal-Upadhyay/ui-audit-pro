#!/usr/bin/env python3
"""
Network Interceptor — Captures and analyzes network requests/responses.

Uses Playwright or browser DevTools to intercept network traffic.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict


class NetworkInterceptor:
    """Captures network traffic from a live instance."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._logs = defaultdict(list)

    def get_logs(self, url: str) -> Dict:
        """Get network logs for a URL using Playwright."""
        logs = self._capture_with_playwright(url)
        if logs:
            return logs

        # Fallback: empty logs
        return {"url": url, "requests": [], "response": {}}

    def _capture_with_playwright(self, url: str) -> Optional[Dict]:
        """Capture network traffic using Playwright."""
        try:
            from playwright.sync_api import sync_playwright

            requests_log = []

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                # Intercept requests
                def handle_request(request):
                    requests_log.append({
                        "url": request.url,
                        "method": request.method,
                        "headers": dict(request.headers),
                        "timestamp": request.timing.get("startTime", 0),
                    })

                def handle_response(response):
                    # Find matching request
                    for req in requests_log:
                        if req["url"] == response.url and "status" not in req:
                            req["status"] = response.status
                            req["duration_ms"] = response.request.timing.get("responseEnd", 0) - response.request.timing.get("startTime", 0)
                            try:
                                req["response_headers"] = dict(response.headers)
                            except Exception:
                                req["response_headers"] = {}
                            break

                page.on("request", handle_request)
                page.on("response", handle_response)

                page.goto(url, wait_until="networkidle", timeout=30000)

                browser.close()

            # Save logs
            log_path = self.output_dir / f"{self._url_to_filename(url)}.json"
            with open(log_path, "w") as f:
                json.dump({"url": url, "requests": requests_log}, f, indent=2)

            return {"url": url, "requests": requests_log, "response": {}}

        except ImportError:
            return None
        except Exception as e:
            print(f"  Warning: Network capture failed for {url}: {e}")
            return None

    def _url_to_filename(self, url: str) -> str:
        """Convert URL to safe filename."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path.strip("/").replace("/", "_") or "index"
        return f"{parsed.netloc}_{path}"

    def analyze_logs(self, logs: Dict) -> List[Dict]:
        """Analyze captured network logs for issues."""
        findings = []
        requests = logs.get("requests", [])

        # Check for failed requests
        for req in requests:
            status = req.get("status")
            if status and status >= 400:
                findings.append({
                    "id": f"failed-request-{hash(req.get('url', ''))}",
                    "title": f"Failed request: {req.get('method', 'GET')} {req.get('url', '')}",
                    "category": "API Contract/Schema Drift",
                    "severity": "high" if status >= 500 else "medium",
                    "description": f"Request returned status {status}",
                    "evidence": f"URL: {req.get('url')}, Method: {req.get('method')}, Status: {status}",
                    "recommended_fix": "Investigate and fix the failing endpoint",
                    "effort": "medium",
                })

        # Check for slow requests
        for req in requests:
            duration = req.get("duration_ms", 0)
            if duration > 3000:
                findings.append({
                    "id": f"slow-request-{hash(req.get('url', ''))}",
                    "title": f"Slow request: {req.get('url', '')}",
                    "category": "Latency/Timeout Behavior",
                    "severity": "medium",
                    "description": f"Request took {duration:.0f}ms",
                    "evidence": f"URL: {req.get('url')}, Duration: {duration:.0f}ms",
                    "recommended_fix": "Optimize endpoint or add caching",
                    "effort": "medium",
                })

        return findings
