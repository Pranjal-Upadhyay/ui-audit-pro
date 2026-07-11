#!/usr/bin/env python3
"""
Report Generator — Produces structured audit reports from findings.

Generates markdown reports with:
- Executive summary
- Findings grouped by severity
- Cross-cutting patterns
- Report diffing against previous runs
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Optional


SEVERITY_ORDER = ["critical", "high", "medium", "low"]
SEVERITY_EMOJI = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🟢",
}


class ReportGenerator:
    """Generates structured audit reports from findings."""

    def __init__(
        self,
        findings: List[Dict],
        discovery: Dict,
        output_dir: Path,
        previous_report: Optional[str] = None,
    ):
        self.findings = findings
        self.discovery = discovery
        self.output_dir = Path(output_dir)
        self.previous_report = previous_report

    def generate(self) -> str:
        """Generate the full audit report and return the file path."""
        # Group findings by severity
        by_severity = defaultdict(list)
        for f in self.findings:
            by_severity[f.get("severity", "medium")].append(f)

        # Build report sections
        sections = [
            self._header(),
            self._executive_summary(by_severity),
            self._severity_breakdown(by_severity),
            self._findings_by_severity(by_severity),
            self._cross_cutting_patterns(),
            self._diff_section() if self.previous_report else "",
            self._appendix(),
        ]

        report = "\n\n".join(s for s in sections if s)

        # Write report
        report_path = self.output_dir / "audit-report.md"
        with open(report_path, "w") as f:
            f.write(report)

        # Also save findings JSON for future diffing
        findings_path = self.output_dir / "findings.json"
        with open(findings_path, "w") as f:
            json.dump(self.findings, f, indent=2, default=str)

        return str(report_path)

    def _header(self) -> str:
        return f"""# UI/UX Audit Report

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Total Findings:** {len(self.findings)}
**Routes Scanned:** {len(self.discovery.get("routes", []))}
**Components Scanned:** {len(self.discovery.get("components", []))}
**API Calls Scanned:** {len(self.discovery.get("api_calls", []))}"""

    def _executive_summary(self, by_severity: Dict) -> str:
        critical = len(by_severity.get("critical", []))
        high = len(by_severity.get("high", []))
        medium = len(by_severity.get("medium", []))
        low = len(by_severity.get("low", []))

        total = critical + high + medium + low

        # Generate narrative
        if critical > 0:
            health = "poor"
            narrative = (
                f"The application has {critical} critical issue(s) that require immediate attention. "
                "These issues may break core user flows, cause data loss/corruption, or present "
                "security vulnerabilities."
            )
        elif high > 0:
            health = "concerning"
            narrative = (
                f"The application has {high} high-severity issue(s) that significantly impact "
                "user trust or usability. While core flows remain functional, these issues "
                "should be addressed before the next release."
            )
        elif medium > 0:
            health = "fair"
            narrative = (
                f"The application has {medium} medium-severity issue(s) that affect perceived "
                "quality and professionalism. Functionality is intact, but visual/behavioral "
                "inconsistencies erode user confidence."
            )
        elif low > 0:
            health = "good"
            narrative = (
                f"The application has only {low} low-severity polish issue(s). "
                "The overall UI/UX is consistent and well-integrated."
            )
        else:
            health = "excellent"
            narrative = (
                "No issues were found. The application demonstrates strong UI/UX consistency "
                "and proper frontend-backend integration."
            )

        return f"""## Executive Summary

**Overall Health:** {health.upper()}

| Severity | Count |
|----------|-------|
| 🔴 Critical | {critical} |
| 🟠 High | {high} |
| 🟡 Medium | {medium} |
| 🟢 Low | {low} |
| **Total** | **{total}** |

{narrative}"""

    def _severity_breakdown(self, by_severity: Dict) -> str:
        # Group by category
        by_category = defaultdict(lambda: defaultdict(int))
        for f in self.findings:
            cat = f.get("category", "Unknown")
            sev = f.get("severity", "medium")
            by_category[cat][sev] += 1

        rows = []
        for cat in sorted(by_category.keys()):
            counts = by_category[cat]
            total = sum(counts.values())
            rows.append(
                f"| {cat} | {counts.get('critical', 0)} | {counts.get('high', 0)} "
                f"| {counts.get('medium', 0)} | {counts.get('low', 0)} | {total} |"
            )

        return f"""## Findings by Category

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
{chr(10).join(rows)}"""

    def _findings_by_severity(self, by_severity: Dict) -> str:
        sections = []

        for severity in SEVERITY_ORDER:
            findings = by_severity.get(severity, [])
            if not findings:
                continue

            emoji = SEVERITY_EMOJI[severity]
            title = severity.upper()

            finding_blocks = []
            for i, f in enumerate(findings, 1):
                finding_blocks.append(self._format_finding(f, i))

            sections.append(
                f"""## {emoji} {title} ({len(findings)})

{chr(10).join(finding_blocks)}"""
            )

        return "\n\n".join(sections)

    def _format_finding(self, finding: Dict, index: int) -> str:
        if not isinstance(finding, dict):
            return f"### {index}. Invalid finding format\n\n"

        title = finding.get("title", "Untitled")
        category = finding.get("category", "Unknown")
        location = finding.get("location", "Unknown")
        description = finding.get("description", "")
        evidence = finding.get("evidence", "")
        fix = finding.get("recommended_fix", "")
        effort = finding.get("effort", "unknown")

        # Build location links if file paths
        location_text = location
        if isinstance(location, dict):
            parts = []
            if location.get("file"):
                parts.append(f"`{location['file']}`")
            if location.get("line"):
                parts[-1] += f" (line {location['line']})"
            if location.get("route"):
                parts.append(f"Route: `{location['route']}`")
            if location.get("component"):
                parts.append(f"Component: `{location['component']}`")
            location_text = " | ".join(parts) if parts else "Unknown"

        evidence_block = ""
        if evidence:
            if isinstance(evidence, list):
                evidence_items = "\n".join(f"- {e}" for e in evidence)
                evidence_block = f"\n\n**Evidence:**\n{evidence_items}"
            else:
                evidence_block = f"\n\n**Evidence:** {evidence}"

        return f"""### {index}. {title}

