#!/usr/bin/env python3
"""
Component Analyzer — Discovers and analyzes frontend components.

Handles: React, Vue, Svelte, Angular components.
Extracts: routes, component tree, props, state management patterns.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set
from collections import defaultdict


class ComponentAnalyzer:
    """Discovers and analyzes frontend components."""

    ROUTE_PATTERNS = {
        "react-router": [
            r"<Route\s+path=[\"']([^\"']+)[\"']",
            r"Route\s*\(\s*\{\s*path:\s*[\"']([^\"']+)[\"']",
            r"path:\s*[\"']([^\"']+)[\"']",
        ],
        "nextjs": [
            r"export\s+default\s+function\s+Page",  # app router pages
            r"getServerSideProps|getStaticProps",  # pages router
        ],
        "vue-router": [
            r"path:\s*[\"']([^\"']+)[\"']",
            r"component:\s*(\w+)",
        ],
        "sveltekit": [
            r"\+page\.(svelte|ts|js)",
            r"\+layout\.(svelte|ts|js)",
        ],
    }

    COMPONENT_PATTERNS = {
        "react": [
            r"(?:export\s+(?:default\s+)?)?(?:function|const)\s+(\w+)\s*(?:=\s*)?(?:\(|=>)",
            r"React\.memo\(\s*(\w+)",
            r"forwardRef\(\s*(?:\([^)]*\)\s*=>|function\s+(\w+))",
        ],
        "vue": [
            r"<script[^>]*>.*?export\s+default\s+\{",
            r"defineComponent\(\s*\{",
            r"<template>",
        ],
        "svelte": [
            r"<script[^>]*>",
            r"export\s+let\s+(\w+)",
        ],
    }

    def __init__(self, codebase_path: Path):
        self.codebase = codebase_path
        self._route_cache = None
        self._component_cache = None

    def discover_routes(self) -> List[Dict]:
        """Discover all routes in the application."""
        if self._route_cache is not None:
            return self._route_cache

        routes = []

        # Check for Next.js app router
        app_dir = self.codebase / "app" or self.codebase / "src" / "app"
        if app_dir.exists():
            routes.extend(self._discover_nextjs_routes(app_dir))

        # Check for Next.js pages router
        pages_dir = self.codebase / "pages" or self.codebase / "src" / "pages"
        if pages_dir.exists():
            routes.extend(self._discover_pages_routes(pages_dir))

        # Check for React Router config files
        for pattern in ["**/router.*", "**/routes.*", "**/App.*"]:
            for f in self.codebase.glob(pattern):
                if ".git" in str(f) or "node_modules" in str(f):
                    continue
                try:
                    content = f.read_text(encoding="utf-8")
                    routes.extend(self._extract_routes_from_config(content, str(f.relative_to(self.codebase))))
                except (UnicodeDecodeError, OSError):
                    continue

        # Check for Vue Router
        for f in self.codebase.rglob("**/router/**"):
            if f.is_file() and f.suffix in {".ts", ".js"}:
                try:
                    content = f.read_text(encoding="utf-8")
                    routes.extend(self._extract_routes_from_config(content, str(f.relative_to(self.codebase))))
                except (UnicodeDecodeError, OSError):
                    continue

        # Deduplicate
        seen = set()
        unique_routes = []
        for r in routes:
            path = r.get("path", r.get("url", ""))
            if path not in seen:
                seen.add(path)
                unique_routes.append(r)

        self._route_cache = unique_routes
        return unique_routes

    def _discover_nextjs_routes(self, app_dir: Path) -> List[Dict]:
        """Discover routes from Next.js app directory."""
        routes = []
        for page_file in app_dir.rglob("+page.{tsx,jsx,ts,js,svelte}"):
            # Convert file path to route
            rel = page_file.relative_to(app_dir)
            parts = []
            for part in rel.parent.parts:
                if part.startswith("[") and part.endswith("]"):
                    parts.append(f":{part[1:-1]}")
                elif part.startswith("[...") and part.endswith("]"):
                    parts.append(f"*{part[4:-1]}")
                elif part == "app":
                    continue
                else:
                    parts.append(part)

            route_path = "/" + "/".join(parts) if parts else "/"
            routes.append({
                "path": route_path,
                "file": str(page_file.relative_to(self.codebase)),
                "framework": "nextjs-app",
            })

        return routes

    def _discover_pages_routes(self, pages_dir: Path) -> List[Dict]:
        """Discover routes from Next.js pages directory."""
        routes = []
        for page_file in pages_dir.rglob("*.{tsx,jsx,ts,js,vue,svelte}"):
            if page_file.name.startswith("_"):
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
            routes.append({
                "path": route_path,
                "file": str(page_file.relative_to(self.codebase)),
                "framework": "nextjs-pages",
            })

        return routes

    def _extract_routes_from_config(self, content: str, file_path: str) -> List[Dict]:
        """Extract routes from a router configuration file."""
        routes = []

        for router_type, patterns in self.ROUTE_PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, content):
                    path = match.group(1) if match.lastindex else match.group(0)
                    if path.startswith("/"):
                        routes.append({
                            "path": path,
                            "file": file_path,
                            "framework": router_type,
                        })

        return routes

    def discover_components(self) -> List[Dict]:
        """Discover all components in the codebase."""
        if self._component_cache is not None:
            return self._component_cache

        components = []

        for ext in [".tsx", ".jsx", ".vue", ".svelte"]:
            for f in self.codebase.rglob(f"*{ext}"):
                if ".git" in str(f) or "node_modules" in str(f):
                    continue
                try:
                    content = f.read_text(encoding="utf-8")
                    component_info = self._analyze_component_file(content, f)
                    if component_info:
                        components.append(component_info)
                except (UnicodeDecodeError, OSError):
                    continue

        self._component_cache = components
        return components

    def _analyze_component_file(self, content: str, file_path: Path) -> Optional[Dict]:
        """Analyze a single component file."""
        rel_path = str(file_path.relative_to(self.codebase))

        # Detect framework
        framework = "unknown"
        if file_path.suffix in {".tsx", ".jsx"}:
            if "from 'react'" in content or 'from "react"' in content or "React." in content:
                framework = "react"
        elif file_path.suffix == ".vue":
            framework = "vue"
        elif file_path.suffix == ".svelte":
            framework = "svelte"

        # Extract component name
        name = file_path.stem
        if name.startswith("use") and len(name) > 3:
            component_type = "hook"
        elif name.startswith("_"):
            component_type = "private"
        else:
            component_type = "component"

        # Extract props interface/type
        props = self._extract_props(content, framework)

        # Extract state management patterns
        state = self._extract_state_patterns(content, framework)

        # Extract API calls
        api_calls = self._extract_api_calls(content)

        # Extract styles
        styles = self._extract_style_patterns(content)

        return {
            "name": name,
            "file": rel_path,
            "framework": framework,
            "type": component_type,
            "props": props,
            "state": state,
            "api_calls": api_calls,
            "styles": styles,
        }

    def _extract_props(self, content: str, framework: str) -> List[str]:
        """Extract prop names from a component."""
        props = []

        if framework == "react":
            # TypeScript interface/type props
            for match in re.finditer(
                r"(?:interface|type)\s+\w+Props\s*(?:=\s*)?\{([^}]+)\}",
                content,
            ):
                for prop_match in re.finditer(r"(\w+)\s*[?:]", match.group(1)):
                    props.append(prop_match.group(1))

            # Function parameter destructuring
            for match in re.finditer(
                r"(?:function|const)\s+\w+\s*(?:=\s*)?(?:\(|<[^>]*>\()?\s*\{([^}]+)\}",
                content,
            ):
                for prop_match in re.finditer(r"(\w+)\s*[,:]", match.group(1)):
                    if prop_match.group(1) not in props:
                        props.append(prop_match.group(1))

        elif framework == "vue":
            for match in re.finditer(r"defineProps<\{([^}]+)\}>", content):
                for prop_match in re.finditer(r"(\w+)\s*[?:]", match.group(1)):
                    props.append(prop_match.group(1))

        return props

    def _extract_state_patterns(self, content: str, framework: str) -> List[Dict]:
        """Extract state management patterns."""
        patterns = []

        if framework == "react":
            # useState
            for match in re.finditer(
                r"const\s+\[(\w+),\s*set\w+\]\s*=\s*useState", content
            ):
                patterns.append({"type": "useState", "name": match.group(1)})

            # useEffect
            for match in re.finditer(r"useEffect\s*\(", content):
                patterns.append({"type": "useEffect"})

            # useContext
            for match in re.finditer(r"useContext\s*\((\w+)\)", content):
                patterns.append({"type": "useContext", "name": match.group(1)})

            # useReducer
            for match in re.finditer(
                r"const\s+\[(\w+),\s*dispatch\]\s*=\s*useReducer", content
            ):
                patterns.append({"type": "useReducer", "name": match.group(1)})

            # Zustand/Redux stores
            for match in re.finditer(r"use(\w+Store)\s*\(", content):
                patterns.append({"type": "store", "name": match.group(1)})

        return patterns

    def _extract_api_calls(self, content: str) -> List[Dict]:
        """Extract API call patterns."""
        calls = []

        # fetch
        for match in re.finditer(
            r"""fetch\s*\(\s*["'`]([^"'`]+)["'`]""", content
        ):
            calls.append({"type": "fetch", "url": match.group(1)})

        # axios
        for match in re.finditer(
            r"axios\.(get|post|put|patch|delete)\s*\(\s*[\"']([^\"']+)[\"']",
            content,
        ):
            calls.append({"type": "axios", "method": match.group(1), "url": match.group(2)})

        # React Query / SWR
        for match in re.finditer(
            r"useQuery\s*(?:<[^>]+>)?\s*\(\s*(?:\[['\"]([^'\"]+)['\"]|\{\s*queryKey:\s*\[['\"]([^'\"]+)['\"]\]\})",
            content,
        ):
            key = match.group(1) or match.group(2)
            if key:
                calls.append({"type": "react-query", "key": key})

        for match in re.finditer(
            r"useSWR\s*\(\s*['\"]([^'\"]+)['\"]", content
        ):
            calls.append({"type": "swr", "key": match.group(1)})

        return calls

    def _extract_style_patterns(self, content: str) -> Dict:
        """Extract style-related patterns."""
        styles = {}

        # CSS modules import
        if re.search(r"import\s+.*\.module\.css", content):
            styles["css_modules"] = True

        # Tailwind usage
        if re.search(r'className=["\'][^"\']*(?:flex|grid|p-|m-|text-|bg-)', content):
            styles["tailwind"] = True

        # styled-components
        if re.search(r"styled\.\w+|styled\(", content):
            styles["styled_components"] = True

        # CSS-in-JS (emotion, etc.)
        if re.search(r"css`|css\(", content):
            styles["css_in_js"] = True

        return styles

    def extract_component_tree(self) -> Dict:
        """Extract the component hierarchy tree."""
        components = self.discover_components()

        tree = {
            "pages": [],
            "layouts": [],
            "components": [],
            "hooks": [],
            "utils": [],
        }

        for comp in components:
            name = comp.get("name", "")
            comp_type = comp.get("type", "component")
            file_path = comp.get("file", "")

            entry = {
                "name": name,
                "file": file_path,
                "props": comp.get("props", []),
                "api_calls": comp.get("api_calls", []),
            }

            if "page" in name.lower() or "/pages/" in file_path or "/app/" in file_path:
                tree["pages"].append(entry)
            elif "layout" in name.lower():
                tree["layouts"].append(entry)
            elif comp_type == "hook":
                tree["hooks"].append(entry)
            else:
                tree["components"].append(entry)

        return tree
