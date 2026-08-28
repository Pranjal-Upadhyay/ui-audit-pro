"""
Unit tests for ui-audit-pro core logic.

Run from the project root:
    cd skills/ui-audit-pro
    pip install -e .
    pytest tests/ -v
"""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class TestParseInlineStyleString:
    def setup_method(self):
        from analyzers.consistency_checker import ConsistencyChecker
        self.checker = ConsistencyChecker()

    def test_quoted_string_values(self):
        raw = "backgroundColor: \'#0070f3\', color: \'white\', borderRadius: \'6px\'"
        result = self.checker._parse_inline_style_string(raw)
        assert result["backgroundColor"] == "#0070f3"
        assert result["color"] == "white"
        assert result["borderRadius"] == "6px"

    def test_bare_numeric_value(self):
        raw = "padding: 24"
        result = self.checker._parse_inline_style_string(raw)
        assert result["padding"] == 24.0

    def test_empty_string(self):
        assert self.checker._parse_inline_style_string("") == {}


class TestSpacingRhythmInlineMode:
    def setup_method(self):
        from analyzers.consistency_checker import ConsistencyChecker
        self.checker = ConsistencyChecker()

    def _data(self, inline_styles):
        return {"computed_styles": {"css_files": {}, "inline_styles": inline_styles}}

    def test_off_grid_padding_string_triggers_finding(self):
        """Core bug fix: padding: 13px 17px must produce a finding."""
        data = self._data([
            {"file": "src/app/page.tsx", "style": "padding: \'13px 17px\', fontSize: \'16px\'"}
        ])
        findings = self.checker._check_spacing_rhythm(data)
        assert len(findings) == 1, f"Expected 1 finding, got {len(findings)}: {findings}"
        assert findings[0]["id"] == "spacing-off-grid"

    def test_on_grid_padding_no_finding(self):
        data = self._data([
            {"file": "src/app/page.tsx", "style": "padding: \'16px 24px\'"}
        ])
        findings = self.checker._check_spacing_rhythm(data)
        assert findings == []

    def test_bare_numeric_on_grid_no_finding(self):
        data = self._data([{"file": "src/app/layout.tsx", "style": "padding: 24"}])
        findings = self.checker._check_spacing_rhythm(data)
        assert findings == []


class TestSpacingRhythmCSSMode:
    def setup_method(self):
        from analyzers.consistency_checker import ConsistencyChecker
        self.checker = ConsistencyChecker()

    def _data(self, css_content):
        return {"computed_styles": {"css_files": {"styles.css": css_content}, "inline_styles": []}}

    def test_on_grid_values_no_findings(self):
        findings = self.checker._check_spacing_rhythm(self._data("padding: 16px; margin: 8px;"))
        assert findings == []

    def test_off_grid_value_raises_finding(self):
        findings = self.checker._check_spacing_rhythm(self._data("padding: 13px;"))
        assert len(findings) == 1
        assert findings[0]["id"] == "spacing-off-grid"


class TestTypographyScaleInlineMode:
    def setup_method(self):
        from analyzers.consistency_checker import ConsistencyChecker
        self.checker = ConsistencyChecker()

    def test_standard_font_size_no_finding(self):
        data = {"computed_styles": {"css_files": {}, "inline_styles": [
            {"file": "src/app/page.tsx", "style": "fontSize: \'16px\'"}
        ]}}
        assert self.checker._check_typography_scale(data) == []

    def test_three_nonstandard_sizes_triggers_finding(self):
        data = {"computed_styles": {"css_files": {}, "inline_styles": [
            {"file": "a.tsx", "style": "fontSize: \'13px\'"},
            {"file": "b.tsx", "style": "fontSize: \'15px\'"},
            {"file": "c.tsx", "style": "fontSize: \'17px\'"},
        ]}}
        findings = self.checker._check_typography_scale(data)
        assert len(findings) == 1
        assert findings[0]["id"] == "typography-one-offs"


class TestVisualIdentityInlineMode:
    def setup_method(self):
        from analyzers.consistency_checker import ConsistencyChecker
        self.checker = ConsistencyChecker()

    def test_identical_styles_no_finding(self):
        style = "backgroundColor: \'#0070f3\', borderRadius: \'6px\', padding: \'16px 24px\', fontSize: \'16px\', fontWeight: 600, color: \'white\'"
        data = {"computed_styles": {"inline_styles": [
            {"file": "src/app/page.tsx", "style": style},
            {"file": "src/app/products/page.tsx", "style": style},
        ]}, "dom_snapshots": {}}
        assert self.checker._check_visual_identity(data) == []

    def test_different_border_radius_triggers_finding(self):
        style_home = "backgroundColor: \'#0070f3\', borderRadius: \'6px\', padding: \'13px 17px\', fontSize: \'16px\', fontWeight: 600, color: \'white\'"
        style_products = "backgroundColor: \'#0070f3\', borderRadius: \'8px\', padding: \'16px 24px\', fontSize: \'16px\', fontWeight: 700, color: \'white\'"
        data = {"computed_styles": {"inline_styles": [
            {"file": "src/app/page.tsx", "style": style_home},
            {"file": "src/app/products/page.tsx", "style": style_products},
        ]}, "dom_snapshots": {}}
        findings = self.checker._check_visual_identity(data)
        assert len(findings) >= 1
        assert findings[0]["category"] == "Visual Identity Consistency"


