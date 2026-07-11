#!/usr/bin/env python3
"""React Generic Adapter — Source-level analysis for React applications."""

import re
from pathlib import Path
from typing import List
from .base import BaseAdapter, RouteInfo, APICallSite, ComponentInfo, TypeContract


class ReactAdapter(BaseAdapter):
    """Adapter for generic React applications (CRA, Vite, etc.)."""

    def list_routes(self) -> List[RouteInfo]:
        routes = []

        # Look for React Router config
        for file_path in self._glob_files([
            "**/router.{ts,tsx,js,jsx}",
            "**/routes.{ts,tsx,js,jsx}",
            "**/App.{tsx,jsx}",
            "**/App.ts",
        ]):
            content = self._read_file(file_path)
            if not content:
                continue

            rel_path = str(file_path.relative_to(self.codebase))

            # Extract route paths from React Router
            for match in re.finditer(
                r"""path\s*=\s*["'`]([^"'`]+)["'`]""",
                content,
            ):
                path = match.group(1)
                if path != "/" and not path.startswith("/"):
                    path = "/" + path
                routes.append(RouteInfo(
                    path=path,
                    file=rel_path,
                    framework="react-router",
                ))

            # Also check for route objects
            for match in re.finditer(
                r"""\{\s*path:\s*["'`]([^"'`]+)["'`]\s*,""",
                content,
            ):
                path = match.group(1)
                if not path.startswith("/"):
                    path = "/" + path
                routes.append(RouteInfo(
                    path=path,
                    file=rel_path,
                    framework="react-router",
                ))

        return routes

    def find_api_call_sites(self) -> List[APICallSite]:
        calls = []

        for file_path in self._glob_files(["**/*.{tsx,jsx,ts,js}"]):
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
                    framework="react",
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
                    framework="react",
                ))

            # React Query
            for match in re.finditer(
                r"useQuery\s*(?:<[^>]+>)?\s*\(\s*\[['\"]([^'\"]+)['\"]",
                content,
            ):
                calls.append(APICallSite(
                    endpoint=match.group(1),
                    method="GET",
                    file=rel_path,
                    line=content[:match.start()].count("\n") + 1,
                    framework="react-query",
                    hooks=["useQuery"],
                ))

            # SWR
            for match in re.finditer(
                r"useSWR\s*\(\s*['\"]([^'\"]+)['\"]",
                content,
            ):
                calls.append(APICallSite(
                    endpoint=match.group(1),
                    method="GET",
                    file=rel_path,
                    line=content[:match.start()].count("\n") + 1,
                    framework="swr",
                    hooks=["useSWR"],
                ))

        return calls

    def find_component_definitions(self) -> List[ComponentInfo]:
        components = []

        for file_path in self._glob_files(["**/*.{tsx,jsx}"]):
            content = self._read_file(file_path)
            if not content:
                continue

            rel_path = str(file_path.relative_to(self.codebase))
            name = file_path.stem

            # Skip test files and non-components
            if name.endswith((".test", ".spec", ".stories")) or name.startswith("_"):
                continue

            # Check for component pattern
            is_component = bool(re.search(
                r"(?:export\s+(?:default\s+)?)?(?:function|const)\s+" + re.escape(name),
                content,
            ))

            if not is_component:
                continue

            # Check for default export
            has_default = bool(re.search(
                r"export\s+default",
                content,
            ))

            # Extract props
            props = []
            props_match = re.search(
                r"(?:interface|type)\s+\w+Props\s*(?:=\s*)?\{([^}]+)\}",
                content,
            )
            if props_match:
                for prop_match in re.finditer(r"(\w+)\s*[?:]", props_match.group(1)):
                    props.append(prop_match.group(1))

            components.append(ComponentInfo(
                name=name,
                file=rel_path,
                line=1,
                framework="react",
                props=props,
                exports_default=has_default,
            ))

        return components

    def get_type_contracts(self) -> List[TypeContract]:
        contracts = []

        for file_path in self._glob_files(["**/*.{ts,tsx}"]):
            content = self._read_file(file_path)
            if not content:
                continue

            rel_path = str(file_path.relative_to(self.codebase))

            # TypeScript interfaces/types
            for match in re.finditer(
                r"(?:export\s+)?(?:interface|type)\s+(\w*(?:Response|Request|Payload|DTO|Props)\w*)\s*(?:=\s*)?\{([^}]+)\}",
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

            # PropTypes
            for match in re.finditer(
                r"(\w+)\.propTypes\s*=\s*\{([^}]+)\}",
                content,
            ):
                fields = [m.group(1) for m in re.finditer(r"(\w+)\s*:", match.group(2))]
                contracts.append(TypeContract(
                    name=f"{match.group(1)}Props",
                    file=rel_path,
                    kind="proptypes",
                    definition=match.group(0)[:200],
                    fields=fields,
                ))

        return contracts