| Field | Value |
|-------|-------|
| **Category** | {category} |
| **Location** | {location_text} |
| **Effort** | {effort} |

**Description:** {description}{evidence_block}

**Recommended Fix:** {fix}

---"""

    def _cross_cutting_patterns(self) -> str:
        # Identify findings that share the same root cause
        root_causes = defaultdict(list)
        for f in self.findings:
            root_cause = f.get("root_cause")
            if root_cause:
                root_causes[root_cause].append(f)

        if not root_causes:
            return ""

        blocks = []
        for cause, related in root_causes.items():
            if len(related) < 2:
                continue

            titles = "\n".join(f"- {f.get('title', 'Untitled')}" for f in related)
            fix = related[0].get("cross_cutting_fix", "Address the root cause to resolve all related issues.")

            blocks.append(f"""#### Root Cause: {cause}

**Affected Findings ({len(related)}):**
{titles}

**Single Fix:** {fix}""")

        if not blocks:
            return ""

        return f"""## Cross-Cutting Patterns

The same root cause produces multiple findings. Addressing the root cause resolves all related issues.

{chr(10).join(blocks)}"""

    def _diff_section(self) -> str:
        if not self.previous_report:
            return ""

        try:
            prev_path = Path(self.previous_report)
            if not prev_path.exists():
                return ""

            with open(prev_path) as f:
                prev_content = f.read()

            # Parse previous findings if available
            prev_findings_path = prev_path.parent / "findings.json"
            if prev_findings_path.exists():
                with open(prev_findings_path) as f:
                    prev_findings = json.load(f)
            else:
                prev_findings = []

            # Compare
            current_ids = {f.get("id", f.get("title")) for f in self.findings}
            prev_ids = {f.get("id", f.get("title")) for f in prev_findings}

            new_issues = current_ids - prev_ids
            resolved_issues = prev_ids - current_ids
            persistent = current_ids & prev_ids

            new_items = "\n".join(f"- {nid}" for nid in new_issues) if new_issues else "- None"
            resolved_items = "\n".join(f"- {rid}" for rid in resolved_issues) if resolved_issues else "- None"
            persistent_items = f"{len(persistent)}" if persistent else "0"

            return f"""## Report Diff (vs. Previous Run)

| Status | Count |
|--------|-------|
| 🆕 New Issues | {len(new_issues)} |
| ✅ Resolved | {len(resolved_issues)} |
| ⏳ Persistent | {persistent_items} |

### New Issues
{new_items}

### Resolved Issues
{resolved_items}"""

        except Exception:
            return ""

    def _appendix(self) -> str:
        routes = self.discovery.get("routes", [])
        components = self.discovery.get("components", [])
        api_calls = self.discovery.get("api_calls", [])

        route_list = "\n".join(
            f"- `{r}`" if isinstance(r, str) else f"- `{r.get('url', 'unknown')}`"
            for r in routes[:50]
        ) or "- None discovered"

        component_list = "\n".join(
            f"- `{c}`" if isinstance(c, str) else f"- `{c.get('name', 'unknown')}`"
            for c in components[:50]
        ) or "- None discovered"

        api_list = "\n".join(
            f"- `{a}`" if isinstance(a, str) else f"- `{a.get('endpoint', 'unknown')}`"
            for a in api_calls[:50]
        ) or "- None discovered"

        # Determine mode
        has_code = bool(self.discovery.get("components") or self.discovery.get("api_calls"))
        has_live = bool(self.discovery.get("screenshots"))
        if has_code and has_live:
            mode = "Combined (code + live instance)"
        elif has_code:
            mode = "Code-only (static analysis)"
        elif has_live:
            mode = "Live-instance (browser automation)"
        else:
            mode = "Unknown"

        return f"""## Appendix

### Audit Mode
{mode}

### Routes Scanned ({len(routes)})
{route_list}

### Components Scanned ({len(components)})
{component_list}

### API Calls Scanned ({len(api_calls)})
{api_list}

### Methods Used
- Static code analysis (AST parsing, CSS extraction, type inference)
- Browser automation (screenshot capture, DOM extraction)
- Network interception (request/response logging)
- Style computation (computed styles, design token extraction)
- Automated a11y checks (contrast, ARIA, focus management)

### Areas Not Tested
- Features behind authentication walls (unless test credentials provided)
- Third-party embedded content
- Native mobile app components
- Server-side rendering edge cases (unless source available)
"""


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate audit report from findings")
    parser.add_argument("--findings", required=True, help="Path to findings.json")
    parser.add_argument("--discovery", help="Path to discovery.json")
    parser.add_argument("--output", default="./audit-output", help="Output directory")
    parser.add_argument("--previous-report", help="Previous report for diffing")

    args = parser.parse_args()

    with open(args.findings) as f:
        findings = json.load(f)

    discovery = {}
    if args.discovery and Path(args.discovery).exists():
        with open(args.discovery) as f:
            discovery = json.load(f)

    generator = ReportGenerator(
        findings=findings,
        discovery=discovery,
        output_dir=Path(args.output),
        previous_report=args.previous_report,
    )

    report_path = generator.generate()
    print(f"Report generated: {report_path}")
