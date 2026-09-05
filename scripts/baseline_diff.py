#!/usr/bin/env python3
"""
Baseline Diff — Turn a one-shot audit into a repeatable CI gate.

Compares a current findings set against a saved baseline and computes what is
NEW, RESOLVED, and PERSISTENT. Crucially it is *coverage-aware*: a finding that
disappeared only because its check was skipped this run is reported as
UNVERIFIED, not RESOLVED — otherwise reduced coverage would silently hide
regressions, the exact failure mode this whole tool exists to prevent.

Exit-code semantics (via `gate()`) let CI fail the build on regressions.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Set

SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}
FAIL_MODES = ("none", "new", "new-high", "regressed", "any")


def load_findings(path: Path) -> List[Dict]:
    """Load a findings list from a findings.json file or its parent directory."""
    path = Path(path)
    if path.is_dir():
        path = path / "findings.json"
    with open(path) as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("findings", [])


def load_coverage(path: Path) -> Optional[Dict]:
    """Load coverage.json sitting next to a findings.json, if present."""
    path = Path(path)
    cov_path = (path / "coverage.json") if path.is_dir() else (path.parent / "coverage.json")
    if cov_path.exists():
        with open(cov_path) as f:
            return json.load(f)
    return None


def _finding_id(f: Dict) -> str:
    return f.get("id") or f.get("title") or "unknown"


def _skipped_categories(coverage: Optional[Dict]) -> Set[str]:
    """Category/check display-names that did NOT run in a given coverage record."""
    if not coverage:
        return set()
    return {c.get("name") for c in coverage.get("skipped", []) if c.get("name")}


def diff(
    baseline: List[Dict],
    current: List[Dict],
    baseline_coverage: Optional[Dict] = None,
    current_coverage: Optional[Dict] = None,
) -> Dict:
    """Compute a coverage-aware diff between two findings sets."""
    base_by_id = {_finding_id(f): f for f in baseline}
    cur_by_id = {_finding_id(f): f for f in current}
    base_ids = set(base_by_id)
    cur_ids = set(cur_by_id)

    new_ids = cur_ids - base_ids
    gone_ids = base_ids - cur_ids
    persistent_ids = cur_ids & base_ids

    # A baseline finding that's absent now is only genuinely RESOLVED if its
    # check actually ran this time. If the check was skipped, we can't claim
    # resolution — flag it UNVERIFIED so a coverage drop can't mask a regression.
    current_skipped = _skipped_categories(current_coverage)
    resolved, unverified = [], []
    for fid in gone_ids:
        f = base_by_id[fid]
        if f.get("category") in current_skipped:
            unverified.append(f)
        else:
            resolved.append(f)

    # Severity regressions among persistent findings (same id, worse severity).
    severity_regressions = []
    for fid in persistent_ids:
        old_sev = SEVERITY_ORDER.get(base_by_id[fid].get("severity", "low"), 0)
        new_sev = SEVERITY_ORDER.get(cur_by_id[fid].get("severity", "low"), 0)
        if new_sev > old_sev:
            severity_regressions.append(cur_by_id[fid])

    new_findings = [cur_by_id[i] for i in new_ids]
    new_high = [f for f in new_findings if f.get("severity") in ("high", "critical")]

    # Did overall coverage shrink vs. the baseline? If so, the diff is partial.
    base_skipped = _skipped_categories(baseline_coverage)
    coverage_regressed = sorted(current_skipped - base_skipped)

    return {
        "new": new_findings,
        "new_high": new_high,
        "resolved": resolved,
        "unverified": unverified,
        "persistent": sorted(persistent_ids),
        "severity_regressions": severity_regressions,
        "coverage_regressed": coverage_regressed,
    }


def gate(diff_result: Dict, fail_on: str = "new-high") -> bool:
    """Return True if the gate should FAIL (CI should exit non-zero)."""
    if fail_on == "none":
        return False
    if fail_on == "any":
        return bool(diff_result["new"] or diff_result["severity_regressions"])
    if fail_on == "new":
        return bool(diff_result["new"])
    if fail_on == "new-high":
        return bool(diff_result["new_high"])
    if fail_on == "regressed":
        return bool(diff_result["new_high"] or diff_result["severity_regressions"])
    raise ValueError(f"Unknown fail_on mode: {fail_on!r}. Expected one of {FAIL_MODES}.")


def format_summary(diff_result: Dict) -> str:
    """Human-readable one-screen summary for console/CI logs."""
    lines = []
    lines.append(f"  New issues:            {len(diff_result['new'])}"
                 f"  (high/critical: {len(diff_result['new_high'])})")
    lines.append(f"  Resolved:              {len(diff_result['resolved'])}")
    lines.append(f"  Unverified (skipped):  {len(diff_result['unverified'])}")
    lines.append(f"  Persistent:            {len(diff_result['persistent'])}")
    lines.append(f"  Severity regressions:  {len(diff_result['severity_regressions'])}")

    if diff_result["new"]:
        lines.append("\n  NEW:")
        for f in diff_result["new"]:
            lines.append(f"    [{f.get('severity', '?').upper()}] {_finding_id(f)} — {f.get('title', '')}")
    if diff_result["severity_regressions"]:
        lines.append("\n  REGRESSED (severity increased):")
        for f in diff_result["severity_regressions"]:
            lines.append(f"    [{f.get('severity', '?').upper()}] {_finding_id(f)} — {f.get('title', '')}")
    if diff_result["unverified"]:
        lines.append("\n  UNVERIFIED — these baseline issues could NOT be re-checked "
                     "(their check was skipped this run); NOT counted as resolved:")
        for f in diff_result["unverified"]:
            lines.append(f"    {_finding_id(f)} — {f.get('category', '')}")
    if diff_result["coverage_regressed"]:
        lines.append("\n  ⚠ COVERAGE REGRESSED vs baseline — checks skipped now that ran before:")
        for name in diff_result["coverage_regressed"]:
            lines.append(f"    - {name}")

    return "\n".join(lines)
