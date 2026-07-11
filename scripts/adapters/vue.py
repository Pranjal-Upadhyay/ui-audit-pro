#!/usr/bin/env python3
"""Vue Adapter — Source-level analysis for Vue applications."""

import re
from pathlib import Path
from typing import List
from .base import BaseAdapter, RouteInfo, APICallSite, ComponentInfo, TypeContract


class VueAdapter(BaseAdapter):
    """Adapter for Vue.js applications."""

    def list_routes(self) -> List[RouteInfo]:
        routes = []

        # Look for Vue Router config
        for file_path in self._glob_files([
            "**/router/index.{ts,js}",
            "**/router.{ts,js}",
            "**/src/router.{ts,js}",
        ]):
            content = self._read_file(file_path)
            if not content:
                continue

            rel_path = str(file_path.relative_to(self.codebase))

            # Extract route paths
            for match in re.finditer(
                r"""path\s*:\s*["'`]([^"'`]+)["'`]""",
                content,
            ):
                path = match.group(1)
                if not path.startswith("/") and path != "*":
                    path = "/" + path
                routes.append(RouteInfo(
                    path=path,
                    file=rel_path,
                    framework="vue-router",
                ))

        # Also scan .vue files for page components
        for file_path in self._glob_files(["**/views/**/*.vue", "**/pages/**/*.vue"]):
            rel_path = str(file_path.relative_to(self.codebase))
            name = file_path.stem
            if name == "index":
                route_path = "/"
            else:
                route_path = f"/{name}"

            routes.append(RouteInfo(
                path=route_path,
                file=rel_path,
                framework="vue-sfc",
            ))

        return routes

    def find_api_call_sites(self) -> List[APICallSite]:
        calls = []

        for file_path in self._glob_files(["**/*.{vue,ts,js}"]):
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
                    framework="vue",
                ))

            # axios calls
            for match in re.finditer(
                r"axios\.(get|post|put|patch|delete)\s*\(\s*[\"']([^\"']+)[\"']",
                content,
            ):
                calls.append(APICallSite(
                    endpoint=match.group(2),
                    method=match.group(1).upper(),
                    file=rel_path,
                    line=content[:match.start()].count("\n") + 1,
                    framework="vue",
                ))

        return calls

    def find_component_definitions(self) -> List[ComponentInfo]:
        components = []

        for file_path in self._glob_files(["**/*.vue"]):
            rel_path = str(file_path.relative_to(self.codebase))
            name = file_path.stem

            if name.startswith("_"):
                continue

            content = self._read_file(file_path)
            props = []
            if content:
                # Extract defineProps
                props_match = re.search(r"defineProps<\{([^}]+)\}>", content)
                if props_match:
                    for prop_match in re.finditer(r"(\w+)\s*[?:]", props_match.group(1)):
                        props.append(prop_match.group(1))

            components.append(ComponentInfo(
                name=name,
                file=rel_path,
                line=1,
                framework="vue",
                props=props,
                exports_default=True,
            ))

        return components

    def get_type_contracts(self) -> List[TypeContract]:
        contracts = []

        for file_path in self._glob_files(["**/*.{ts,tsx}"]):
            content = self._read_file(file_path)
            if not content:
                continue

            rel_path = str(file_path.relative_to(self.codebase))

            for match in re.finditer(
                r"(?:export\s+)?(?:interface|type)\s+(\w*(?:Response|Request|Payload)\w*)\s*(?:=\s*)?\{([^}]+)\}",
                content,
            ):
                fields = [m.group(1) for m in re.finditer(r"(\w+)\s*[?:]", match.group(2))]
                contracts.append(TypeContract(
                    name=match.group(1),
                    file=rel_path,
                    kind="interface" if "interface" in match.group(0) else "type",
                    definition=match.group(0)[:200],
                    fields=fields,
                ))

        return contracts
