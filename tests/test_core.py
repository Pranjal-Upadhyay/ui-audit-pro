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

    # --- Phase 4: richer AI-slop heuristics -------------------------------

    def _text_data(self, texts):
        return {
            "computed_styles": {"colors": [], "font_families": []},
            "dom_snapshots": {"https://x": {
                "text_elements": [{"text": t} for t in texts]}},
        }

    def test_detects_decorative_emoji_overuse(self):
        data = self._text_data(["✨ Fast", "🚀 Scale", "🔥 Ship", "💡 Smart", "🎯 Win"])
        ids = [f["id"] for f in self.checker._check_ai_design_tropes(data)]
        assert "ai-trope-emoji-decoration" in ids

    def test_few_emoji_not_flagged(self):
        data = self._text_data(["✨ Welcome", "Normal heading"])
        ids = [f["id"] for f in self.checker._check_ai_design_tropes(data)]
        assert "ai-trope-emoji-decoration" not in ids

    def test_detects_placeholder_content(self):
        data = self._text_data(["Lorem ipsum dolor sit amet", "john doe"])
        findings = self.checker._check_ai_design_tropes(data)
        ph = [f for f in findings if f["id"] == "ai-trope-placeholder-content"]
        assert ph and ph[0]["severity"] == "medium"

    def test_detects_generic_cta_overuse(self):
        data = self._text_data(["Get Started", "Learn More", "Sign Up Free"])
        ids = [f["id"] for f in self.checker._check_ai_design_tropes(data)]
        assert "ai-trope-generic-cta" in ids

    def test_two_ctas_not_flagged(self):
        data = self._text_data(["Get Started", "Learn More"])
        ids = [f["id"] for f in self.checker._check_ai_design_tropes(data)]
        assert "ai-trope-generic-cta" not in ids

    def test_wires_up_source_gradients_and_pill_badges(self):
        data = {
            "computed_styles": {"colors": [], "font_families": [], "ai_tropes": {
                "ai_gradients": ["a.tsx", "b.tsx"],
                "ai_pill_badges": ["hero.tsx"],
            }},
            "dom_snapshots": {},
        }
        ids = [f["id"] for f in self.checker._check_ai_design_tropes(data)]
        assert "ai-trope-gradient-overuse" in ids
        assert "ai-trope-pill-badges" in ids


class TestScanTextSlop:
    def setup_method(self):
        from analyzers.consistency_checker import ConsistencyChecker
        self.checker = ConsistencyChecker()

    def test_counts_cliches_and_em_dashes(self):
        r = self.checker._scan_text_slop(
            ["Supercharge your team — effortlessly — today"])
        assert "supercharge your" in r["cliches"]
        assert "effortlessly" in r["cliches"]
        assert r["em_dashes"] == 2

    def test_cta_requires_short_standalone_label(self):
        # 'get started' buried in a long sentence must NOT count as a CTA
        r = self.checker._scan_text_slop(
            ["Once you have configured everything you can get started with the API"])
        assert r["ctas"] == []

    def test_cta_matches_standalone_button_text(self):
        r = self.checker._scan_text_slop(["Get Started"])
        assert r["ctas"] == ["get started"]

    def test_empty_and_none_safe(self):
        r = self.checker._scan_text_slop(["", None, "hello"])
        assert r["em_dashes"] == 0 and r["cliches"] == []



class TestCheckRegistration:
    """Every implemented check must be reachable from the audit pipeline.

    Guards against the class of bug where a checker method is written and
    unit-tested but never added to the dispatch list, so it silently never
    runs in production.
    """

    def _implemented(self, cls):
        return {
            name[len("_check_"):]
            for name in dir(cls)
            if name.startswith("_check_")
        }

    def test_every_consistency_check_is_dispatched(self):
        from analyzers.consistency_checker import ConsistencyChecker
        from audit import UI_CHECKS

        registered = {check_id for _, check_id, _ in UI_CHECKS}
        missing = self._implemented(ConsistencyChecker) - registered
        assert not missing, f"Implemented but never dispatched: {sorted(missing)}"

    def test_every_integration_check_is_dispatched(self):
        from analyzers.integration_checker import IntegrationChecker
        from audit import INTEGRATION_CHECKS

        registered = {check_id for _, check_id, _ in INTEGRATION_CHECKS}
        missing = self._implemented(IntegrationChecker) - registered
        assert not missing, f"Implemented but never dispatched: {sorted(missing)}"

    def test_every_dispatched_check_is_implemented(self):
        from analyzers.consistency_checker import ConsistencyChecker
        from analyzers.integration_checker import IntegrationChecker
        from audit import UI_CHECKS, INTEGRATION_CHECKS

        for checks, cls in ((UI_CHECKS, ConsistencyChecker), (INTEGRATION_CHECKS, IntegrationChecker)):
            implemented = self._implemented(cls)
            for _, check_id, _ in checks:
                assert check_id in implemented, f"Dispatched but not implemented: {check_id}"

    def test_every_check_declares_a_valid_layer(self):
        from audit import UI_CHECKS, INTEGRATION_CHECKS

        for _, check_id, requires in UI_CHECKS + INTEGRATION_CHECKS:
            assert requires in ("source", "browser", "either"), (check_id, requires)


