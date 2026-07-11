#!/usr/bin/env python3
"""
Stack Detector — Auto-detects the frontend/backend framework stack.

Inspects package.json, config files, directory structure, and file patterns
to determine which adapters to use for source-level analysis.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field


@dataclass
class StackInfo:
    """Detected stack information."""
    frontend_framework: Optional[str] = None  # react, nextjs, vue, svelte, angular, vanilla
    backend_framework: Optional[str] = None   # express, fastify, node, python, go, unknown
    language: str = "javascript"              # javascript, typescript, python, etc.
    has_typescript: bool = False
    has_build_tooling: bool = False
    package_manager: Optional[str] = None     # npm, yarn, pnpm, bun
    config_files: List[str] = field(default_factory=list)
    adapter_names: List[str] = field(default_factory=list)
    detected_at: str = ""
    warnings: List[str] = field(default_factory=list)


class StackDetector:
    """Detects the technology stack of a codebase."""

    # Framework signature files
    NEXTJS_SIGNATURES = [
        "next.config.js", "next.config.mjs", "next.config.ts",
        "app/layout.tsx", "app/layout.jsx", "pages/_app.tsx",
    ]
    REACT_SIGNATURES = [
        "src/App.tsx", "src/App.jsx", "src/App.js",
        "src/main.tsx", "src/main.jsx", "src/index.tsx",
    ]
    VUE_SIGNATURES = [
        "src/App.vue", "vue.config.js", "vite.config.ts", "vite.config.js",
        "nuxt.config.ts", "nuxt.config.js",
    ]
    SVELTE_SIGNATURES = [
        "svelte.config.js", "src/routes",
    ]
    ANGULAR_SIGNATURES = [
        "angular.json", "src/app/app.module.ts",
    ]

    BACKEND_SIGNATURES = {
        "express": ["express", "express.js"],
        "fastify": ["fastify"],
        "nextjs-api": ["next", "app/api"],
        "python-flask": ["flask", "Flask"],
        "python-django": ["django", "Django"],
        "python-fastapi": ["fastapi", "FastAPI"],
        "go-gin": ["gin-gonic"],
        "go-echo": ["labstack/echo"],
    }

    def __init__(self, codebase_path: str):
        self.codebase = Path(codebase_path)
        self.stack = StackInfo(detected_at=str(self.codebase))

    def detect(self) -> StackInfo:
        """Run full stack detection."""
        self._detect_package_manager()
        self._detect_language()
        self._detect_frontend_framework()
        self._detect_backend_framework()
        self._detect_typescript()
        self._detect_build_tooling()
        self._assign_adapters()
        return self.stack

    def _detect_package_manager(self):
        """Detect which package manager is used."""
        if (self.codebase / "package-lock.json").exists():
            self.stack.package_manager = "npm"
        elif (self.codebase / "yarn.lock").exists():
            self.stack.package_manager = "yarn"
        elif (self.codebase / "pnpm-lock.yaml").exists():
            self.stack.package_manager = "pnpm"
        elif (self.codebase / "bun.lockb").exists():
            self.stack.package_manager = "bun"

    def _detect_language(self):
        """Detect primary programming language."""
        # Check for Python
        if (self.codebase / "requirements.txt").exists() or \
           (self.codebase / "pyproject.toml").exists() or \
           (self.codebase / "setup.py").exists():
            self.stack.language = "python"
            return

        # Check for Go
        if (self.codebase / "go.mod").exists():
            self.stack.language = "go"
            return

        # Check for Rust
        if (self.codebase / "Cargo.toml").exists():
            self.stack.language = "rust"
            return

        # Default to JavaScript/TypeScript
        self.stack.language = "javascript"

    def _detect_frontend_framework(self):
        """Detect frontend framework from config files and directory structure."""
        # Check package.json dependencies
        pkg_json = self._load_package_json()
        if pkg_json:
            deps = {}
            deps.update(pkg_json.get("dependencies", {}))
            deps.update(pkg_json.get("devDependencies", {}))

            # Next.js (check before React since Next includes React)
            if "next" in deps:
                self.stack.frontend_framework = "nextjs"
                self.stack.config_files.append("next.config.*")
                return

            # React
            if "react" in deps:
                self.stack.frontend_framework = "react"
                return

            # Vue
            if "vue" in deps:
                self.stack.frontend_framework = "vue"
                return

            # Svelte
            if "svelte" in deps:
                self.stack.frontend_framework = "svelte"
                return

            # Angular
            if "@angular/core" in deps:
                self.stack.frontend_framework = "angular"
                return

        # Check directory structure as fallback
        if self._has_files(self.NEXTJS_SIGNATURES):
            self.stack.frontend_framework = "nextjs"
        elif self._has_files(self.VUE_SIGNATURES):
            self.stack.frontend_framework = "vue"
        elif self._has_files(self.SVELTE_SIGNATURES):
            self.stack.frontend_framework = "svelte"
        elif self._has_files(self.ANGULAR_SIGNATURES):
            self.stack.frontend_framework = "angular"
        elif self._has_files(self.REACT_SIGNATURES):
            self.stack.frontend_framework = "react"
        else:
            # Check if there are any HTML files (static site)
            html_files = list(self.codebase.glob("**/*.html"))
            if html_files:
                self.stack.frontend_framework = "vanilla"
            else:
                self.stack.frontend_framework = "unknown"
                self.stack.warnings.append("Could not detect frontend framework")

    def _detect_backend_framework(self):
        """Detect backend framework."""
        if self.stack.language == "python":
            pkg_json = self._load_package_json()
            req_txt = self._load_requirements_txt()

            if req_txt:
                req_lower = req_txt.lower()
                if "fastapi" in req_lower:
                    self.stack.backend_framework = "python-fastapi"
                elif "flask" in req_lower:
                    self.stack.backend_framework = "python-flask"
                elif "django" in req_lower:
                    self.stack.backend_framework = "python-django"
            return

        if self.stack.language == "go":
            go_mod = self._load_file("go.mod")
            if go_mod:
                if "gin-gonic" in go_mod:
                    self.stack.backend_framework = "go-gin"
                elif "labstack/echo" in go_mod:
                    self.stack.backend_framework = "go-echo"
                else:
                    self.stack.backend_framework = "go"
            return

        # JavaScript/Node.js backend detection
        pkg_json = self._load_package_json()
        if pkg_json:
            deps = {}
            deps.update(pkg_json.get("dependencies", {}))

            if "express" in deps:
                self.stack.backend_framework = "express"
            elif "fastify" in deps:
                self.stack.backend_framework = "fastify"
            elif "next" in deps and self.stack.frontend_framework == "nextjs":
                self.stack.backend_framework = "nextjs-api"

    def _detect_typescript(self):
        """Check if project uses TypeScript."""
        if (self.codebase / "tsconfig.json").exists():
            self.stack.has_typescript = True
            self.stack.language = "typescript"
            self.stack.config_files.append("tsconfig.json")
        elif (self.codebase / "jsconfig.json").exists():
            self.stack.config_files.append("jsconfig.json")

    def _detect_build_tooling(self):
        """Check for build tooling."""
        pkg_json = self._load_package_json()
        if pkg_json:
            all_deps = {}
            all_deps.update(pkg_json.get("dependencies", {}))
            all_deps.update(pkg_json.get("devDependencies", {}))

            build_tools = ["webpack", "vite", "rollup", "esbuild", "parcel", "turbopack"]
            for tool in build_tools:
                if tool in all_deps:
                    self.stack.has_build_tooling = True
                    break

    def _assign_adapters(self):
        """Assign appropriate adapters based on detected stack."""
        adapters = set()

        # Frontend adapters
        if self.stack.frontend_framework == "nextjs":
            adapters.add("nextjs")
        elif self.stack.frontend_framework == "react":
            adapters.add("react")
        elif self.stack.frontend_framework == "vue":
            adapters.add("vue")
        elif self.stack.frontend_framework == "svelte":
            adapters.add("svelte")
        elif self.stack.frontend_framework == "angular":
            adapters.add("angular")
        elif self.stack.frontend_framework == "vanilla":
            adapters.add("static-html")

        # Backend adapters
        if self.stack.backend_framework in ("express", "fastify"):
            adapters.add("node-express")
        elif self.stack.backend_framework in ("python-flask", "python-django", "python-fastapi"):
            adapters.add("python-backend")

        # If no adapters matched, use static-html as fallback
        if not adapters:
            adapters.add("static-html")
            self.stack.warnings.append(
                "No specific adapter matched; using static-html fallback. "
                "Source-level tracing will be limited."
            )

        self.stack.adapter_names = sorted(adapters)

    def _load_package_json(self) -> Optional[Dict]:
        """Load and parse package.json."""
        pkg_path = self.codebase / "package.json"
        if pkg_path.exists():
            try:
                return json.loads(pkg_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
        return None

    def _load_requirements_txt(self) -> Optional[str]:
        """Load requirements.txt content."""
        req_path = self.codebase / "requirements.txt"
        if req_path.exists():
            try:
                return req_path.read_text(encoding="utf-8")
            except OSError:
                return None
        return None

    def _load_file(self, filename: str) -> Optional[str]:
        """Load a file's content."""
        file_path = self.codebase / filename
        if file_path.exists():
            try:
                return file_path.read_text(encoding="utf-8")
            except OSError:
                return None
        return None

    def _has_files(self, signatures: List[str]) -> bool:
        """Check if any of the signature files exist."""
        for sig in signatures:
            if (self.codebase / sig).exists():
                return True
        return False

    def get_adapter_config(self) -> Dict:
        """Get configuration for loading adapters."""
        return {
            "codebase": str(self.codebase),
            "stack": {
                "frontend": self.stack.frontend_framework,
                "backend": self.stack.backend_framework,
                "language": self.stack.language,
                "typescript": self.stack.has_typescript,
            },
            "adapters": self.stack.adapter_names,
        }


def detect_stack(codebase_path: str) -> StackInfo:
    """Convenience function to detect stack."""
    detector = StackDetector(codebase_path)
    return detector.detect()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python detect_stack.py <codebase_path>")
        sys.exit(1)

    stack = detect_stack(sys.argv[1])
    print(f"Frontend: {stack.frontend_framework}")
    print(f"Backend: {stack.backend_framework}")
    print(f"Language: {stack.language}")
    print(f"TypeScript: {stack.has_typescript}")
    print(f"Adapters: {stack.adapter_names}")
    if stack.warnings:
        print(f"Warnings: {stack.warnings}")