class TestStackDetector:
    def setup_method(self):
        from detect_stack import StackDetector
        self.cls = StackDetector

    def test_detects_nextjs_from_package_json(self, tmp_path):
        pkg = {"dependencies": {"next": "14.2.0", "react": "^18"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        (tmp_path / "src" / "app").mkdir(parents=True)
        (tmp_path / "src" / "app" / "page.tsx").write_text("export default function Home() { return null }")
        stack = self.cls(str(tmp_path)).detect()
        assert stack.frontend_framework == "nextjs"

    def test_unknown_stack_returns_list_adapters(self, tmp_path):
        (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"unknown-lib": "1.0"}}))
        stack = self.cls(str(tmp_path)).detect()
        assert isinstance(stack.adapter_names, list)


class TestNextJSAdapterListRoutes:
    TEST_APP = Path(__file__).parent.parent.parent.parent / "test-app"

    def setup_method(self):
        from adapters.nextjs import NextJSAdapter
        self.adapter_cls = NextJSAdapter

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent.parent.parent / "test-app").exists(),
        reason="test-app not found",
    )
    def test_finds_at_least_three_routes(self):
        adapter = self.adapter_cls(str(self.TEST_APP))
        routes = adapter.list_routes()
        assert len(routes) >= 3, f"Got {len(routes)}: {[r.path for r in routes]}"

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent.parent.parent / "test-app").exists(),
        reason="test-app not found",
    )
    def test_route_paths_are_strings(self):
        adapter = self.adapter_cls(str(self.TEST_APP))
        for r in adapter.list_routes():
            assert isinstance(r.path, str)


class TestRouteDeduplication:
    @staticmethod
    def _dedup(routes):
        seen_paths = set()
        unique = []
        for r in routes:
            path_key = r.get("path", "").rstrip("/") or "/"
            if path_key not in seen_paths:
                seen_paths.add(path_key)
                unique.append(r)
        return unique

    def test_same_path_different_framework_deduped(self):
        routes = [
            {"path": "/products", "framework": "nextjs"},
            {"path": "/products", "framework": "browser-crawl"},
        ]
        assert len(self._dedup(routes)) == 1

    def test_different_paths_kept(self):
        routes = [
            {"path": "/", "framework": "nextjs"},
            {"path": "/products", "framework": "nextjs"},
            {"path": "/cart", "framework": "nextjs"},
        ]
        assert len(self._dedup(routes)) == 3

    def test_trailing_slash_deduped(self):
        routes = [
            {"path": "/products/", "framework": "nextjs"},
            {"path": "/products", "framework": "browser-crawl"},
        ]
        assert len(self._dedup(routes)) == 1


class TestAIDesignTropes:
    def setup_method(self):
        from analyzers.consistency_checker import ConsistencyChecker
        self.checker = ConsistencyChecker()

    def test_detects_uncustomized_indigo_slate_palette(self):
        data = {
            "computed_styles": {
                "colors": ["#6366f1", "#0f172a"],
                "font_families": ["Inter, sans-serif"],
            },
            "dom_snapshots": {},
        }
        findings = self.checker._check_ai_design_tropes(data)
        finding_ids = [f["id"] for f in findings]
        assert "ai-trope-default-palette" in finding_ids

    def test_detects_font_monoculture(self):
        data = {
            "computed_styles": {
                "colors": ["#333333"],
                "font_families": ["Inter, sans-serif"],
            },
            "dom_snapshots": {},
        }
        findings = self.checker._check_ai_design_tropes(data)
        finding_ids = [f["id"] for f in findings]
        assert "ai-trope-font-monoculture" in finding_ids

    def test_detects_ai_microcopy_cliches(self):
        data = {
            "computed_styles": {"colors": [], "font_families": []},
            "dom_snapshots": {
                "https://example.com": {
                    "text_elements": [
                        {"text": "Supercharge your workflow with our seamless integration!"}
                    ]
                }
            },
        }
        findings = self.checker._check_ai_design_tropes(data)
        finding_ids = [f["id"] for f in findings]
        assert "ai-trope-microcopy-cliches" in finding_ids

    def test_clean_custom_design_no_ai_trope_findings(self):
        data = {
            "computed_styles": {
                "colors": ["#111111", "#ff5500", "#ffffff"],
                "font_families": ["CustomBrandSerif", "Satoshi, sans-serif"],
            },
            "dom_snapshots": {
                "https://example.com": {
                    "text_elements": [
                        {"text": "Build better products faster."}
                    ]
                }
            },
        }
        findings = self.checker._check_ai_design_tropes(data)
        assert len(findings) == 0