class TestCoverageHonesty:
    """Zero findings with incomplete coverage must never read as a pass."""

    def _report(self, skipped, executed, findings=()):
        from report_generator import ReportGenerator
        return ReportGenerator(
            findings=list(findings),
            discovery={},
            output_dir=Path("/tmp"),
            coverage={
                "capabilities": {"layer2_source": True, "layer1_browser": False},
                "executed": [{"name": f"e{i}", "id": f"e{i}"} for i in range(executed)],
                "skipped": [
                    {"name": f"s{i}", "id": f"s{i}", "reason": "no browser"} for i in range(skipped)
                ],
            },
        )

    def test_zero_findings_with_skips_is_unknown_not_excellent(self):
        gen = self._report(skipped=28, executed=9)
        summary = gen._executive_summary({})
        assert "UNKNOWN" in summary
        assert "EXCELLENT" not in summary

    def test_zero_findings_with_full_coverage_is_excellent(self):
        gen = self._report(skipped=0, executed=37)
        summary = gen._executive_summary({})
        assert "EXCELLENT" in summary

    def test_no_checks_executed_is_unknown(self):
        gen = self._report(skipped=0, executed=0)
        summary = gen._executive_summary({})
        assert "UNKNOWN" in summary

    def test_coverage_section_warns_about_skips(self):
        gen = self._report(skipped=28, executed=9)
        section = gen._coverage_section()
        assert "28 check(s) did not run" in section
        assert "not** a clean bill of" in section


class TestRedaction:
    def test_redacts_sensitive_keys_at_any_depth(self):
        from capture.network_interceptor import redact, REDACTED

        payload = {
            "user": {"name": "ada", "api_key": "sk-live-123"},
            "items": [{"authorization": "Bearer xyz", "id": 1}],
            "accessToken": "abc",
            "password": "hunter2",
            "safe": "keep-me",
        }
        result = redact(payload)

        assert result["user"]["api_key"] == REDACTED
        assert result["items"][0]["authorization"] == REDACTED
        assert result["accessToken"] == REDACTED
        assert result["password"] == REDACTED
        assert result["user"]["name"] == "ada"
        assert result["safe"] == "keep-me"
        assert result["items"][0]["id"] == 1

    def test_original_payload_is_not_mutated(self):
        from capture.network_interceptor import redact

        payload = {"secret": "s"}
        redact(payload)
        assert payload["secret"] == "s"


class TestInferShape:
    def test_scalar_types(self):
        from capture.network_interceptor import infer_shape

        assert infer_shape({"a": 1, "b": 1.5, "c": "x", "d": True, "e": None}) == {
            "a": "integer", "b": "number", "c": "string", "d": "boolean", "e": "null",
        }

    def test_arrays_are_capped_at_three_items(self):
        from capture.network_interceptor import infer_shape

        assert infer_shape([1, 2, 3, 4, 5]) == ["integer", "integer", "integer"]

    def test_recursion_is_capped(self):
        from capture.network_interceptor import infer_shape

        deep = {"a": {"b": {"c": {"d": {"e": 1}}}}}
        assert infer_shape(deep) == {"a": {"b": {"c": {"d": "..."}}}}


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def body(self):
        return self._body


