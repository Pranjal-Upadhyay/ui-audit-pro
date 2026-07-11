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
from capture.screenshot_capture import ScreenshotCapture
from capture.network_interceptor import NetworkInterceptor
from capture.dom_extractor import DOMExtractor
from report_generator import ReportGenerator


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

    def detect_stack(self) -> StackInfo:
        """Auto-detect the technology stack."""
        print("[0/4] Detecting technology stack...")

        if not self.codebase:
            self.stack = StackInfo(frontend_framework="unknown", backend_framework="unknown")
            print("  No codebase provided; browser-level checks only")
            return self.stack

        detector = StackDetector(str(self.codebase))
        self.stack = detector.detect()

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
            for route in live_routes:
                url = route if isinstance(route, str) else route.get("url", "")
                if url and not any(r.get("path") == url or r.get("path") == url for r in result["routes"]):
                    result["routes"].append({"path": url, "file": None, "framework": "browser-crawl"})

        # Deduplicate routes by (path, framework) tuple
        seen = set()
        unique_routes = []
        for r in result["routes"]:
            key = (r.get("path", ""), r.get("framework", ""))
            if key not in seen:
                seen.add(key)
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
            print(f"  Capturing from live instance: {self.live_url}")

            for route in discovery.get("routes", []):
                url = route.get("path", "") if isinstance(route, dict) else str(route)
                if not url.startswith("http"):
                    url = f"{self.live_url.rstrip('/')}/{url.lstrip('/')}"

                print(f"  Capturing: {url}")

                # Screenshot
                screenshot_path = self.screenshot_capture.capture(url)
                result["screenshots"][url] = str(screenshot_path)

                # DOM snapshot
                dom_snapshot = self.dom_extractor.extract(url)
                result["dom_snapshots"][url] = dom_snapshot

                # Network logs
                network_log = self.network_interceptor.get_logs(url)
                result["network_logs"][url] = network_log
        else:
            print("  No live URL provided; skipping browser-level capture")

        # Save capture results
        capture_path = self.output / "capture.json"
        with open(capture_path, "w") as f:
            json.dump(result, f, indent=2, default=str)

        self.captured_data = result
        print(f"  Capture saved to {capture_path}")
        return result

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
        capture_data["type_contracts"] = discovery.get("type_contracts", [])
        capture_data["api_calls"] = discovery.get("api_calls", [])
        capture_data["components"] = discovery.get("components", [])

        findings = []

        # --- Layer 1: UI/UX Consistency Checks (23 categories) ---
        print("  [Layer 1] Running UI/UX consistency checks...")

        ui_checks = [
            ("Visual Identity Consistency", "visual_identity"),
            ("Spacing Rhythm", "spacing_rhythm"),
            ("Typography Scale", "typography_scale"),
            ("Icon Set Consistency", "icon_consistency"),
            ("Interaction State Consistency", "interaction_states"),
            ("Modal/Popup/Overlay Behavior", "modal_behavior"),
            ("Loading/Empty/Error State Consistency", "state_consistency"),
            ("Form Validation Consistency", "form_validation"),
            ("Content/Microcopy Consistency", "content_consistency"),
            ("Structural/Navigational Consistency", "navigation_consistency"),
            ("Responsive/Cross-Breakpoint Consistency", "responsive_consistency"),
            ("Accessibility as Consistency Signal", "accessibility"),
            ("Motion/Animation Consistency", "animation_consistency"),
            ("Layout Integrity Bugs", "layout_integrity"),
            ("Data Density/Truncation Consistency", "truncation_consistency"),
            ("Iconography/Color Semantics", "icon_color_semantics"),
            ("Empty/Zero/Singular-Plural Correctness", "grammar_correctness"),
            ("Pagination/Infinite-Scroll Consistency", "pagination_consistency"),
            ("Notification/Toast Consistency", "notification_consistency"),
            ("Permission/Role-Based UI Consistency", "permission_consistency"),
            ("Theming Consistency (Dark Mode)", "theming_consistency"),
            ("Input Affordance Consistency", "input_consistency"),
            ("Print/Export/PDF View Consistency", "print_consistency"),
        ]

        for check_name, check_id in ui_checks:
            print(f"    Checking: {check_name}")
            try:
                check_findings = self.consistency_checker.run_check(check_id, capture_data)
                findings.extend(check_findings)
            except Exception as e:
                print(f"    Warning: {check_name} check failed: {e}")

        # --- Layer 1 + 2: Frontend-Backend Integration Checks (13 categories) ---
        print("  [Layer 1+2] Running integration checks...")

        integration_checks = [
            ("API Contract/Schema Drift", "api_contract"),
            ("Type Mismatches", "type_mismatches"),
            ("Loading/Error/Empty State Wiring", "state_wiring"),
            ("Unhandled Promise Rejections", "unhandled_errors"),
            ("Race Conditions/Stale Data", "race_conditions"),
            ("Optimistic UI Correctness", "optimistic_ui"),
            ("Auth/Session Boundary Handling", "auth_handling"),
            ("Latency/Timeout Behavior", "latency_timeout"),
            ("Pagination/Data Consistency", "pagination_data"),
            ("Real-time/Websocket Sync", "websocket_sync"),
            ("File Upload/Download Edge Cases", "file_transfer"),
            ("Idempotency/Double-Submit", "double_submit"),
            ("Localization/Timezone Mismatches", "timezone_issues"),
        ]

        for check_name, check_id in integration_checks:
            print(f"    Checking: {check_name}")
            try:
                check_findings = self.integration_checker.run_check(
                    check_id, capture_data, codebase=self.codebase
                )
                findings.extend(check_findings)
            except Exception as e:
                print(f"    Warning: {check_name} check failed: {e}")

        # Annotate findings with source locations if adapters provided them
        self._annotate_findings_with_source_locations(findings, discovery)

        # Save findings
        findings_path = self.output / "findings.json"
        with open(findings_path, "w") as f:
            json.dump(findings, f, indent=2, default=str)

        self.findings = findings
        print(f"  Found {len(findings)} issues across {len(ui_checks) + len(integration_checks)} checks")
        print(f"  Findings saved to {findings_path}")
        return findings

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

        generator = ReportGenerator(
            findings=self.findings,
            discovery=discovery,
            output_dir=self.output,
            previous_report=previous_report,
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

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    engine = UIAuditEngine(
        codebase_path=getattr(args, "codebase", None),
        output_dir=args.output,
        live_url=getattr(args, "url", None),
    )

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


if __name__ == "__main__":
    main()
