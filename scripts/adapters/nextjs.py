#!/usr/bin/env python3
"""Next.js Adapter — Source-level analysis for Next.js applications."""

import re
from pathlib import Path
from typing import List, Optional
from .base import BaseAdapter, RouteInfo, APICallSite, ComponentInfo, TypeContract


class NextJSAdapter(BaseAdapter):
    """Adapter for Next.js applications (App Router + Pages Router)."""

    def list_routes(self) -> List[RouteInfo]:
        routes = []

        # App Router: app/ directory
        app_dir = self.codebase / "app"
        if app_dir.exists():
            routes.extend(self._scan_app_router(app_dir))

        # Pages Router: pages/ directory
        pages_dir = self.codebase / "pages"
        if pages_dir.exists():
            routes.extend(self._scan_pages_router(pages_dir))

        # Also check src/app and src/pages
        for prefix in ["src/app", "src/pages"]:
            alt_dir = self.codebase / prefix
            if alt_dir.exists():
                if "app" in prefix:
                    routes.extend(self._scan_app_router(alt_dir))
                else:
                    routes.extend(self._scan_pages_router(alt_dir))

        return routes

    def _scan_app_router(self, app_dir: Path) -> List[RouteInfo]:
        """Scan Next.js App Router directory."""
        routes = []
        # Exclude non-page files (layout, loading, error, etc.)
        # Use _glob_files helper for consistent file discovery
        page_patterns = [f"**/page.{ext}" for ext in ["tsx", "jsx", "ts", "js"]]
        page_files = self._glob_files(page_patterns)
        for page_file in page_files:
            # _glob_files already filters node_modules, no need for skip_files check
            rel = page_file.relative_to(app_dir)
            parts = []
            for part in rel.parent.parts:
                if part.startswith("[") and part.endswith("]"):
                    if part.startswith("[..."):
                        parts.append(f"*{part[4:-1]}")
                    else:
                        parts.append(f":{part[1:-1]}")
                elif part in ("app", "src"):
                    continue
                else:
                    parts.append(part)

            route_path = "/" + "/".join(parts) if parts else "/"
            routes.append(RouteInfo(
                path=route_path,
                file=str(page_file.relative_to(self.codebase)),
                framework="nextjs-app",
            ))
        return routes

    def _scan_pages_router(self, pages_dir: Path) -> List[RouteInfo]:
        """Scan Next.js Pages Router directory."""
        routes = []
        skip_files = {"_app", "_document", "_error", "404", "500"}

        all_patterns = [f"**/*.{ext}" for ext in ["tsx", "jsx", "ts", "js"]]
        all_files = self._glob_files(all_patterns)
        for page_file in all_files:
            if page_file.stem in skip_files:
                continue

            rel = page_file.relative_to(pages_dir)
            parts = []
            for part in rel.with_suffix("").parts:
                if part.startswith("[") and part.endswith("]"):
                    parts.append(f":{part[1:-1]}")
                elif part == "index":
                    continue
                else:
                    parts.append(part)

            route_path = "/" + "/".join(parts) if parts else "/"
            routes.append(RouteInfo(
                path=route_path,
                file=str(page_file.relative_to(self.codebase)),
                framework="nextjs-pages",
            ))
        return routes

    def find_api_call_sites(self) -> List[APICallSite]:
        calls = []

        # App Router API routes
        api_dir = self.codebase / "app" / "api"
        if not api_dir.exists():
            api_dir = self.codebase / "src" / "app" / "api"
        if api_dir.exists():
            # Use _glob_files for proper brace expansion
            api_files = self._glob_files(["**/route.{ts,js}"])
            # Filter to only files within the api directory
            for route_file in api_files:
                try:
                    route_file.relative_to(api_dir)
                except ValueError:
                    continue
                content = self._read_file(route_file)
                if not content:
                    continue

                # Find exported HTTP methods
                for method in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
                    if re.search(rf"export\s+(?:async\s+)?function\s+{method}", content):
                        rel_path = str(route_file.relative_to(self.codebase))
                        # Derive endpoint from file path
                        endpoint = "/" + str(route_file.relative_to(api_dir.parent)).replace("/route.ts", "").replace("/route.js", "")
                        calls.append(APICallSite(
                            endpoint=endpoint,
                            method=method,
                            file=rel_path,
                            line=content.find(f"export") + 1,
                            framework="nextjs-api",
                        ))

        # Client-side fetch/axios calls
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
                    framework="nextjs-client",
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
                    framework="nextjs-client",
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

            # Skip non-component files
            if name.startswith("_") or name in ("layout", "loading", "error", "not-found"):
                continue

            # Check for default export
            has_default = bool(re.search(
                r"export\s+default\s+(?:function|const|class)\s+\w+",
                content,
            ))

            # Extract props interface
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
                framework="nextjs",
                props=props,
                exports_default=has_default,
            ))

        return components

    def get_type_contracts(self) -> List[TypeContract]:
        contracts = []

        # TypeScript interfaces/types
        for file_path in self._glob_files(["**/*.{ts,tsx}"]):
            content = self._read_file(file_path)
            if not content:
                continue

            rel_path = str(file_path.relative_to(self.codebase))

            # Find ALL exported interfaces and types (not just API-related ones)
            for match in re.finditer(
                r"(?:export\s+)?(?:interface|type)\s+(\w+)\s*(?:=\s*)?\{([^}]+)\}",
                content,
            ):
                # Skip internal types like Props, State, etc. unless they have API-related fields
                type_name = match.group(1)
                fields = [m.group(1) for m in re.finditer(r"(\w+)\s*[?:]", match.group(2))]
                
                # Include all exported types - they may be used in API contracts
                contracts.append(TypeContract(
                    name=type_name,
                    file=rel_path,
                    kind="interface" if "interface" in match.group(0) else "type",
                    definition=match.group(0)[:200],
                    fields=fields,
                ))

        # Zod schemas
        for file_path in self._glob_files(["**/*.{ts,tsx,js}"]):
            content = self._read_file(file_path)
            if not content:
                continue

            rel_path = str(file_path.relative_to(self.codebase))

            for match in re.finditer(
                r"(?:export\s+)?(?:const|let)\s+(\w+Schema)\s*=\s*z\.\w+",
                content,
            ):
                contracts.append(TypeContract(
                    name=match.group(1),
                    file=rel_path,
                    kind="zod",
                    definition=match.group(0)[:200],
                ))

        # OpenAPI/Swagger specs
        for spec_file in self._glob_files(["**/openapi.{json,yaml,yml}", "**/swagger.{json,yaml,yml}"]):
            content = self._read_file(spec_file)
            if content:
                contracts.append(TypeContract(
                    name=spec_file.stem,
                    file=str(spec_file.relative_to(self.codebase)),
                    kind="openapi",
                    definition=content[:500],
                ))

        # GraphQL schemas
        for schema_file in self._glob_files(["**/*.graphql", "**/*.gql", "**/schema.graphql"]):
            content = self._read_file(schema_file)
            if content:
                contracts.append(TypeContract(
                    name=schema_file.stem,
                    file=str(schema_file.relative_to(self.codebase)),
                    kind="graphql",
                    definition=content[:500],
                ))

        return contracts