class TestAttachBody:
    def _interceptor(self, tmp_path):
        from capture.network_interceptor import NetworkInterceptor

        return NetworkInterceptor(tmp_path)

    def test_captures_and_redacts_json_body(self, tmp_path):
        ni = self._interceptor(tmp_path)
        req = {}
        body = json.dumps({"total": "42.00", "token": "leak"}).encode()
        ni._attach_body(req, _FakeResponse(body), {"content-type": "application/json"})

        assert req["response_body"]["total"] == "42.00"
        assert req["response_body"]["token"] == "[REDACTED]"
        assert req["response_shape"] == {"total": "string", "token": "string"}

    def test_ignores_non_json_content_type(self, tmp_path):
        ni = self._interceptor(tmp_path)
        req = {}
        ni._attach_body(req, _FakeResponse(b"<html>"), {"content-type": "text/html"})
        assert "response_body" not in req

    def test_marks_oversized_body_as_truncated(self, tmp_path):
        from capture.network_interceptor import MAX_BODY_BYTES

        ni = self._interceptor(tmp_path)
        req = {}
        huge = b"x" * (MAX_BODY_BYTES + 1)
        ni._attach_body(req, _FakeResponse(huge), {"content-type": "application/json"})
        assert req["response_truncated"] is True
        assert "response_body" not in req

    def test_malformed_json_does_not_raise(self, tmp_path):
        ni = self._interceptor(tmp_path)
        req = {}
        ni._attach_body(req, _FakeResponse(b"{not json"), {"content-type": "application/json"})
        assert "response_body" not in req


class TestIntegrationChecksReadPerRequestBodies:
    """Bodies now live per-request; checks must no longer read a page-level `response`."""

    def _logs(self, body, url="http://localhost:3000/api/order"):
        return {
            "http://localhost:3000/cart": {
                "url": "http://localhost:3000/cart",
                "requests": [
                    {"url": url, "method": "POST", "status": 200, "response_body": body},
                ],
            }
        }

    def test_type_mismatch_detected_from_captured_body(self):
        from analyzers.integration_checker import IntegrationChecker

        findings = IntegrationChecker().run_check(
            "type_mismatches",
            {
                "network_logs": self._logs({"total": "42.00"}),
                "type_contracts": [{
                    "kind": "interface",
                    "name": "Order",
                    "file": "src/types/order.ts",
                    "definition": "interface Order { total: number }",
                }],
            },
        )

        ids = [f["id"] for f in findings]
        assert any("type-contract-mismatch-total" in i for i in ids)

    def test_contract_drift_detected_from_captured_body(self):
        from analyzers.integration_checker import IntegrationChecker

        findings = IntegrationChecker().run_check(
            "api_contract",
            {
                "network_logs": self._logs({"total": 1, "surpriseField": True}),
                "api_contracts": {
                    "typescript_types": [{
                        "name": "Order",
                        "file": "src/types/order.ts",
                        "definition": "interface Order { total: number }",
                    }],
                },
            },
        )

        assert any("surpriseField" in f["evidence"] for f in findings)

    def test_no_captured_bodies_yields_no_false_positives(self):
        from analyzers.integration_checker import IntegrationChecker

        logs = {"http://x/": {"url": "http://x/", "requests": [{"url": "http://x/a", "status": 200}]}}
        findings = IntegrationChecker().run_check(
            "type_mismatches",
            {"network_logs": logs, "type_contracts": []},
        )
        assert findings == []


class TestBaselineDiff:
    def _f(self, fid, sev="low", category="Cat A", title="t"):
        return {"id": fid, "severity": sev, "category": category, "title": title}

    def test_new_and_resolved_and_persistent(self):
        from baseline_diff import diff
        base = [self._f("a"), self._f("b")]
        cur = [self._f("b"), self._f("c")]
        r = diff(base, cur)
        assert [x["id"] for x in r["new"]] == ["c"]
        assert [x["id"] for x in r["resolved"]] == ["a"]
        assert r["persistent"] == ["b"]

    def test_resolved_becomes_unverified_when_check_skipped(self):
        """A baseline issue must NOT count as resolved if its check didn't re-run."""
        from baseline_diff import diff
        base = [self._f("a", category="Layout Integrity Bugs")]
        cur = []  # 'a' is gone...
        current_cov = {"skipped": [{"name": "Layout Integrity Bugs", "id": "layout_integrity"}]}
        r = diff(base, cur, current_coverage=current_cov)
        assert r["resolved"] == []
        assert [x["id"] for x in r["unverified"]] == ["a"]

    def test_resolved_when_check_did_run(self):
        from baseline_diff import diff
        base = [self._f("a", category="Layout Integrity Bugs")]
        cur = []
        current_cov = {"skipped": [{"name": "Some Other Check", "id": "other"}]}
        r = diff(base, cur, current_coverage=current_cov)
        assert [x["id"] for x in r["resolved"]] == ["a"]
        assert r["unverified"] == []

    def test_severity_regression_detected(self):
        from baseline_diff import diff
        base = [self._f("a", sev="low")]
        cur = [self._f("a", sev="high")]
        r = diff(base, cur)
        assert [x["id"] for x in r["severity_regressions"]] == ["a"]

    def test_coverage_regression_flagged(self):
        from baseline_diff import diff
        base_cov = {"skipped": []}
        cur_cov = {"skipped": [{"name": "Form Validation Consistency"}]}
        r = diff([], [], baseline_coverage=base_cov, current_coverage=cur_cov)
        assert r["coverage_regressed"] == ["Form Validation Consistency"]

    def test_gate_new_high(self):
        from baseline_diff import diff, gate
        base = []
        cur = [self._f("a", sev="high"), self._f("b", sev="low")]
        r = diff(base, cur)
        assert gate(r, "new-high") is True
        assert gate(r, "none") is False

    def test_gate_new_low_only(self):
        from baseline_diff import diff, gate
        r = diff([], [self._f("a", sev="low")])
        assert gate(r, "new-high") is False   # low doesn't trip the high gate
        assert gate(r, "new") is True         # ...but trips the 'any new' gate

    def test_gate_regressed_mode(self):
        from baseline_diff import diff, gate
        r = diff([self._f("a", sev="low")], [self._f("a", sev="high")])
        assert gate(r, "regressed") is True

    def test_gate_unknown_mode_raises(self):
        from baseline_diff import gate
        with pytest.raises(ValueError):
            gate({"new": [], "new_high": [], "severity_regressions": []}, "bogus")


