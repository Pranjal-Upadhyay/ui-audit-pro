#!/usr/bin/env python3
"""
UI Audit Pro — Main Audit Engine

Two-layer architecture:
  Layer 1: Runtime/browser-level checks (framework-agnostic)
  Layer 2: Source-code-level checks (framework-aware, pluggable adapters)

Usage:
  python3 audit.py detect  --codebase <path>
  python3 audit.py full    --codebase <path> [--url <url>] --output <dir>
  python3 audit.py discover --codebase <path> [--url <url>] --output <dir>
  python3 audit.py capture  --codebase <path> [--url <url>] --output <dir>
  python3 audit.py audit    --codebase <path> [--url <url>] --output <dir>
  python3 audit.py report   --findings <json> --output <dir> [--previous-report <md>]
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from detect_stack import StackDetector, StackInfo
from analyzers.style_analyzer import StyleAnalyzer
from analyzers.consistency_checker import ConsistencyChecker
from analyzers.integration_checker import IntegrationChecker
from capture import ensure_playwright, BrowserUnavailableError
from capture.screenshot_capture import ScreenshotCapture
from capture.network_interceptor import NetworkInterceptor
from capture.dom_extractor import DOMExtractor
from report_generator import ReportGenerator
from baseline_diff import FAIL_MODES


# Each check declares the data layer it needs so the report can distinguish
# "ran and found nothing" from "never ran".
#   source  -> needs codebase-derived styles/types (Layer 2)
#   browser -> needs live DOM/network capture (Layer 1)
#   either  -> has both a source-level and a browser-level code path
UI_CHECKS = [
    ("Visual Identity Consistency", "visual_identity", "either"),
    ("Spacing Rhythm", "spacing_rhythm", "source"),
    ("Typography Scale", "typography_scale", "source"),
    ("Icon Set Consistency", "icon_consistency", "browser"),
    ("Interaction State Consistency", "interaction_states", "browser"),
    ("Modal/Popup/Overlay Behavior", "modal_behavior", "browser"),
    ("Loading/Empty/Error State Consistency", "state_consistency", "browser"),
    ("Form Validation Consistency", "form_validation", "browser"),
    ("Content/Microcopy Consistency", "content_consistency", "browser"),
    ("Structural/Navigational Consistency", "navigation_consistency", "browser"),
    ("Responsive/Cross-Breakpoint Consistency", "responsive_consistency", "browser"),
    ("Accessibility as Consistency Signal", "accessibility", "browser"),
    ("Motion/Animation Consistency", "animation_consistency", "source"),
    ("Layout Integrity Bugs", "layout_integrity", "browser"),
    ("Data Density/Truncation Consistency", "truncation_consistency", "browser"),
    ("Iconography/Color Semantics", "icon_color_semantics", "browser"),
    ("Empty/Zero/Singular-Plural Correctness", "grammar_correctness", "browser"),
    ("Pagination/Infinite-Scroll Consistency", "pagination_consistency", "browser"),
    ("Notification/Toast Consistency", "notification_consistency", "browser"),
    ("Permission/Role-Based UI Consistency", "permission_consistency", "browser"),
    ("Theming Consistency (Dark Mode)", "theming_consistency", "source"),
    ("Input Affordance Consistency", "input_consistency", "browser"),
    ("Print/Export/PDF View Consistency", "print_consistency", "source"),
    ("AI Design Tropes & Brand Originality", "ai_design_tropes", "either"),
]

INTEGRATION_CHECKS = [
    ("API Contract/Schema Drift", "api_contract", "browser"),
    ("Type Mismatches", "type_mismatches", "either"),
    ("Loading/Error/Empty State Wiring", "state_wiring", "browser"),
    ("Unhandled Promise Rejections", "unhandled_errors", "source"),
    ("Race Conditions/Stale Data", "race_conditions", "browser"),
    ("Optimistic UI Correctness", "optimistic_ui", "browser"),
    ("Auth/Session Boundary Handling", "auth_handling", "browser"),
    ("Latency/Timeout Behavior", "latency_timeout", "browser"),
    ("Pagination/Data Consistency", "pagination_data", "browser"),
    ("Real-time/Websocket Sync", "websocket_sync", "browser"),
    ("File Upload/Download Edge Cases", "file_transfer", "browser"),
    ("Idempotency/Double-Submit", "double_submit", "browser"),
    ("Localization/Timezone Mismatches", "timezone_issues", "browser"),
]


def load_adapter(codebase_path: str, adapter_name: str):
    """Dynamically load an adapter by name."""
    from adapters.base import BaseAdapter

    adapter_map = {
        "nextjs": ("adapters.nextjs", "NextJSAdapter"),
        "react": ("adapters.react", "ReactAdapter"),
        "vue": ("adapters.vue", "VueAdapter"),
        "static-html": ("adapters.static_html", "StaticHTMLAdapter"),
        "node-express": ("adapters.node_express", "NodeExpressAdapter"),
    }

    if adapter_name not in adapter_map:
        return None

    module_path, class_name = adapter_map[adapter_name]
    try:
        import importlib
        module = importlib.import_module(module_path)
        adapter_class = getattr(module, class_name)
        return adapter_class(codebase_path)
    except (ImportError, AttributeError) as e:
        print(f"  Warning: Could not load adapter '{adapter_name}': {e}")
        return None


class UIAuditEngine:
    """Main audit engine with two-layer architecture."""

    def __init__(self, codebase_path: str, output_dir: str, live_url: str = None):
        self.codebase = Path(codebase_path) if codebase_path else None
        self.output = Path(output_dir)
        self.live_url = live_url
        self.output.mkdir(parents=True, exist_ok=True)

        # Stack detection
        self.stack: StackInfo = None
        self.adapters = []

        # Layer 1: Browser-level tools (framework-agnostic)
        self.screenshot_capture = ScreenshotCapture(self.output / "screenshots")
        self.network_interceptor = NetworkInterceptor(self.output / "network")
        self.dom_extractor = DOMExtractor(self.output / "dom")

        # Layer 2: Source-level style analysis (when codebase available)
        self.style_analyzer = StyleAnalyzer(self.codebase) if self.codebase else None

        # Checkers
        self.consistency_checker = ConsistencyChecker()
        self.integration_checker = IntegrationChecker()

        # State
        self.discovered_routes = []
        self.captured_data = {}
        self.findings = []

        # What the audit was actually able to observe. Drives the coverage
        # section of the report so zero findings is never mistaken for a pass.
        self.capabilities = {
            "layer2_source": False,
            "layer1_browser": False,
            "network_bodies": False,
            "multi_viewport": False,
        }
        self.coverage = {"executed": [], "skipped": []}

    def detect_stack(self) -> StackInfo:
        """Auto-detect the technology stack."""
        print("[0/4] Detecting technology stack...")

        if not self.codebase:
            self.stack = StackInfo(frontend_framework="unknown", backend_framework="unknown")
            print("  No codebase provided; browser-level checks only")
            return self.stack

        detector = StackDetector(str(self.codebase))
        self.stack = detector.detect()
        self.capabilities["layer2_source"] = True

        print(f"  Frontend: {self.stack.frontend_framework}")
        print(f"  Backend: {self.stack.backend_framework}")
        print(f"  Language: {self.stack.language}")
        print(f"  TypeScript: {self.stack.has_typescript}")
        print(f"  Adapters: {self.stack.adapter_names}")

        if self.stack.warnings:
            for w in self.stack.warnings:
                print(f"  Warning: {w}")

        # Load adapters
        for adapter_name in self.stack.adapter_names:
            adapter = load_adapter(str(self.codebase), adapter_name)
            if adapter:
                self.adapters.append(adapter)
                print(f"  Loaded adapter: {adapter_name}")

        # Save stack info
        stack_path = self.output / "stack.json"
        with open(stack_path, "w") as f:
            json.dump({
                "frontend": self.stack.frontend_framework,
                "backend": self.stack.backend_framework,
                "language": self.stack.language,
                "typescript": self.stack.has_typescript,
                "adapters": self.stack.adapter_names,
                "warnings": self.stack.warnings,
            }, f, indent=2)

        return self.stack

    def discover(self) -> dict:
        """Phase 1: Discover routes/screens/components (Layer 2: source-level)."""
        print("[1/4] Discovering routes and components...")

        result = {
            "routes": [],
            "api_calls": [],
            "components": [],
            "type_contracts": [],
            "design_tokens": None,
            "stack": None,
            "timestamp": datetime.now().isoformat(),
        }

        # Layer 2: Source-level discovery via adapters (if source code available)
        if self.adapters:
            print(f"  Running {len(self.adapters)} adapter(s) for source-level discovery...")
            for adapter in self.adapters:
                adapter_result = adapter.analyze()
                result["routes"].extend([
                    {"path": r.path, "file": r.file, "framework": r.framework}
                    for r in adapter_result.routes
                ])
                result["api_calls"].extend([
                    {"endpoint": c.endpoint, "method": c.method, "file": c.file, "line": c.line, "framework": c.framework}
                    for c in adapter_result.api_calls
                ])
                result["components"].extend([
                    {"name": c.name, "file": c.file, "framework": c.framework}
                    for c in adapter_result.components
                ])
                result["type_contracts"].extend([
                    {"name": t.name, "file": t.file, "kind": t.kind, "fields": t.fields, "definition": t.definition}
                    for t in adapter_result.type_contracts
                ])
                if adapter_result.warnings:
                    for w in adapter_result.warnings:
                        print(f"    Adapter warning: {w}")

        # Layer 1: Browser-level discovery (if live URL available)
        if self.live_url:
            print(f"  Crawling live instance: {self.live_url}")
            live_routes = self.screenshot_capture.crawl_routes(self.live_url)
            existing_paths = {r.get("path", "").rstrip("/") for r in result["routes"]}
            for route in live_routes:
                url = route if isinstance(route, str) else route.get("url", "")
                if not url:
                    continue
                # Normalize: strip the live_url prefix to get the path for comparison
                path = url
                if self.live_url and url.startswith(self.live_url):
                    path = url[len(self.live_url):] or "/"
                if path.rstrip("/") not in existing_paths:
                    result["routes"].append({"path": url, "file": None, "framework": "browser-crawl"})
                    existing_paths.add(path.rstrip("/"))

        # Deduplicate routes by normalised path (ignore which adapter/crawler found it)
        seen_paths = set()
        unique_routes = []
        for r in result["routes"]:
            path_key = r.get("path", "").rstrip("/") or "/"
            if path_key not in seen_paths:
                seen_paths.add(path_key)
                unique_routes.append(r)
        result["routes"] = unique_routes

        if self.stack:
            result["stack"] = {
                "frontend": self.stack.frontend_framework,
                "backend": self.stack.backend_framework,
                "language": self.stack.language,
            }

        # Save discovery
        discovery_path = self.output / "discovery.json"
        with open(discovery_path, "w") as f:
            json.dump(result, f, indent=2, default=str)

        self.discovered_routes = result["routes"]
        print(f"  Found {len(result['routes'])} routes, {len(result['api_calls'])} API calls, {len(result['components'])} components")
        print(f"  Discovery saved to {discovery_path}")
        return result

    def capture(self) -> dict:
        """Phase 2: Capture screenshots, DOM, and network data (Layer 1: browser-level)."""
        print("[2/4] Capturing browser-level data...")

        # Load discovery if available
        discovery_path = self.output / "discovery.json"
        if discovery_path.exists():
            with open(discovery_path) as f:
                discovery = json.load(f)
        else:
            discovery = self.discover()

        result = {
            "screenshots": {},
            "dom_snapshots": {},
            "network_logs": {},
            "computed_styles": {},
            "timestamp": datetime.now().isoformat(),
        }

        # Layer 2: Source-level CSS analysis (when codebase available)
        if self.codebase and self.style_analyzer:
            print(f"  Analyzing CSS from codebase: {self.codebase}")
            styles = self.style_analyzer.extract_all_styles()
            if isinstance(result.get("computed_styles"), dict):
                result["computed_styles"].update(styles)
            else:
                result["computed_styles"] = styles

        # Layer 1: Browser-level capture (when live URL available)
        if self.live_url:
            # Fail loudly rather than silently producing empty snapshots.
            ensure_playwright()

            print(f"  Capturing from live instance: {self.live_url}")
            failures = []

            for route in discovery.get("routes", []):
                url = route.get("path", "") if isinstance(route, dict) else str(route)
                if not url.startswith("http"):
                    url = f"{self.live_url.rstrip('/')}/{url.lstrip('/')}"

                print(f"  Capturing: {url}")

                screenshot_path = self.screenshot_capture.capture(url)
                if screenshot_path:
                    result["screenshots"][url] = str(screenshot_path)

                dom_snapshot = self._extract_multi_viewport(url)
                if dom_snapshot:
                    result["dom_snapshots"][url] = dom_snapshot
                else:
                    failures.append(url)

                network_log = self.network_interceptor.get_logs(url)
                if network_log:
                    result["network_logs"][url] = network_log

            # Active probing of discovered safe endpoints (Phase 1.2). Reaches
            # endpoints not called on page load and repeats to expose flakiness.
            api_calls = discovery.get("api_calls", [])
            if api_calls:
                print(f"  Probing {len(api_calls)} discovered API endpoint(s)...")
                probes = self.network_interceptor.probe_endpoints(self.live_url, api_calls)
                for key, log in probes.items():
                    result["network_logs"][key] = log
                if probes:
                    print(f"  Probed {len(probes)} endpoint(s) x{self.network_interceptor.PROBE_COUNT}")

            self.capabilities["layer1_browser"] = bool(result["dom_snapshots"])

            if failures:
                print(f"  ERROR: {len(failures)} route(s) could not be captured: {failures}")
            if not result["dom_snapshots"]:
                print(
                    "  ERROR: Browser capture produced no DOM snapshots. "
                    "Layer 1 checks will be reported as SKIPPED, not as passing."
                )
        else:
            print("  No live URL provided; skipping browser-level capture (Layer 1)")

        # Save capture results
        capture_path = self.output / "capture.json"
        with open(capture_path, "w") as f:
            json.dump(result, f, indent=2, default=str)

        self.captured_data = result
        print(f"  Capture saved to {capture_path}")
        return result

    # Desktop first: it is the canonical snapshot fed to cross-page consistency
    # checks. The narrower viewports contribute only breakpoint-specific deltas,
    # so the same page isn't triple-counted as three "different" screens.
    VIEWPORTS = [
        {"width": 1440, "height": 900, "label": "desktop"},
        {"width": 768, "height": 1024, "label": "tablet"},
        {"width": 375, "height": 812, "label": "mobile"},
    ]

    @staticmethod
    def _issue_signature(issue: dict) -> tuple:
        return (issue.get("type"), issue.get("element"))

    def _extract_multi_viewport(self, url: str):
        """Capture a route at several viewports.

        Returns the desktop snapshot enriched with `breakpoint_issues`: layout
        problems that appear at a narrower viewport but NOT at desktop. Those are
        genuine responsive regressions (e.g. horizontal overflow only at 375px),
        which is exactly what the responsive/cross-breakpoint check consumes.
        """
        primary = None
        desktop_sigs = set()
        breakpoint_issues = []
        captured = 0

        for vp in self.VIEWPORTS:
            snapshot = self.dom_extractor.extract(url, viewport=vp)
            if not snapshot:
                continue
            captured += 1
            issues = snapshot.get("layout_issues", [])
            if primary is None:
                primary = snapshot
                desktop_sigs = {self._issue_signature(i) for i in issues}
                continue
            for issue in issues:
                if self._issue_signature(issue) in desktop_sigs:
                    continue  # also broken on desktop → not a breakpoint regression
                tagged = dict(issue)
                tagged["viewport"] = vp["label"]
                tagged["description"] = f"[{vp['label']} @ {vp['width']}px] {issue.get('description', '')}"
                breakpoint_issues.append(tagged)

        if primary is not None:
            primary["breakpoint_issues"] = breakpoint_issues
            if captured > 1:
                self.capabilities["multi_viewport"] = True
        return primary

    def audit(self) -> list:
        """Phase 3: Run all consistency and integration checks."""
        print("[3/4] Running audit checks...")

        # Load data from previous phases
        discovery_path = self.output / "discovery.json"
        capture_path = self.output / "capture.json"

        discovery = {}
        if discovery_path.exists():
            with open(discovery_path) as f:
                discovery = json.load(f)

        capture_data = {}
        if capture_path.exists():
            with open(capture_path) as f:
                capture_data = json.load(f)

        # Merge discovery data into capture_data for checkers
        type_contracts = discovery.get("type_contracts", [])
        capture_data["type_contracts"] = type_contracts
        capture_data["api_calls"] = discovery.get("api_calls", [])
        capture_data["components"] = discovery.get("components", [])

        # The API-contract check reads `api_contracts.typescript_types`; adapters
        # emit these as `type_contracts`. Bridge them so the check doesn't report
        # "no contract found" when TypeScript interfaces plainly exist.
        capture_data.setdefault("api_contracts", {})
        capture_data["api_contracts"].setdefault(
            "typescript_types",
            [
                {"name": t.get("name"), "file": t.get("file"), "definition": t.get("definition", "")}
                for t in type_contracts
                if t.get("kind") in ("interface", "type")
            ],
        )

        # Recompute capabilities from the data actually on disk, so that
        # `audit` works as a standalone command after a prior capture run.
        self.capabilities["layer1_browser"] = bool(capture_data.get("dom_snapshots"))
        self.capabilities["layer2_source"] = bool(
            capture_data.get("computed_styles") or discovery.get("components")
        )

        findings = []
        self.coverage = {"executed": [], "skipped": []}

        def run_checks(checks, runner, label):
            print(f"  [{label}] Running {len(checks)} checks...")
            for check_name, check_id, requires in checks:
                if not self._can_run(requires):
                    reason = (
                        "no live URL / browser capture (Layer 1 unavailable)"
                        if requires == "browser"
                        else "no codebase provided (Layer 2 unavailable)"
                        if requires == "source"
                        else "neither source nor browser data available"
                    )
                    self.coverage["skipped"].append(
                        {"name": check_name, "id": check_id, "requires": requires, "reason": reason}
                    )
                    print(f"    SKIPPED: {check_name} — {reason}")
                    continue

                print(f"    Checking: {check_name}")
                self.coverage["executed"].append(
                    {"name": check_name, "id": check_id, "requires": requires}
                )
                try:
                    findings.extend(runner(check_id))
                except Exception as e:
                    print(f"    ERROR: {check_name} check failed: {e}")

        run_checks(
            UI_CHECKS,
            lambda cid: self.consistency_checker.run_check(cid, capture_data),
            "Layer 1+2",
        )
        run_checks(
            INTEGRATION_CHECKS,
            lambda cid: self.integration_checker.run_check(cid, capture_data, codebase=self.codebase),
            "Integration",
        )
        # Annotate findings with source locations if adapters provided them
        self._annotate_findings_with_source_locations(findings, discovery)

        # Save findings
        findings_path = self.output / "findings.json"
        with open(findings_path, "w") as f:
            json.dump(findings, f, indent=2, default=str)

        # Persist coverage alongside findings so the report can be regenerated
        # standalone without losing the executed/skipped distinction.
        with open(self.output / "coverage.json", "w") as f:
            json.dump(
                {"capabilities": self.capabilities, **self.coverage}, f, indent=2, default=str
            )

        self.findings = findings
        executed = len(self.coverage["executed"])
        skipped = len(self.coverage["skipped"])
        print(f"  Found {len(findings)} issues across {executed} executed checks")
        if skipped:
            print(f"  {skipped} check(s) SKIPPED for lack of input data — see coverage.json")
        print(f"  Findings saved to {findings_path}")
        return findings

    def _can_run(self, requires: str) -> bool:
        """Whether the data a check depends on was actually captured."""
        if requires == "browser":
            return self.capabilities["layer1_browser"]
        if requires == "source":
            return self.capabilities["layer2_source"]
        return self.capabilities["layer1_browser"] or self.capabilities["layer2_source"]

    def _annotate_findings_with_source_locations(self, findings: list, discovery: dict):
        """Enrich findings with file/line info from adapters when available."""
        api_calls = discovery.get("api_calls", [])
        components = discovery.get("components", [])

        # Build lookup maps
        endpoint_to_file = {}
        for call in api_calls:
            endpoint = call.get("endpoint", "")
            if endpoint:
                endpoint_to_file[endpoint] = {
                    "file": call.get("file"),
                    "line": call.get("line"),
                    "framework": call.get("framework"),
                }

        for finding in findings:
            location = finding.get("location", {})
            if isinstance(location, dict):
                endpoint = location.get("endpoint", "")
                if endpoint and endpoint in endpoint_to_file:
                    source = endpoint_to_file[endpoint]
                    location["file"] = source["file"]
                    location["line"] = source["line"]
                    location["source_framework"] = source["framework"]

    def generate_report(self, previous_report: str = None) -> str:
        """Phase 4: Generate structured audit report."""
        print("[4/4] Generating audit report...")

        if not self.findings:
            findings_path = self.output / "findings.json"
            if findings_path.exists():
                with open(findings_path) as f:
                    self.findings = json.load(f)
            else:
                self.findings = self.audit()

        discovery_path = self.output / "discovery.json"
        discovery = {}
        if discovery_path.exists():
            with open(discovery_path) as f:
                discovery = json.load(f)

        coverage_path = self.output / "coverage.json"
        if coverage_path.exists():
            with open(coverage_path) as f:
                coverage = json.load(f)
        else:
            coverage = {"capabilities": self.capabilities, **self.coverage}

        generator = ReportGenerator(
            findings=self.findings,
            discovery=discovery,
            output_dir=self.output,
            previous_report=previous_report,
            coverage=coverage,
        )

        report_path = generator.generate()
        print(f"  Report generated: {report_path}")
        return report_path

    def full_audit(self, previous_report: str = None) -> str:
        """Run the complete audit pipeline."""
        print("=" * 60)
        print("UI Audit Pro — Full Audit")
        print("=" * 60)

        self.detect_stack()
        self.discover()
        self.capture()
        self.audit()
        report_path = self.generate_report(previous_report)

        print("=" * 60)
        print(f"Audit complete! Report: {report_path}")
        print("=" * 60)

        return report_path

    def compare_baseline(self, baseline: str, fail_on: str = "new-high") -> int:
        """Compare the current run against a saved baseline. Returns an exit code.

        This is the CI-gate entry point: exit 0 = gate passed, exit 1 = gate
        tripped (a regression per --fail-on). The comparison is coverage-aware,
        so a baseline issue whose check was skipped this run is reported as
        UNVERIFIED rather than silently counted as resolved.
        """
        from baseline_diff import (
            load_findings, load_coverage, diff, gate, format_summary,
        )

        current = self.findings
        if not current:
            findings_path = self.output / "findings.json"
            if findings_path.exists():
                with open(findings_path) as f:
                    current = json.load(f)

        current_cov = None
        cov_path = self.output / "coverage.json"
        if cov_path.exists():
            with open(cov_path) as f:
                current_cov = json.load(f)

        baseline_findings = load_findings(Path(baseline))
        baseline_cov = load_coverage(Path(baseline))

        result = diff(baseline_findings, current, baseline_cov, current_cov)

        print("=" * 60)
        print(f"Baseline comparison (fail-on: {fail_on})")
        print("=" * 60)
        print(format_summary(result))

        failed = gate(result, fail_on)
        print("=" * 60)
        if failed:
            print("GATE FAILED — see new/regressed issues above.")
        else:
            print("GATE PASSED.")
        print("=" * 60)
        return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(
        description="UI Audit Pro — Two-Layer Consistency & Integration Audit Engine"
    )
    subparsers = parser.add_subparsers(dest="command", help="Audit command")

    # Common arguments
    common_args = argparse.ArgumentParser(add_help=False)
    common_args.add_argument("--codebase", "-c", help="Path to frontend/backend codebase")
    common_args.add_argument("--url", "-u", help="Live instance URL (enables Layer 1 browser checks)")
    common_args.add_argument("--output", "-o", default="./audit-output", help="Output directory")

    # Detect command
    subparsers.add_parser("detect", parents=[common_args], help="Auto-detect technology stack")

    # Discover command
    subparsers.add_parser("discover", parents=[common_args], help="Discover routes and components")

    # Capture command
    subparsers.add_parser("capture", parents=[common_args], help="Capture screenshots, DOM, and network data")

    # Audit command
    subparsers.add_parser("audit", parents=[common_args], help="Run all audit checks")

    # Report command
    report_parser = subparsers.add_parser("report", parents=[common_args], help="Generate audit report")
    report_parser.add_argument("--findings", required=True, help="Path to findings.json")
    report_parser.add_argument("--previous-report", help="Previous report for diffing")

    # Full pipeline
    full_parser = subparsers.add_parser("full", parents=[common_args], help="Run complete audit pipeline")
    full_parser.add_argument("--previous-report", help="Previous report for diffing")
    full_parser.add_argument(
        "--baseline",
        help="Path to a baseline findings.json (or its output dir) to gate against",
    )
    full_parser.add_argument(
        "--fail-on",
        choices=FAIL_MODES,
        default="new-high",
        help="Exit non-zero when: new (any new issue), new-high (new high/critical), "
             "regressed (new-high or worsened severity), any, or none. Default: new-high.",
    )

    # Baseline comparison (standalone CI gate over an existing run)
    baseline_parser = subparsers.add_parser(
        "baseline", parents=[common_args], help="Compare an existing run against a baseline (CI gate)"
    )
    baseline_parser.add_argument(
        "--baseline", required=True, help="Path to baseline findings.json or its output dir"
    )
    baseline_parser.add_argument(
        "--fail-on", choices=FAIL_MODES, default="new-high", help="Gate failure mode (default: new-high)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    engine = UIAuditEngine(
        codebase_path=getattr(args, "codebase", None),
        output_dir=args.output,
        live_url=getattr(args, "url", None),
    )

    try:
        if args.command == "detect":
            engine.detect_stack()
        elif args.command == "discover":
            engine.detect_stack()
            engine.discover()
        elif args.command == "capture":
            engine.detect_stack()
            engine.capture()
        elif args.command == "audit":
            engine.detect_stack()
            engine.audit()
        elif args.command == "report":
            findings_path = Path(args.findings)
            if findings_path.exists():
                with open(findings_path) as f:
                    engine.findings = json.load(f)
            engine.generate_report(getattr(args, "previous_report", None))
        elif args.command == "full":
            engine.full_audit(getattr(args, "previous_report", None))
            baseline = getattr(args, "baseline", None)
            if baseline:
                code = engine.compare_baseline(baseline, getattr(args, "fail_on", "new-high"))
                sys.exit(code)
        elif args.command == "baseline":
            code = engine.compare_baseline(args.baseline, args.fail_on)
            sys.exit(code)
    except BrowserUnavailableError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
