#!/usr/bin/env python3
"""Static HTML Adapter — Source-level analysis for vanilla HTML/CSS/JS sites."""

import re
from pathlib import Path
from typing import List
from .base import BaseAdapter, RouteInfo, APICallSite, ComponentInfo, TypeContract


class StaticHTMLAdapter(BaseAdapter):
    """Adapter for static HTML/CSS/JS sites with no build tooling."""

    def list_routes(self) -> List[RouteInfo]:
        routes = []

        for html_file in self._glob_files(["**/*.html"]):
            rel_path = str(html_file.relative_to(self.codebase))
            name = html_file.stem

            if name == "index":
                route_path = "/"
            else:
                route_path = f"/{name}.html"

            routes.append(RouteInfo(
                path=route_path,
                file=rel_path,
                framework="static-html",
            ))

        return routes

    def find_api_call_sites(self) -> List[APICallSite]:
        calls = []

        for file_path in self._glob_files(["**/*.{js,html}"]):
            content = self._read_file(file_path)
            if not content:
                continue

            rel_path = str(file_path.relative_to(self.codebase))

            # fetch() calls
            for match in re.finditer(
                r"""(?:await\s+)?fetch\s*\(\s*["'`]([^"'`]+)["'`]""",
                content,
            ):
                calls.append(APICallSite(
                    endpoint=match.group(1),
                    method="GET",
                    file=rel_path,
                    line=content[:match.start()].count("\n") + 1,
                    framework="vanilla-js",
                ))

            # XMLHttpRequest
            for match in re.finditer(
                r"""\.open\s*\(\s*["'`](\w+)["'`]\s*,\s*["'`]([^"'`]+)["'`]""",
                content,
            ):
                calls.append(APICallSite(
                    endpoint=match.group(2),
                    method=match.group(1).upper(),
                    file=rel_path,
                    line=content[:match.start()].count("\n") + 1,
                    framework="vanilla-js",
                ))

            # jQuery AJAX
            for match in re.finditer(
                r"""\$\.(?:get|post|ajax)\s*\(\s*["'`]([^"'`]+)["'`]""",
                content,
            ):
                calls.append(APICallSite(
                    endpoint=match.group(1),
                    method="GET",
                    file=rel_path,
                    line=content[:match.start()].count("\n") + 1,
                    framework="jquery",
                ))

        return calls

    def find_component_definitions(self) -> List[ComponentInfo]:
        components = []

        # For static HTML, "components" are reusable HTML snippets or JS classes
        for file_path in self._glob_files(["**/*.js"]):
            content = self._read_file(file_path)
            if not content:
                continue

            rel_path = str(file_path.relative_to(self.codebase))

            # Look for class definitions that might be components
            for match in re.finditer(
                r"class\s+(\w+)",
                content,
            ):
                components.append(ComponentInfo(
                    name=match.group(1),
                    file=rel_path,
                    line=content[:match.start()].count("\n") + 1,
                    framework="vanilla-js",
                    exports_default=False,
                ))

            # Look for function definitions
            for match in re.finditer(
                r"(?:export\s+)?function\s+(\w+)\s*\(",
                content,
            ):
                components.append(ComponentInfo(
                    name=match.group(1),
                    file=rel_path,
                    line=content[:match.start()].count("\n") + 1,
                    framework="vanilla-js",
                    exports_default=False,
                ))

        return components

    def get_type_contracts(self) -> List[TypeContract]:
        # Static HTML/JS sites typically don't have type contracts
        # Return empty list gracefully
        return []
