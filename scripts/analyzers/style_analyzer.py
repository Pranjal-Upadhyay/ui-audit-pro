#!/usr/bin/env python3
"""
Style Analyzer — Extracts and analyzes CSS/styles from codebases.

Handles: CSS files, CSS modules, Tailwind classes, styled-components,
CSS-in-JS (emotion, styled-jsx), inline styles, CSS custom properties.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set
from collections import defaultdict


class StyleAnalyzer:
    """Extracts and analyzes styles from a frontend codebase."""

    CSS_EXTENSIONS = {".css", ".scss", ".sass", ".less", ".styl"}
    JS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}

    # Tailwind spacing scale (px values)
    TAILWIND_SPACING = {
        "0": 0, "0.5": 2, "1": 4, "1.5": 6, "2": 8, "2.5": 10,
        "3": 12, "3.5": 14, "4": 16, "5": 20, "6": 24, "7": 28,
        "8": 32, "9": 36, "10": 40, "11": 44, "12": 48, "14": 56,
        "16": 64, "20": 80, "24": 96, "28": 112, "32": 128,
        "36": 144, "40": 160, "44": 176, "48": 192, "52": 208,
        "56": 224, "60": 240, "64": 256, "72": 288, "80": 320,
        "96": 384,
    }

    # Common font size scales
    COMMON_FONT_SCALES = {
        "xs": 12, "sm": 14, "base": 16, "lg": 18, "xl": 20,
        "2xl": 24, "3xl": 30, "4xl": 36, "5xl": 48, "6xl": 60,
    }

    def __init__(self, codebase_path: Path):
        self.codebase = codebase_path
        self._style_cache = {}
        self._token_cache = None

    def find_design_tokens(self) -> Optional[Dict]:
        """Find design token files (tokens.json, theme.ts, etc.)."""
        if self._token_cache is not None:
            return self._token_cache

        token_patterns = [
            "**/tokens.json", "**/tokens.ts", "**/tokens.js",
            "**/theme.json", "**/theme.ts", "**/theme.js",
            "**/design-tokens.*", "**/variables.css",
            "**/styles/tokens.*", "**/styles/theme.*",
            "**/tailwind.config.*", "**/postcss.config.*",
        ]

        tokens = {}
        for pattern in token_patterns:
            for f in self.codebase.glob(pattern):
                try:
                    content = f.read_text(encoding="utf-8")
                    tokens[str(f.relative_to(self.codebase))] = {
                        "type": f.suffix,
                        "size": len(content),
                        "preview": content[:500],
                    }
                except (UnicodeDecodeError, OSError):
                    continue

        self._token_cache = tokens if tokens else None
        return self._token_cache

    def extract_all_styles(self) -> Dict:
        """Extract all style definitions from the codebase."""
        styles = {
            "css_files": {},
            "tailwind_classes": defaultdict(set),
            "inline_styles": [],
            "styled_components": [],
            "css_variables": {},
            "font_families": set(),
            "font_sizes": set(),
            "colors": set(),
            "border_radii": set(),
            "spacing_values": set(),
            "shadows": set(),
            "transitions": set(),
            "breakpoints": set(),
        }

        # Scan CSS files
        for ext in self.CSS_EXTENSIONS:
            for f in self.codebase.rglob(f"*{ext}"):
                if ".git" in str(f) or "node_modules" in str(f):
                    continue
                try:
                    content = f.read_text(encoding="utf-8")
                    rel_path = str(f.relative_to(self.codebase))
                    styles["css_files"][rel_path] = content
                    self._extract_css_values(content, styles)
                except (UnicodeDecodeError, OSError):
                    continue

        # Scan JS/TS files for styled-components, CSS-in-JS, inline styles
        for ext in self.JS_EXTENSIONS:
            for f in self.codebase.rglob(f"*{ext}"):
                if ".git" in str(f) or "node_modules" in str(f):
                    continue
                try:
                    content = f.read_text(encoding="utf-8")
                    self._extract_js_styles(content, str(f.relative_to(self.codebase)), styles)
                except (UnicodeDecodeError, OSError):
                    continue

        # Convert sets to lists for JSON serialization
        for key in ["font_families", "font_sizes", "colors", "border_radii",
                     "spacing_values", "shadows", "transitions", "breakpoints"]:
            styles[key] = sorted(styles[key])

        return styles

    def _extract_css_values(self, css_content: str, styles: Dict):
        """Extract design values from CSS content."""
        # Font families
        for match in re.finditer(r"font-family:\s*([^;]+)", css_content):
            styles["font_families"].add(match.group(1).strip())

        # Font sizes
        for match in re.finditer(r"font-size:\s*([\d.]+(?:px|rem|em))", css_content):
            styles["font_sizes"].add(match.group(1))

        # Colors (hex, rgb, rgba, hsl)
        for match in re.finditer(
            r"(?:color|background-color|border-color|fill|stroke):\s*"
            r"(#[0-9a-fA-F]{3,8}|rgb\([^)]+\)|rgba\([^)]+\)|hsl\([^)]+\))",
            css_content,
        ):
            styles["colors"].add(match.group(1))

        # Border radius
        for match in re.finditer(r"border-radius:\s*([^;]+)", css_content):
            styles["border_radii"].add(match.group(1).strip())

        # Spacing (margin, padding)
        for match in re.finditer(
            r"(?:margin|padding)(?:-(?:top|right|bottom|left))?:\s*([\d.]+(?:px|rem|em))",
            css_content,
        ):
            styles["spacing_values"].add(match.group(1))

        # Box shadows
        for match in re.finditer(r"box-shadow:\s*([^;]+)", css_content):
            styles["shadows"].add(match.group(1).strip())

        # Transitions
        for match in re.finditer(r"transition:\s*([^;]+)", css_content):
            styles["transitions"].add(match.group(1).strip())

        # CSS custom properties (design tokens)
        for match in re.finditer(r"--([\w-]+):\s*([^;]+)", css_content):
            var_name = match.group(1)
            var_value = match.group(2).strip()
            if any(
                keyword in var_name.lower()
                for keyword in ["color", "font", "spacing", "radius", "shadow", "breakpoint"]
            ):
                styles["css_variables"][f"--{var_name}"] = var_value

    def _extract_js_styles(self, js_content: str, file_path: str, styles: Dict):
        """Extract styles from JS/TS files."""
        # Tailwind classes in className
        for match in re.finditer(
            r'className=["\']([^"\']+)["\']', js_content
        ):
            classes = match.group(1).split()
            for cls in classes:
                # Extract base utility (before modifiers like hover:, md:, etc.)
                base = cls.split(":")[-1] if ":" in cls else cls
                if base:
                    styles["tailwind_classes"][base].add(file_path)

        # Inline styles
        for match in re.finditer(r"style=\{\{([^}]+)\}\}", js_content):
            styles["inline_styles"].append({
                "file": file_path,
                "style": match.group(1),
            })

        # styled-components / emotion / css-in-JS
        for match in re.finditer(
            r"(?:styled\.\w+|css`)([^`]+)`", js_content
        ):
            styles["styled_components"].append({
                "file": file_path,
                "css": match.group(1)[:200],
            })
