#!/usr/bin/env python3
"""
API Analyzer — Discovers and analyzes API call patterns in frontend code.

Extracts: endpoints, request/response types, error handling patterns,
loading state wiring, auth handling.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict


class APIAnalyzer:
    """Discovers and analyzes API call patterns in frontend code."""

    def __init__(self, codebase_path: Path):
        self.codebase = codebase_path
        self._api_cache = None
        self._contract_cache = None

    def discover_api_calls(self) -> List[Dict]:
        """Discover all API call sites in the codebase."""
        if self._api_cache is not None:
            return self._api_cache

        calls = []

        for ext in [".ts", ".tsx", ".js", ".jsx"]:
            for f in self.codebase.rglob(f"*{ext}"):
                if ".git" in str(f) or "node_modules" in str(f):
                    continue
                try:
                    content = f.read_text(encoding="utf-8")
                    file_calls = self._extract_api_calls_from_file(content, f)
                    calls.extend(file_calls)
                except (UnicodeDecodeError, OSError):
                    continue

        self._api_cache = calls
        return calls

    def _extract_api_calls_from_file(self, content: str, file_path: Path) -> List[Dict]:
        """Extract API calls from a single file."""
        calls = []
        rel_path = str(file_path.relative_to(self.codebase))

        # fetch() calls
        for match in re.finditer(
            r"""(?:const\s+(\w+)\s*=\s*)?await\s+fetch\s*\(\s*["'`]([^"'`]+)["'`]"""
            r"""(?:\s*,\s*\{([^}]*)\})?""",
            content,
            re.DOTALL,
        ):
            url = match.group(2)
            options = match.group(3) or ""
            method = "GET"
            method_match = re.search(r"method:\s*[\"'](\w+)[\"']", options)
            if method_match:
                method = method_match.group(1)

            calls.append({
                "type": "fetch",
                "url": url,
                "method": method,
                "file": rel_path,
                "line": content[:match.start()].count("\n") + 1,
                "options": options.strip(),
            })

        # axios calls
        for match in re.finditer(
            r"axios\.(get|post|put|patch|delete|request)\s*\(\s*"
            r"[\"']([^\"']+)[\"'](?:\s*,\s*([^)]+))?",
            content,
        ):
            calls.append({
                "type": "axios",
                "method": match.group(1).upper(),
                "url": match.group(2),
                "file": rel_path,
                "line": content[:match.start()].count("\n") + 1,
                "options": (match.group(3) or "").strip(),
            })

        # React Query useQuery
        for match in re.finditer(
            r"useQuery\s*(?:<[^>]+>)?\s*\(\s*"
            r"(?:\[['\"]([^'\"]+)['\"](?:\s*,\s*[^)]+)?\]|"
            r"\{\s*queryKey:\s*\[['\"]([^'\"]+)['\"]",
            content,
        ):
            key = match.group(1) or match.group(2)
            calls.append({
                "type": "react-query",
                "key": key,
                "file": rel_path,
                "line": content[:match.start()].count("\n") + 1,
            })

        # SWR useSWR
        for match in re.finditer(
            r"useSWR\s*(?:<[^>]+>)?\s*\(\s*['\"]([^'\"]+)['\"]",
            content,
        ):
            calls.append({
                "type": "swr",
                "key": match.group(1),
                "file": rel_path,
                "line": content[:match.start()].count("\n") + 1,
            })

        # API service/client classes
        for match in re.finditer(
            r"(?:this|self)\.\w+\.\w+\.(get|post|put|patch|delete)\s*\(\s*"
            r"[\"']([^\"']+)[\"']",
            content,
        ):
            calls.append({
                "type": "service",
                "method": match.group(1).upper(),
                "url": match.group(2),
                "file": rel_path,
                "line": content[:match.start()].count("\n") + 1,
            })

        return calls

    def extract_api_contracts(self) -> Dict:
        """Extract API contracts (OpenAPI, GraphQL schemas, TypeScript types)."""
        if self._contract_cache is not None:
            return self._contract_cache

        contracts = {
            "openapi": [],
            "graphql": [],
            "typescript_types": [],
            "zod_schemas": [],
        }

        # OpenAPI/Swagger specs
        for pattern in ["**/openapi.{json,yaml,yml}", "**/swagger.{json,yaml,yml}",
                        "**/api-spec.{json,yaml,yml}", "**/api.{json,yaml,yml}"]:
            for f in self.codebase.glob(pattern):
                if "node_modules" in str(f):
                    continue
                try:
                    content = f.read_text(encoding="utf-8")
                    contracts["openapi"].append({
                        "file": str(f.relative_to(self.codebase)),
                        "preview": content[:500],
                    })
                except (UnicodeDecodeError, OSError):
                    continue

        # GraphQL schemas
        for pattern in ["**/*.graphql", "**/*.gql", "**/schema.graphql"]:
            for f in self.codebase.glob(pattern):
                if "node_modules" in str(f):
                    continue
                try:
                    content = f.read_text(encoding="utf-8")
                    contracts["graphql"].append({
                        "file": str(f.relative_to(self.codebase)),
                        "preview": content[:500],
                    })
                except (UnicodeDecodeError, OSError):
                    continue

        # TypeScript API-related types
        for ext in [".ts", ".tsx"]:
            for f in self.codebase.rglob(f"*{ext}"):
                if ".git" in str(f) or "node_modules" in str(f):
                    continue
                try:
                    content = f.read_text(encoding="utf-8")
                    # Look for API response/request types
                    for match in re.finditer(
                        r"(?:interface|type)\s+(\w*(?:Response|Request|Payload|DTO|Schema)\w*)\s*(?:=\s*)?\{([^}]+)\}",
                        content,
                    ):
                        contracts["typescript_types"].append({
                            "name": match.group(1),
                            "file": str(f.relative_to(self.codebase)),
                            "definition": match.group(0)[:200],
                        })
                except (UnicodeDecodeError, OSError):
                    continue

        # Zod schemas
        for ext in [".ts", ".tsx", ".js"]:
            for f in self.codebase.rglob(f"*{ext}"):
                if ".git" in str(f) or "node_modules" in str(f):
                    continue
                try:
                    content = f.read_text(encoding="utf-8")
                    for match in re.finditer(
                        r"(?:const|export)\s+(\w+Schema)\s*=\s*z\.\w+",
                        content,
                    ):
                        contracts["zod_schemas"].append({
                            "name": match.group(1),
                            "file": str(f.relative_to(self.codebase)),
                        })
                except (UnicodeDecodeError, OSError):
                    continue

        self._contract_cache = contracts
        return contracts

    def check_error_handling(self, content: str, file_path: str) -> List[Dict]:
        """Check error handling patterns in API calls. Used by integration_checker."""
        findings = []

        fetch_calls = list(re.finditer(r"await\s+fetch\s*\(", content))
        catch_blocks = list(re.finditer(r"\}\s*catch", content))

        if fetch_calls and not catch_blocks:
            findings.append({
                "id": f"missing-error-handling-{hash(file_path)}",
                "title": "API calls without error handling",
                "category": "Loading/Error/Empty State Wiring",
                "severity": "high",
                "location": {"file": file_path},
                "description": "Found fetch() calls without try/catch blocks.",
                "evidence": f"Found {len(fetch_calls)} fetch calls, 0 catch blocks",
                "recommended_fix": "Wrap API calls in try/catch and handle errors in the UI",
                "effort": "small",
            })

        promise_calls = list(re.finditer(r"\.then\s*\(", content))
        if promise_calls and not catch_blocks and not re.search(r"\.catch\s*\(", content):
            findings.append({
                "id": f"unhandled-promise-{hash(file_path)}",
                "title": "Promise chains without .catch()",
                "category": "Unhandled Promise Rejections",
                "severity": "high",
                "location": {"file": file_path},
                "description": "Found .then() chains without .catch() or try/catch.",
                "evidence": f"Found {len(promise_calls)} .then() calls without error handling",
                "recommended_fix": "Add .catch() handlers or convert to async/await with try/catch",
                "effort": "small",
            })

        return findings

    def check_loading_states(self, content: str, file_path: str) -> List[Dict]:
        """Check for proper loading state wiring. Used by integration_checker."""
        findings = []

        has_loading = bool(re.search(r"loading|isLoading|isPending|pending", content))
        api_calls = re.findall(r"fetch\s*\(|axios\.|useQuery|useSWR", content)

        if api_calls and not has_loading:
            findings.append({
                "id": f"missing-loading-state-{hash(file_path)}",
                "title": "API calls without loading state",
                "category": "Loading/Error/Empty State Wiring",
                "severity": "medium",
                "location": {"file": file_path},
                "description": "Component makes API calls but doesn't track or display loading state.",
                "evidence": f"Found {len(api_calls)} API calls, no loading state indicator",
                "recommended_fix": "Add loading state tracking and show loading UI",
                "effort": "small",
            })

        has_error = bool(re.search(r"error|isError", content))
        if api_calls and not has_error:
            findings.append({
                "id": f"missing-error-state-{hash(file_path)}",
                "title": "API calls without error state handling",
                "category": "Loading/Error/Empty State Wiring",
                "severity": "medium",
                "location": {"file": file_path},
                "description": "Component makes API calls but doesn't track or display error state.",
                "evidence": f"Found {len(api_calls)} API calls, no error state indicator",
                "recommended_fix": "Add error state tracking and show error UI to users",
                "effort": "small",
            })

        return findings

    def check_type_safety(self, content: str, file_path: str) -> List[Dict]:
        """Check for type safety issues. Used by integration_checker."""
        findings = []

        any_types = re.findall(r":\s*any\b", content)
        if any_types:
            findings.append({
                "id": f"any-type-usage-{hash(file_path)}",
                "title": "Use of 'any' type in API-related code",
                "category": "Type Mismatches",
                "severity": "medium",
                "location": {"file": file_path},
                "description": f"Found {len(any_types)} uses of 'any' type.",
                "evidence": f"any type count: {len(any_types)}",
                "recommended_fix": "Define proper TypeScript interfaces for API responses",
                "effort": "small",
            })

        return findings