class TestAxeMapping:
    """Phase 3: axe-core violation -> a11y_issue mapping (browser-free)."""

    def _sample(self):
        return [{
            "id": "color-contrast",
            "help": "Elements must meet minimum color contrast ratio thresholds",
            "description": "Ensure contrast between foreground and background",
            "helpUrl": "https://dequeuniversity.com/rules/axe/4.10/color-contrast",
            "impact": "serious",
            "tags": ["cat.color", "wcag2aa", "wcag143"],
            "nodes": [
                {"target": ["p.lead"], "impact": "serious",
                 "failureSummary": "Fix any of the following: contrast 2.1 is too low",
                 "html": "<p class='lead'>hi</p>"},
                {"target": [".footer > span"], "impact": "serious",
                 "failureSummary": "", "html": "<span>x</span>"},
            ],
        }, {
            "id": "region",
            "help": "All page content should be contained by landmarks",
            "description": "Ensures all content is contained by a landmark",
            "helpUrl": "https://dequeuniversity.com/rules/axe/4.10/region",
            "impact": "moderate",
            "tags": ["cat.keyboard", "best-practice"],
            "nodes": [{"target": ["img"], "impact": "moderate",
                       "failureSummary": "wrap in a landmark", "html": "<img src=x>"}],
        }]

    def test_flattens_one_issue_per_node(self):
        from capture.dom_extractor import DOMExtractor
        issues = DOMExtractor._map_axe_violations(self._sample(), 100)
        assert len(issues) == 3  # 2 contrast nodes + 1 region node

    def test_severity_mapping(self):
        from capture.dom_extractor import DOMExtractor
        issues = DOMExtractor._map_axe_violations(self._sample(), 100)
        by_rule = {i["type"]: i for i in issues}
        assert by_rule["color-contrast"]["severity"] == "high"   # serious -> high
        assert by_rule["region"]["severity"] == "medium"         # moderate -> medium

    def test_precise_selector_and_wcag_tags(self):
        from capture.dom_extractor import DOMExtractor
        issues = DOMExtractor._map_axe_violations(self._sample(), 100)
        contrast = [i for i in issues if i["type"] == "color-contrast"]
        assert contrast[0]["element"] == "p.lead"
        assert "wcag2aa" in contrast[0]["wcag_tags"]
        assert "best-practice" not in contrast[0]["wcag_tags"]  # non-wcag tag dropped

    def test_fix_falls_back_to_help_url_when_no_summary(self):
        from capture.dom_extractor import DOMExtractor
        issues = DOMExtractor._map_axe_violations(self._sample(), 100)
        contrast = [i for i in issues if i["type"] == "color-contrast"]
        assert contrast[1]["fix"].startswith("See https://dequeuniversity.com")

    def test_respects_max_issues_cap(self):
        from capture.dom_extractor import DOMExtractor
        issues = DOMExtractor._map_axe_violations(self._sample(), 1)
        assert len(issues) == 1

    def test_empty_violations_is_empty(self):
        from capture.dom_extractor import DOMExtractor
        assert DOMExtractor._map_axe_violations([], 100) == []


