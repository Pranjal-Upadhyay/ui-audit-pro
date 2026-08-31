#!/usr/bin/env python3
"""
Network Interceptor — Captures and analyzes network requests/responses.

Uses Playwright or browser DevTools to intercept network traffic.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import defaultdict

SENSITIVE_KEY_RE = re.compile(r"token|secret|password|authorization|api[_-]?key", re.I)
REDACTED = "[REDACTED]"

MAX_BODY_BYTES = 256 * 1024
MAX_SHAPE_DEPTH = 4
MAX_SHAPE_ARRAY_ITEMS = 3


def redact(value: Any) -> Any:
    """Recursively replace values under sensitive-looking keys before they hit disk."""
    if isinstance(value, dict):
        return {
            k: (REDACTED if SENSITIVE_KEY_RE.search(str(k)) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def infer_shape(value: Any, _depth: int = 0) -> Any:
    """Describe a JSON value's structure as types, discarding the data itself."""
    if _depth >= MAX_SHAPE_DEPTH:
        return "..."
    if isinstance(value, dict):
        return {k: infer_shape(v, _depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [infer_shape(v, _depth + 1) for v in value[:MAX_SHAPE_ARRAY_ITEMS]]
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


class NetworkInterceptor:
    """Captures network traffic from a live instance."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._logs = defaultdict(list)

    # How many times to hit each endpoint. Intermittent failures and
    # schema variance are invisible to a single request, so probe repeatedly.
    PROBE_COUNT = 5
    # Only actively re-hit side-effect-free methods; never replay writes.
    SAFE_PROBE_METHODS = {"GET", "HEAD"}

    def get_logs(self, url: str) -> Optional[Dict]:
        """Get network logs for a URL using Playwright.

        Returns None if capture failed. Callers must treat None as a capture
        failure rather than as "this page made no requests".
        """
        return self._capture_with_playwright(url)

    def probe_endpoints(self, base_url: str, api_calls: List[Dict]) -> Dict[str, Dict]:
        """Actively hit each discovered safe endpoint PROBE_COUNT times.

        Passive page-load capture only sees endpoints the page calls on load.
        Probing reaches the rest and, by repeating, surfaces flakiness and
        schema variance. Returns a network_logs-shaped dict keyed by a
        `probe:<endpoint>` label so the standard integration checks consume it.
        Only GET/HEAD are probed — writes are never replayed.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            from . import PLAYWRIGHT_MISSING_MSG, BrowserUnavailableError
            raise BrowserUnavailableError(PLAYWRIGHT_MISSING_MSG) from e

        from urllib.parse import urljoin

        # Deduplicate endpoints by (method, endpoint); keep only safe methods.
        targets = {}
        for call in api_calls:
            method = (call.get("method") or "GET").upper()
            endpoint = call.get("endpoint") or ""
            if method not in self.SAFE_PROBE_METHODS or not endpoint:
                continue
            targets[(method, endpoint)] = urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/"))

        if not targets:
            return {}

        results: Dict[str, Dict] = {}
        try:
            with sync_playwright() as p:
                ctx = p.request.new_context()
                for (method, endpoint), full_url in targets.items():
                    attempts = []
                    for _ in range(self.PROBE_COUNT):
                        try:
                            resp = ctx.fetch(full_url, method=method, timeout=30000)
                        except Exception as e:
                            attempts.append({"url": full_url, "method": method, "error": str(e)})
                            continue
                        entry = {"url": full_url, "method": method, "status": resp.status}
                        headers = {}
                        try:
                            headers = dict(resp.headers)
                        except Exception:
                            pass
                        if "json" in str(headers.get("content-type", "")).lower():
                            try:
                                body = resp.json()
                                entry["response_body"] = redact(body)
                                entry["response_shape"] = infer_shape(body)
                            except Exception:
                                pass
                        attempts.append(entry)
                    results[f"probe:{endpoint}"] = {
                        "url": full_url,
                        "endpoint": endpoint,
                        "probed": True,
                        "requests": attempts,
                    }
                ctx.dispose()
        except Exception as e:
            print(f"  ERROR: Endpoint probing failed: {e}")
            return results

        return results

    def _capture_with_playwright(self, url: str) -> Optional[Dict]:
        """Capture network traffic using Playwright."""
        try:
            from playwright.sync_api import sync_playwright

            requests_log = []
            by_request = {}

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                # Intercept requests
                def handle_request(request):
                    entry = {
                        "url": request.url,
                        "method": request.method,
                        "headers": redact(dict(request.headers)),
                        "timestamp": (request.timing or {}).get("startTime", 0),
                    }
                    requests_log.append(entry)
                    by_request[id(request)] = entry

                def handle_response(response):
                    req = by_request.get(id(response.request))
                    if req is None:
                        return
                    req["status"] = response.status
                    timing = response.request.timing or {}
                    req["duration_ms"] = timing.get("responseEnd", 0) - timing.get("startTime", 0)
                    try:
                        headers = dict(response.headers)
                    except Exception:
                        headers = {}
                    req["response_headers"] = redact(headers)
                    self._attach_body(req, response, headers)

                page.on("request", handle_request)
                page.on("response", handle_response)

                page.goto(url, wait_until="networkidle", timeout=30000)

                browser.close()

            result = {
                "url": url,
                "requests": requests_log,
                "api_responses": self._index_api_responses(requests_log),
            }

            log_path = self.output_dir / f"{self._url_to_filename(url)}.json"
            with open(log_path, "w") as f:
                json.dump(result, f, indent=2)

            return result

        except ImportError as e:
            from . import PLAYWRIGHT_MISSING_MSG, BrowserUnavailableError
            raise BrowserUnavailableError(PLAYWRIGHT_MISSING_MSG) from e
        except Exception as e:
            print(f"  ERROR: Network capture failed for {url}: {e}")
            return None

    @staticmethod
    def _attach_body(req: Dict, response, headers: Dict):
        """Attach a redacted response body and its inferred shape to a request entry."""
        content_type = str(headers.get("content-type", "")).lower()
        if "json" not in content_type:
            return
        try:
            raw = response.body()
        except Exception:
            return
        if raw is None:
            return
        if len(raw) > MAX_BODY_BYTES:
            req["response_truncated"] = True
            return
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        req["response_body"] = redact(parsed)
        req["response_shape"] = infer_shape(parsed)

    @staticmethod
    def _index_api_responses(requests_log: List[Dict]) -> Dict[str, List[Dict]]:
        """Group captured responses by URL path so checks can look up an endpoint."""
        from urllib.parse import urlparse

        index = defaultdict(list)
        for req in requests_log:
            if "status" not in req:
                continue
            path = urlparse(req.get("url", "")).path or "/"
            index[path].append(req)
        return dict(index)

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
