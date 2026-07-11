#!/usr/bin/env python3
"""
Integration Checker — Runs frontend-backend integration checks.

Implements all 13 integration categories from the audit spec.
"""

import re
from typing import Dict, List
from collections import defaultdict


class IntegrationChecker:
    """Runs frontend-backend integration checks against captured data."""

    def run_check(self, check_id: str, capture_data: Dict, codebase=None) -> List[Dict]:
        """Run a specific integration check and return findings."""
        method = getattr(self, f"_check_{check_id}", None)
        if method:
            return method(capture_data, codebase)
        return []

    def _check_api_contract(self, data: Dict, codebase=None) -> List[Dict]:
        """Check API contract/schema drift."""
        findings = []
        api_contracts = data.get("api_contracts", {})
        network_logs = data.get("network_logs", {})

        openapi_specs = api_contracts.get("openapi", [])
        ts_types = api_contracts.get("typescript_types", [])

        # Check if frontend types exist for API calls
        if network_logs and not ts_types and not openapi_specs:
            findings.append({
                "id": "no-api-contract",
                "title": "No API contract definition found",
                "category": "API Contract/Schema Drift",
                "severity": "high",
                "description": "Frontend makes API calls but no OpenAPI spec, GraphQL schema, or TypeScript response types were found",
                "recommended_fix": "Define TypeScript interfaces for all API responses, or maintain an OpenAPI spec",
                "effort": "medium",
            })

        # Check for fields in types that don't match network responses
        for url, logs in network_logs.items():
            if not isinstance(logs, dict):
                continue
            response = logs.get("response", {})
            response_fields = set(response.keys()) if isinstance(response, dict) else set()

            for ts_type in ts_types:
                type_fields = set(re.findall(r"(\w+)\s*[?:]", ts_type.get("definition", "")))
                unused_fields = type_fields - response_fields
                missing_fields = response_fields - type_fields

                if missing_fields:
                    findings.append({
                        "id": f"contract-drift-{ts_type['name']}",
                        "title": f"Type '{ts_type['name']}' missing fields from API response",
                        "category": "API Contract/Schema Drift",
                        "severity": "medium",
                        "location": {"file": ts_type.get("file", "unknown")},
                        "description": f"Backend sends fields not in TypeScript type: {missing_fields}",
                        "evidence": f"Missing from type: {missing_fields}. Response fields: {response_fields}",
                        "recommended_fix": f"Add missing fields to the {ts_type['name']} interface",
                        "effort": "small",
                    })

        return findings

    def _check_type_mismatches(self, data: Dict, codebase=None) -> List[Dict]:
        """Check for type mismatches between frontend and backend.
        
        Cross-references adapter-discovered TypeScript interfaces against
        actual network response payloads to detect runtime type mismatches.
        Also analyzes API route source code to detect type issues in code-only mode.
        """
        findings = []
        network_logs = data.get("network_logs", {})
        type_contracts = data.get("type_contracts", [])
        api_calls = data.get("api_calls", [])

        # Build a map of field names to their expected types from TypeScript interfaces
        ts_field_types = {}  # field_name -> {"expected_type": "number", "source": "Order", ...}
        for contract in type_contracts:
            if contract.get("kind") in ("interface", "type"):
                definition = contract.get("definition", "")
                # Parse field: type mappings from the interface definition
                for match in re.finditer(r"(\w+)\s*:\s*(\w+)", definition):
                    field_name = match.group(1)
                    field_type = match.group(2)
                    if field_name not in ts_field_types:
                        ts_field_types[field_name] = {
                            "expected_type": field_type,
                            "source": contract.get("name", "unknown"),
                            "file": contract.get("file", ""),
                        }

        # Check each network response against TypeScript type definitions
        for url, logs in network_logs.items():
            if not isinstance(logs, dict):
                continue
            response = logs.get("response", {})
            if not isinstance(response, dict):
                continue

            for key, value in response.items():
                actual_type = type(value).__name__

                # Check against TypeScript type definitions
                if key in ts_field_types:
                    expected_type = ts_field_types[key]["expected_type"].lower()
                    source = ts_field_types[key]["source"]
                    file = ts_field_types[key]["file"]

                    # Map TypeScript types to Python types
                    type_mismatches = {
                        ("number", "str"): True,
                        ("string", "int"): True,
                        ("string", "float"): True,
                        ("boolean", "str"): True,
                    }

                    is_mismatch = type_mismatches.get((expected_type, actual_type), False)

                    if is_mismatch:
                        findings.append({
                            "id": f"type-contract-mismatch-{key}-{hash(url)}",
                            "title": f"Type contract mismatch: '{key}' is {actual_type} but TypeScript declares {expected_type}",
                            "category": "Type Mismatches",
                            "severity": "high",
                            "location": {
                                "route": url,
                                "file": file,
                                "type_source": source,
                            },
                            "description": (
                                f"Field '{key}' in API response is '{value}' (type: {actual_type}), "
                                f"but TypeScript interface '{source}' declares it as {expected_type}. "
                                f"This will cause silent formatting/math bugs at runtime."
                            ),
                            "evidence": {
                                "field": key,
                                "expected_type": expected_type,
                                "actual_type": actual_type,
                                "actual_value": value,
                                "typescript_source": source,
                                "typescript_file": file,
                            },
                            "recommended_fix": (
                                f"Either fix the backend to send '{key}' as {expected_type}, "
                                f"or update the TypeScript interface '{source}' to declare '{key}' as {actual_type}"
                            ),
                            "effort": "small",
                        })
                else:
                    # No TypeScript type found — heuristic check for string-looking numbers
                    if isinstance(value, str) and value.replace(".", "").replace("-", "").isdigit():
                        findings.append({
                            "id": f"type-mismatch-{key}-{hash(url)}",
                            "title": f"Numeric value '{key}' sent as string (no TypeScript type found)",
                            "category": "Type Mismatches",
                            "severity": "medium",
                            "location": {"route": url},
                            "description": f"Field '{key}' is '{value}' (string) but likely should be a number",
                            "evidence": f"Value: '{value}' (type: {actual_type})",
                            "recommended_fix": f"Ensure backend sends '{key}' as a number, or define a TypeScript type",
                            "effort": "small",
                        })

        # CODE-ONLY MODE: Analyze source code for type mismatches
        if codebase and not network_logs and ts_field_types:
            # Collect all unique source files from API calls
            files_to_check = set()
            for call in api_calls:
                file_path = call.get("file", "")
                if file_path:
                    files_to_check.add((file_path, call.get("line", 0), call.get("endpoint", "")))

            # Also discover API route handler files via adapter if available
            try:
                from adapters.nextjs import NextJSAdapter
                adapter = NextJSAdapter(str(codebase))
                for call in adapter.find_api_call_sites():
                    file_path = call.file
                    if file_path:
                        files_to_check.add((file_path, call.line, call.endpoint))
            except Exception:
                pass

            for file_path, line, endpoint in files_to_check:
                if file_path:
                    try:
                        source_path = codebase / file_path
                        if source_path.exists():
                            source_content = source_path.read_text(encoding="utf-8")
                            for field_name, field_info in ts_field_types.items():
                                expected_type = field_info["expected_type"].lower()
                                if expected_type == "number":
                                    str_pattern = rf"{field_name}\s*:\s*['\"]([^'\"]+)['\"]"
                                    str_match = re.search(str_pattern, source_content)
                                    if str_match:
                                        value = str_match.group(1)
                                        if value.replace(".", "").replace("-", "").isdigit():
                                            findings.append({
                                                "id": f"type-mismatch-source-{field_name}-{file_path}",
                                                "title": f"Type contract mismatch: '{field_name}' is a string but TypeScript declares number",
                                                "category": "Type Mismatches",
                                                "severity": "high",
                                                "location": {
                                                    "file": file_path,
                                                    "line": source_content[:str_match.start()].count("\n") + 1,
                                                    "type_source": field_info["source"],
                                                },
                                                "description": (
                                                    f"API route returns '{field_name}' as string '{value}' but "
                                                    f"TypeScript interface '{field_info['source']}' declares it as {expected_type}. "
                                                    f"This will cause silent formatting/math bugs at runtime."
                                                ),
                                                "evidence": {
                                                    "field": field_name,
                                                    "expected_type": expected_type,
                                                    "actual_type": "string",
                                                    "actual_value": value,
                                                    "typescript_source": field_info["source"],
                                                    "typescript_file": field_info["file"],
                                                    "api_route_file": file_path,
                                                },
                                                "recommended_fix": (
                                                    f"Fix the API route to return '{field_name}' as a number instead of string '{value}'"
                                                ),
                                                "effort": "small",
                                            })
                    except (OSError, UnicodeDecodeError):
                        pass

        return findings

    def _check_state_wiring(self, data: Dict, codebase=None) -> List[Dict]:
        """Check loading/error/empty state wiring (functional)."""
        findings = []
        network_logs = data.get("network_logs", {})

        for url, logs in network_logs.items():
            if not isinstance(logs, dict):
                continue

            requests = logs.get("requests", [])
            for req in requests:
                status = req.get("status")
                if status and status >= 400:
                    # Check if there's error handling by examining response headers and context
                    has_error_ui = req.get("has_error_ui", False)
                    # Also check if there's an error boundary or error component nearby
                    has_error_boundary = req.get("has_error_boundary", False)
                    if not has_error_ui and not has_error_boundary:
                        findings.append({
                            "id": f"unhandled-error-{url}-{status}",
                            "title": f"HTTP {status} error without user feedback",
                            "category": "Loading/Error/Empty State Wiring",
                            "severity": "high",
                            "location": {"route": url, "endpoint": req.get("url", "unknown")},
                            "description": f"API returned {status} but no error state was displayed to the user",
                            "evidence": f"Status: {status}, URL: {req.get('url')}",
                            "recommended_fix": "Handle this error status and display appropriate error UI",
                            "effort": "small",
                        })

        return findings

    def _check_unhandled_errors(self, data: Dict, codebase=None) -> List[Dict]:
        """Check for unhandled promise rejections / swallowed errors.
        
        Uses discovery's api_calls data (from adapters) to find API calls
        in source code and check for missing error handling.
        """
        findings = []
        api_calls = data.get("api_calls", [])

        # Source-level analysis: check for API calls without error handling
        if codebase and api_calls:
            for call in api_calls:
                file_path = call.get("file", "")
                line = call.get("line", 0)
                if file_path:
                    try:
                        source_path = codebase / file_path
                        if source_path.exists():
                            file_content = source_path.read_text(encoding="utf-8")
                            # Check surrounding context for error handling
                            lines = file_content.split("\n")
                            start = max(0, line - 5)
                            end = min(len(lines), line + 10)
                            context = "\n".join(lines[start:end])

                            # Strip comments before checking for error handling patterns
                            code_lines = []
                            for cl in lines[start:end]:
                                # Remove single-line comments
                                stripped = re.sub(r'//.*$', '', cl)
                                # Remove inline comments after code
                                stripped = re.sub(r'//.*$', '', stripped)
                                code_lines.append(stripped)
                            code_context = "\n".join(code_lines)

                            # Check for actual try/catch blocks or .catch() calls (not in comments)
                            has_catch = bool(re.search(r'\btry\b', code_context)) or bool(re.search(r'\bcatch\s*\(', code_context)) or bool(re.search(r'\.catch\s*\(', code_context))

                            if not has_catch:
                                endpoint = call.get("endpoint", "unknown")
                                findings.append({
                                    "id": f"swallowed-error-{file_path}-{line}",
                                    "title": f"API call to {endpoint} without error handling at line {line}",
                                    "category": "Unhandled Promise Rejections",
                                    "severity": "high",
                                    "location": {
                                        "file": file_path,
                                        "line": line,
                                        "endpoint": endpoint,
                                    },
                                    "description": (
                                        f"Fetch call to '{endpoint}' found without surrounding try/catch or .catch(). "
                                        f"If the network request fails, this will cause an unhandled promise rejection."
                                    ),
                                    "evidence": f"Context: {context[:200]}",
                                    "recommended_fix": "Add try/catch or .catch() handler around the fetch call",
                                    "effort": "small",
                                })
                    except (OSError, UnicodeDecodeError):
                        pass

        # Also check via APIAnalyzer if available and codebase provided
        if codebase and not api_calls:
            try:
                from analyzers.api_analyzer import APIAnalyzer
                analyzer = APIAnalyzer(codebase)
                calls = analyzer.discover_api_calls()

                for call in calls:
                    file_path = call.get("file", "")
                    if file_path:
                        try:
                            file_content = open(codebase / file_path).read()
                            call_line = call.get("line", 0)
                            lines = file_content.split("\n")
                            start = max(0, call_line - 5)
                            end = min(len(lines), call_line + 10)
                            context = "\n".join(lines[start:end])

                            if "catch" not in context and ".catch" not in context:
                                findings.append({
                                    "id": f"swallowed-error-{file_path}-{call_line}",
                                    "title": f"API call without error handling at line {call_line}",
                                    "category": "Unhandled Promise Rejections",
                                    "severity": "high",
                                    "location": {"file": file_path, "line": call_line},
                                    "description": "API call found without surrounding error handling",
                                    "evidence": f"Context: {context[:200]}",
                                    "recommended_fix": "Add try/catch or .catch() handler",
                                    "effort": "small",
                                })
                        except (FileNotFoundError, OSError):
                            pass
            except ImportError:
                pass

        return findings

    def _check_race_conditions(self, data: Dict, codebase=None) -> List[Dict]:
        """Check for race conditions and stale data."""
        findings = []
        network_logs = data.get("network_logs", {})

        for url, logs in network_logs.items():
            if not isinstance(logs, dict):
                continue

            requests = logs.get("requests", [])
            # Check for multiple in-flight requests to same endpoint
            endpoint_groups = defaultdict(list)
            for req in requests:
                endpoint = req.get("url", "")
                endpoint_groups[endpoint].append(req)

            for endpoint, reqs in endpoint_groups.items():
                if len(reqs) > 1:
                    # Check if abort controllers are used
                    has_abort = any(r.get("has_abort", False) for r in reqs)
                    if not has_abort:
                        findings.append({
                            "id": f"race-condition-{hash(endpoint)}",
                            "title": f"Potential race condition on {endpoint}",
                            "category": "Race Conditions/Stale Data",
                            "severity": "medium",
                            "location": {"route": url, "endpoint": endpoint},
                            "description": f"Multiple requests to same endpoint without abort controllers",
                            "evidence": f"Request count: {len(reqs)}",
                            "recommended_fix": "Use AbortController to cancel in-flight requests when parameters change",
                            "effort": "small",
                        })

        return findings

    def _check_optimistic_ui(self, data: Dict, codebase=None) -> List[Dict]:
        """Check optimistic UI correctness."""
        findings = []
        network_logs = data.get("network_logs", {})

        for url, logs in network_logs.items():
            if not isinstance(logs, dict):
                continue
            requests = logs.get("requests", [])
            # Check for optimistic updates without rollback
            for req in requests:
                if req.get("method") in ("POST", "PUT", "DELETE") and req.get("status", 200) >= 400:
                    has_rollback = req.get("has_rollback", False)
                    if not has_rollback:
                        findings.append({
                            "id": f"no-rollback-{hash(req.get('url', ''))}",
                            "title": f"Failed {req.get('method')} without rollback",
                            "category": "Optimistic UI Correctness",
                            "severity": "medium",
                            "location": {"route": url, "endpoint": req.get("url", "unknown")},
                            "description": "Optimistic update may not rollback on failure",
                            "evidence": f"Method: {req.get('method')}, Status: {req.get('status')}",
                            "recommended_fix": "Implement rollback logic for failed optimistic updates",
                            "effort": "medium",
                        })
        return findings

    def _check_auth_handling(self, data: Dict, codebase=None) -> List[Dict]:
        """Check auth/session boundary handling."""
        findings = []
        network_logs = data.get("network_logs", {})

        for url, logs in network_logs.items():
            if not isinstance(logs, dict):
                continue

            requests = logs.get("requests", [])
            for req in requests:
                status = req.get("status")
                if status == 401:
                    # Check if there's a re-auth flow by looking for login redirects or auth modals
                    has_reauth = req.get("has_reauth_flow", False)
                    has_login_redirect = "/login" in req.get("url", "") or "/auth" in req.get("url", "")
                    if not has_reauth and not has_login_redirect:
                        findings.append({
                            "id": f"no-reauth-{url}",
                            "title": "401 response without re-authentication flow",
                            "category": "Auth/Session Boundary Handling",
                            "severity": "critical",
                            "location": {"route": url, "endpoint": req.get("url", "unknown")},
                            "description": "API returned 401 (unauthorized) but no re-authentication prompt was shown",
                            "evidence": f"Status: 401, URL: {req.get('url')}",
                            "recommended_fix": "Implement automatic redirect to login or show re-authentication modal on 401",
                            "effort": "small",
                        })
                elif status == 403:
                    has_forbidden_ui = req.get("has_forbidden_ui", False)
                    has_forbidden_page = req.get("has_forbidden_page", False)
                    if not has_forbidden_ui and not has_forbidden_page:
                        findings.append({
                            "id": f"no-forbidden-ui-{url}",
                            "title": "403 response without forbidden state UI",
                            "category": "Auth/Session Boundary Handling",
                            "severity": "high",
                            "location": {"route": url, "endpoint": req.get("url", "unknown")},
                            "description": "API returned 403 (forbidden) but no appropriate UI was shown",
                            "recommended_fix": "Show a 'permission denied' message or hide the feature entirely",
                            "effort": "small",
                        })

        return findings

    def _check_latency_timeout(self, data: Dict, codebase=None) -> List[Dict]:
        """Check latency and timeout behavior."""
        findings = []
        network_logs = data.get("network_logs", {})

        for url, logs in network_logs.items():
            if not isinstance(logs, dict):
                continue

            requests = logs.get("requests", [])
            for req in requests:
                duration = req.get("duration_ms", 0)
                if duration > 5000:  # 5 seconds
                    has_loading_ui = req.get("has_loading_ui", False)
                    if not has_loading_ui:
                        findings.append({
                            "id": f"slow-no-loading-{url}-{req.get('url', '')}",
                            "title": f"Slow request ({duration}ms) without loading indicator",
                            "category": "Latency/Timeout Behavior",
                            "severity": "medium",
                            "location": {"route": url, "endpoint": req.get("url", "unknown")},
                            "description": f"Request took {duration}ms but no loading state was shown",
                            "evidence": f"Duration: {duration}ms",
                            "recommended_fix": "Show loading indicator for requests taking > 300ms",
                            "effort": "trivial",
                        })

        return findings

    def _check_pagination_data(self, data: Dict, codebase=None) -> List[Dict]:
        """Check pagination/data consistency across requests."""
        findings = []
        network_logs = data.get("network_logs", {})

        for url, logs in network_logs.items():
            if not isinstance(logs, dict):
                continue
            requests = logs.get("requests", [])
            # Check for pagination parameter changes
            page_params = set()
            for req in requests:
                if "page" in req.get("url", "") or "offset" in req.get("url", ""):
                    page_params.add(req.get("url", ""))

            if len(page_params) > 1:
                findings.append({
                    "id": f"pagination-params-{hash(url)}",
                    "title": "Inconsistent pagination parameters",
                    "category": "Pagination/Data Consistency",
                    "severity": "low",
                    "location": {"route": url},
                    "description": f"Found {len(page_params)} different pagination parameter patterns",
                    "recommended_fix": "Standardize pagination parameters across all list endpoints",
                    "effort": "small",
                })
        return findings

    def _check_websocket_sync(self, data: Dict, codebase=None) -> List[Dict]:
        """Check real-time/websocket sync."""
        findings = []
        network_logs = data.get("network_logs", {})

        for url, logs in network_logs.items():
            if not isinstance(logs, dict):
                continue
            requests = logs.get("requests", [])
            ws_requests = [r for r in requests if "ws" in r.get("url", "") or "websocket" in r.get("url", "")]

            if ws_requests:
                # Check for potential sync issues
                findings.append({
                    "id": f"ws-sync-check-{hash(url)}",
                    "title": "WebSocket connection detected - manual sync verification needed",
                    "category": "Real-time/Websocket Sync",
                    "severity": "low",
                    "location": {"route": url},
                    "description": f"Found {len(ws_requests)} WebSocket connections - verify state reconciliation with REST data",
                    "recommended_fix": "Ensure websocket updates are reconciled with last REST-fetched state",
                    "effort": "medium",
                })
        return findings

    def _check_file_transfer(self, data: Dict, codebase=None) -> List[Dict]:
        """Check file upload/download edge cases."""
        findings = []
        network_logs = data.get("network_logs", {})

        for url, logs in network_logs.items():
            if not isinstance(logs, dict):
                continue
            requests = logs.get("requests", [])
            upload_requests = [r for r in requests if r.get("method") == "POST" and "file" in r.get("url", "").lower()]

            if upload_requests:
                for req in upload_requests:
                    has_progress = req.get("has_progress_indicator", False)
                    if not has_progress:
                        findings.append({
                            "id": f"upload-no-progress-{hash(req.get('url', ''))}",
                            "title": "File upload without progress indicator",
                            "category": "File Upload/Download Edge Cases",
                            "severity": "low",
                            "location": {"route": url, "endpoint": req.get("url", "unknown")},
                            "description": "File upload endpoint lacks progress feedback",
                            "recommended_fix": "Add progress indicator for file uploads",
                            "effort": "small",
                        })
        return findings

    def _check_double_submit(self, data: Dict, codebase=None) -> List[Dict]:
        """Check idempotency / double-submit bugs."""
        findings = []
        network_logs = data.get("network_logs", {})

        for url, logs in network_logs.items():
            if not isinstance(logs, dict):
                continue

            requests = logs.get("requests", [])
            # Check for duplicate POST/PUT/DELETE requests within short time
            write_requests = [r for r in requests if r.get("method") in ("POST", "PUT", "DELETE")]

            endpoint_times = defaultdict(list)
            for req in write_requests:
                endpoint = req.get("url", "")
                timestamp = req.get("timestamp", 0)
                endpoint_times[endpoint].append(timestamp)

            for endpoint, times in endpoint_times.items():
                if len(times) > 1:
                    # Check if requests are within 1 second
                    times_sorted = sorted(times)
                    for i in range(len(times_sorted) - 1):
                        if times_sorted[i + 1] - times_sorted[i] < 1000:
                            findings.append({
                                "id": f"double-submit-{hash(endpoint)}",
                                "title": f"Potential double-submit on {endpoint}",
                                "category": "Idempotency/Double-Submit",
                                "severity": "high",
                                "location": {"route": url, "endpoint": endpoint},
                                "description": "Multiple write requests to same endpoint within 1 second",
                                "evidence": f"Request times: {times_sorted}",
                                "recommended_fix": "Disable submit button after first click, or implement idempotency keys",
                                "effort": "small",
                            })
                            break

        return findings

    def _check_timezone_issues(self, data: Dict, codebase=None) -> List[Dict]:
        """Check localization/timezone mismatches."""
        findings = []
        network_logs = data.get("network_logs", {})

        for url, logs in network_logs.items():
            if not isinstance(logs, dict):
                continue

            response = logs.get("response", {})
            if not isinstance(response, dict):
                continue

            # Check for raw UTC timestamps
            for key, value in response.items():
                if isinstance(value, str) and "T" in value and "Z" in value:
                    # Looks like a raw ISO timestamp
                    findings.append({
                        "id": f"raw-utc-{key}-{hash(url)}",
                        "title": f"Raw UTC timestamp '{key}' displayed without conversion",
                        "category": "Localization/Timezone Mismatches",
                        "severity": "medium",
                        "location": {"route": url},
                        "description": f"Field '{key}' contains a raw UTC timestamp that may not be converted to user's timezone",
                        "evidence": f"Value: {value}",
                        "recommended_fix": "Convert UTC timestamps to user's local timezone before display",
                        "effort": "small",
                    })

        return findings