class TestAccessibilityCheckConsumesAxe:
    """Phase 3: _check_accessibility honours axe-supplied severity + help_url."""

    def _data(self, issue):
        return {"dom_snapshots": {"http://x/products": {
            "a11y_engine": "axe-core", "a11y_issues": [issue]}}}

    def test_uses_axe_severity_and_stable_id(self):
        from analyzers.consistency_checker import ConsistencyChecker
        c = ConsistencyChecker()
        issue = {"type": "color-contrast", "element": "p.lead", "severity": "high",
                 "title": "Contrast too low", "description": "d", "evidence": "<p>",
                 "help_url": "https://deque/color-contrast", "fix": "raise contrast"}
        findings = c._check_accessibility(self._data(issue))
        assert len(findings) == 1
        f = findings[0]
        assert f["severity"] == "high"
        assert f["id"].startswith("a11y-color-contrast-")
        assert "color-contrast" in f["evidence"] and "deque" in f["evidence"]

    def test_two_issues_same_rule_get_unique_ids(self):
        from analyzers.consistency_checker import ConsistencyChecker
        c = ConsistencyChecker()
        data = {"dom_snapshots": {"http://x/p": {"a11y_engine": "axe-core", "a11y_issues": [
            {"type": "color-contrast", "element": "p.a", "severity": "high", "title": "t"},
            {"type": "color-contrast", "element": "p.b", "severity": "high", "title": "t"},
        ]}}}
        findings = c._check_accessibility(data)
        assert len({f["id"] for f in findings}) == 2

    def test_legacy_heuristic_impact_still_maps(self):
        from analyzers.consistency_checker import ConsistencyChecker
        c = ConsistencyChecker()
        issue = {"type": "missing-alt", "element": "img", "impact": "critical",
                 "title": "Image missing alt text", "fix": "add alt"}
        findings = c._check_accessibility(self._data(issue))
        assert findings[0]["severity"] == "high"  # impact critical -> high


class TestReportDiffSection:
    """Phase-2 follow-up: report _diff_section now uses the coverage-aware,
    non-swallowing baseline_diff engine."""

    def _gen(self, tmp_path, current_findings, current_coverage,
             baseline_findings, baseline_coverage):
        from report_generator import ReportGenerator
        prev_dir = tmp_path / "prev"
        prev_dir.mkdir()
        (prev_dir / "findings.json").write_text(json.dumps(baseline_findings))
        if baseline_coverage is not None:
            (prev_dir / "coverage.json").write_text(json.dumps(baseline_coverage))
        prev_report = prev_dir / "audit-report.md"
        prev_report.write_text("# old report")
        out = tmp_path / "cur"
        out.mkdir()
        return ReportGenerator(
            findings=current_findings, discovery={}, output_dir=out,
            previous_report=str(prev_report), coverage=current_coverage,
        )

    def _f(self, fid, sev="low", category="Cat A", title="t"):
        return {"id": fid, "severity": sev, "category": category, "title": title}

    def test_new_high_issue_rendered(self, tmp_path):
        gen = self._gen(
            tmp_path,
            current_findings=[self._f("a"), self._f("b", sev="high")],
            current_coverage={"executed": [], "skipped": []},
            baseline_findings=[self._f("a")],
            baseline_coverage={"executed": [], "skipped": []},
        )
        out = gen._diff_section()
        assert "New Issues" in out
        assert "`b`" in out and "HIGH" in out

    def test_skipped_check_makes_gone_finding_unverified_not_resolved(self, tmp_path):
        gen = self._gen(
            tmp_path,
            current_findings=[],  # 'a' is gone...
            current_coverage={"skipped": [{"name": "Layout Integrity Bugs"}]},
            baseline_findings=[self._f("a", category="Layout Integrity Bugs")],
            baseline_coverage={"skipped": []},
        )
        out = gen._diff_section()
        assert "Unverified" in out
        assert "Coverage Regressed" in out
        # must NOT be reported as resolved
        assert "### Resolved Issues\n- None" in out

    def test_missing_previous_findings_reports_visibly(self, tmp_path):
        from report_generator import ReportGenerator
        prev_dir = tmp_path / "prev"; prev_dir.mkdir()
        prev_report = prev_dir / "audit-report.md"; prev_report.write_text("# old")
        out = tmp_path / "cur"; out.mkdir()
        gen = ReportGenerator(findings=[], discovery={}, output_dir=out,
                              previous_report=str(prev_report), coverage={})
        section = gen._diff_section()
        assert section != ""  # not silently swallowed
        assert "Could not diff" in section
