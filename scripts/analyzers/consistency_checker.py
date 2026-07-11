#!/usr/bin/env python3
"""
Consistency Checker — Runs UI/UX consistency checks against captured data.

Implements all 23 consistency categories from the audit spec.
"""

import re
from typing import Dict, List, Optional
from collections import defaultdict


class ConsistencyChecker:
    """Runs UI/UX consistency checks against captured data."""

    def run_check(self, check_id: str, capture_data: Dict, codebase=None) -> List[Dict]:
        """Run a specific consistency check and return findings."""
        method = getattr(self, f"_check_{check_id}", None)
        if method:
            return method(capture_data, codebase)
        return []

    def _check_visual_identity(self, data: Dict, codebase=None) -> List[Dict]:
        """Check visual identity consistency across components.

        Semantic-role clustering groups elements by their inferred role
        (derived from text content + tag) rather than by CSS class names.
        Two buttons with text 'Add to Cart' on different pages are grouped
        together even if they have different class names.
        """
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        # Collect all interactive elements with their semantic role
        # Semantic role = normalized text content + tag (not CSS class)
        role_groups = defaultdict(list)

        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            elements = snapshot.get("elements", [])
            for el in elements:
                tag = el.get("tag", "")
                text = el.get("text", "").strip().lower()
                styles_dict = el.get("computed_styles", {})

                if not text or tag not in ("button", "a", "input", "select", "textarea"):
                    continue

                # Infer semantic role from text content + tag
                # Normalize: 'Add to Cart' and 'add to cart' -> 'button:add to cart'
                semantic_role = f"{tag}:{text}"

                # Create style signature for comparison
                if tag in ("button", "a"):
                    style_sig = self._style_signature(styles_dict, [
                        "background-color", "border-radius", "padding",
                        "font-size", "font-weight", "color",
                    ])
                elif tag in ("input", "select", "textarea"):
                    style_sig = self._style_signature(styles_dict, [
                        "border", "border-radius", "padding", "font-size",
                    ])

                role_groups[semantic_role].append({
                    "url": url,
                    "element": el,
                    "style_sig": style_sig,
                    "tag": tag,
                    "text": text,
                })

        # For each semantic role, check if all instances share the same style
        for role, instances in role_groups.items():
            if len(instances) < 2:
                continue  # Need at least 2 to compare

            # Group by style signature
            sig_groups = defaultdict(list)
            for inst in instances:
                sig_groups[inst["style_sig"]].append(inst)

            if len(sig_groups) > 1:
                # Multiple different styles for the same semantic role!
                dominant_sig = max(sig_groups.keys(), key=lambda s: len(sig_groups[s]))
                dominant_count = len(sig_groups[dominant_sig])

                for sig, variant_instances in sig_groups.items():
                    if sig == dominant_sig:
                        continue

                    # Collect all locations where the inconsistent variant appears
                    locations = [inst["url"] for inst in variant_instances]

                    findings.append({
                        "id": f"visual-identity-{role[:30]}",
                        "title": f"Inconsistent styling for '{instances[0]['text']}' buttons",
                        "category": "Visual Identity Consistency",
                        "severity": "medium",
                        "location": {
                            "route": variant_instances[0]["url"],
                            "component": f"{instances[0]['tag']} with text '{instances[0]['text']}'",
                            "all_locations": locations,
                        },
                        "description": (
                            f"Found {len(variant_instances)} instances of '{instances[0]['text']}' "
                            f"with non-standard styling across routes: {locations}. "
                            f"The dominant pattern ({dominant_count} instances) uses different styles."
                        ),
                        "evidence": {
                            "semantic_role": role,
                            "variant_style": sig,
                            "dominant_style": dominant_sig,
                            "variant_count": len(variant_instances),
                            "dominant_count": dominant_count,
                            "affected_routes": locations,
                        },
                        "recommended_fix": (
                            f"Standardize '{instances[0]['text']}' button styling across all routes "
                            f"to match the dominant pattern ({dominant_count} instances)"
                        ),
                        "effort": "small",
                    })

        return findings

    def _check_spacing_rhythm(self, data: Dict, codebase=None) -> List[Dict]:
        """Check spacing follows a consistent grid."""
        findings = []
        styles = data.get("computed_styles", {})

        # Analyze CSS files for spacing values
        css_files = styles.get("css_files", {})
        non_grid_values = set()

        for file_path, content in css_files.items():
            for match in re.finditer(
                r"(?:margin|padding)(?:-(?:top|right|bottom|left))?:\s*([\d.]+)px",
                content,
            ):
                value = float(match.group(1))
                if value % 4 != 0:
                    non_grid_values.add(value)

        if non_grid_values:
            findings.append({
                "id": "spacing-off-grid",
                "title": "Spacing values not on 4px grid",
                "category": "Spacing Rhythm",
                "severity": "medium",
                "description": f"Found {len(non_grid_values)} spacing values not on a 4px grid: {sorted(non_grid_values)[:10]}",
                "evidence": f"Off-grid values: {sorted(non_grid_values)}",
                "recommended_fix": "Standardize all spacing to 4px increments (4, 8, 12, 16, 20, 24, 32, 40, 48, 64)",
                "effort": "small",
                "root_cause": "No spacing scale defined" if len(non_grid_values) > 5 else None,
            })

        return findings

    def _check_typography_scale(self, data: Dict, codebase=None) -> List[Dict]:
        """Check typography follows a consistent scale."""
        findings = []
        styles = data.get("computed_styles", {})

        css_files = styles.get("css_files", {})
        font_sizes = set()

        for file_path, content in css_files.items():
            for match in re.finditer(r"font-size:\s*([\d.]+)(?:px|rem|em)", content):
                try:
                    value = float(match.group(1))
                    if "rem" in match.group(0) or "em" in match.group(0):
                        value *= 16  # Convert to px
                    font_sizes.add(value)
                except ValueError:
                    continue

        # Check for one-off sizes
        standard_sizes = {10, 12, 14, 16, 18, 20, 24, 30, 36, 48, 60, 72, 96}
        one_offs = font_sizes - standard_sizes

        if len(one_offs) > 2:
            findings.append({
                "id": "typography-one-offs",
                "title": "Font sizes not from consistent scale",
                "category": "Typography Scale",
                "severity": "medium",
                "description": f"Found {len(one_offs)} non-standard font sizes: {sorted(one_offs)}",
                "evidence": f"One-off sizes: {sorted(one_offs)} px. Standard sizes found: {sorted(font_sizes & standard_sizes)}",
                "recommended_fix": "Define a type scale and refactor all font-size declarations to use it",
                "effort": "medium",
            })

        return findings

    def _check_icon_consistency(self, data: Dict, codebase=None) -> List[Dict]:
        """Check icon set consistency."""
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        icon_libraries = set()
        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            icons = snapshot.get("icons", [])
            for icon in icons:
                lib = icon.get("library", "unknown")
                if lib != "unknown":
                    icon_libraries.add(lib)

        if len(icon_libraries) > 1:
            findings.append({
                "id": "icon-library-mix",
                "title": "Multiple icon libraries in use",
                "category": "Icon Set Consistency",
                "severity": "medium",
                "description": f"Found {len(icon_libraries)} different icon libraries: {icon_libraries}",
                "evidence": f"Libraries: {icon_libraries}",
                "recommended_fix": "Standardize on a single icon library (e.g., Lucide, Heroicons) throughout the app",
                "effort": "medium",
            })

        return findings

    def _check_interaction_states(self, data: Dict, codebase=None) -> List[Dict]:
        """Check interaction state consistency."""
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        # Check for hover states on interactive elements
        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            elements = snapshot.get("interactive_elements", [])
            for el in elements:
                has_hover = el.get("has_hover_style", False)
                has_focus = el.get("has_focus_style", False)
                tag = el.get("tag", "")

                if not has_hover and tag in ("button", "a"):
                    findings.append({
                        "id": f"missing-hover-{el.get('id', 'unknown')}",
                        "title": "Interactive element missing hover state",
                        "category": "Interaction State Consistency",
                        "severity": "low",
                        "location": {"route": url, "component": tag},
                        "description": f"Element '{el.get('text', '')}' lacks hover state styling",
                        "recommended_fix": "Add :hover pseudo-class styles for visual feedback",
                        "effort": "trivial",
                    })

        return findings

    def _check_modal_behavior(self, data: Dict, codebase=None) -> List[Dict]:
        """Check modal/popup/overlay behavior consistency."""
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        modals = []
        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            for modal in snapshot.get("modals", []):
                modals.append({**modal, "url": url})

        if len(modals) > 1:
            # Check for consistent close behavior
            has_escape = [m for m in modals if m.get("closes_on_escape")]
            has_backdrop = [m for m in modals if m.get("closes_on_backdrop_click")]

            if has_escape and len(has_escape) < len(modals):
                findings.append({
                    "id": "modal-inconsistent-escape",
                    "title": "Inconsistent Escape key handling in modals",
                    "category": "Modal/Popup/Overlay Behavior",
                    "severity": "medium",
                    "description": f"Some modals close on Escape ({len(has_escape)}), others don't ({len(modals) - len(has_escape)})",
                    "recommended_fix": "All modals should close on Escape key press for consistency",
                    "effort": "trivial",
                })

        return findings

    def _check_state_consistency(self, data: Dict, codebase=None) -> List[Dict]:
        """Check loading/empty/error state consistency."""
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue

            # Check for lists/grids without loading states
            lists = snapshot.get("lists", [])
            for lst in lists:
                if not lst.get("has_loading_state"):
                    findings.append({
                        "id": f"missing-loading-{url}-{lst.get('type', 'list')}",
                        "title": "List missing loading state",
                        "category": "Loading/Empty/Error State Consistency",
                        "severity": "medium",
                        "location": {"route": url},
                        "description": f"List/grid component lacks a loading skeleton or spinner",
                        "recommended_fix": "Add skeleton loading state for all data-driven lists",
                        "effort": "small",
                    })

        # Check for inconsistent empty-state text across routes
        empty_texts = defaultdict(set)
        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            # Look for empty state indicators
            for el in snapshot.get("elements", []):
                classes = el.get("classes", "")
                if isinstance(classes, str) and any(k in classes.lower() for k in ["empty", "no-data", "zero", "placeholder"]):
                    text = el.get("text", "").strip()
                    if text:
                        empty_texts[text].add(url)
            # Also check text_elements for common empty state patterns
            for te in snapshot.get("text_elements", []):
                text = te.get("text", "").strip()
                if text and any(p in text.lower() for p in ["no items", "0 items", "empty", "nothing found", "no results"]):
                    empty_texts[text].add(url)

        if len(empty_texts) > 1:
            # Multiple different empty state texts found across routes
            texts_list = [(text, urls) for text, urls in empty_texts.items()]
            findings.append({
                "id": "inconsistent-empty-state",
                "title": "Inconsistent empty state text across routes",
                "category": "Loading/Empty/Error State Consistency",
                "severity": "medium",
                "description": f"Found {len(texts_list)} different empty state messages: {[t for t, u in texts_list]}",
                "evidence": {"empty_texts": {t: list(u) for t, u in texts_list}},
                "recommended_fix": "Standardize empty state messaging across all routes",
                "effort": "small",
            })

        return findings

    def _check_form_validation(self, data: Dict, codebase=None) -> List[Dict]:
        """Check form validation consistency."""
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        forms = []
        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            for form in snapshot.get("forms", []):
                forms.append({**form, "url": url})

        if len(forms) > 1:
            validation_styles = set()
            for form in forms:
                style = form.get("validation_style", "unknown")
                validation_styles.add(style)

            if len(validation_styles) > 1:
                findings.append({
                    "id": "form-validation-inconsistent",
                    "title": "Inconsistent form validation styles",
                    "category": "Form Validation Consistency",
                    "severity": "medium",
                    "description": f"Found {len(validation_styles)} different validation patterns across forms: {validation_styles}",
                    "recommended_fix": "Standardize on a single validation pattern (inline errors, toast notifications, etc.)",
                    "effort": "small",
                })

        return findings

    def _check_content_consistency(self, data: Dict, codebase=None) -> List[Dict]:
        """Check content and microcopy consistency."""
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        # Check for inconsistent button labels
        button_labels = set()
        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            for btn in snapshot.get("buttons", []):
                label = btn.get("text", "").strip()
                if label:
                    button_labels.add(label)

        # Check for casing inconsistencies
        title_case = {l for l in button_labels if l.istitle()}
        sentence_case = {l for l in button_labels if l[0].isupper() and not l.istitle()}
        lower_case = {l for l in button_labels if l[0].islower()}

        if len([s for s in [title_case, sentence_case, lower_case] if s]) > 1:
            findings.append({
                "id": "button-casing-inconsistent",
                "title": "Inconsistent button label casing",
                "category": "Content/Microcopy Consistency",
                "severity": "low",
                "description": "Button labels use mixed casing styles (Title Case, Sentence case, lowercase)",
                "evidence": {
                    "title_case": list(title_case)[:5],
                    "sentence_case": list(sentence_case)[:5],
                    "lower_case": list(lower_case)[:5],
                },
                "recommended_fix": "Standardize button labels to a single casing convention (e.g., Title Case for all CTAs)",
                "effort": "trivial",
            })

        return findings

    def _check_navigation_consistency(self, data: Dict, codebase=None) -> List[Dict]:
        """Check structural/navigational consistency."""
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        # Check breadcrumb consistency
        breadcrumbs = []
        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            has_breadcrumb = snapshot.get("has_breadcrumb", False)
            breadcrumbs.append({"url": url, "has_breadcrumb": has_breadcrumb})

        if breadcrumbs:
            with_breadcrumb = [b for b in breadcrumbs if b["has_breadcrumb"]]
            without_breadcrumb = [b for b in breadcrumbs if not b["has_breadcrumb"]]

            if with_breadcrumb and without_breadcrumb:
                findings.append({
                    "id": "breadcrumb-inconsistent",
                    "title": "Inconsistent breadcrumb presence",
                    "category": "Structural/Navigational Consistency",
                    "severity": "low",
                    "description": f"{len(with_breadcrumb)} routes have breadcrumbs, {len(without_breadcrumb)} don't",
                    "recommended_fix": "Add breadcrumbs to all deep-nested routes for consistent navigation",
                    "effort": "small",
                })

        return findings

    def _check_responsive_consistency(self, data: Dict, codebase=None) -> List[Dict]:
        """Check responsive/cross-breakpoint consistency."""
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            breakpoint_issues = snapshot.get("breakpoint_issues", [])
            for issue in breakpoint_issues:
                findings.append({
                    "id": f"responsive-{url}-{issue.get('element', 'unknown')}",
                    "title": f"Responsive issue: {issue.get('description', 'Unknown')}",
                    "category": "Responsive/Cross-Breakpoint Consistency",
                    "severity": "medium",
                    "location": {"route": url, "component": issue.get("element", "unknown")},
                    "description": issue.get("description", ""),
                    "recommended_fix": issue.get("fix", "Review responsive behavior at this breakpoint"),
                    "effort": "small",
                })

        return findings

    def _check_accessibility(self, data: Dict, codebase=None) -> List[Dict]:
        """Check accessibility issues."""
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue

            a11y_issues = snapshot.get("a11y_issues", [])
            for issue in a11y_issues:
                severity = "high" if issue.get("impact") == "critical" else "medium"
                findings.append({
                    "id": f"a11y-{issue.get('type', 'unknown')}-{url}",
                    "title": issue.get("title", "Accessibility issue"),
                    "category": "Accessibility as Consistency Signal",
                    "severity": severity,
                    "location": {"route": url, "element": issue.get("element", "unknown")},
                    "description": issue.get("description", ""),
                    "evidence": issue.get("evidence", ""),
                    "recommended_fix": issue.get("fix", "Fix accessibility issue"),
                    "effort": issue.get("effort", "small"),
                })

        return findings

    def _check_animation_consistency(self, data: Dict, codebase=None) -> List[Dict]:
        """Check motion/animation consistency."""
        findings = []
        styles = data.get("computed_styles", {})

        css_files = styles.get("css_files", {})
        transition_durations = set()

        for file_path, content in css_files.items():
            for match in re.finditer(r"transition-duration:\s*([\d.]+)(?:ms|s)", content):
                try:
                    value = float(match.group(1))
                    if "s" in match.group(0):
                        value *= 1000
                    transition_durations.add(value)
                except ValueError:
                    continue

        if len(transition_durations) > 5:
            findings.append({
                "id": "animation-duration-inconsistent",
                "title": "Too many transition durations",
                "category": "Motion/Animation Consistency",
                "severity": "low",
                "description": f"Found {len(transition_durations)} different transition durations: {sorted(transition_durations)}",
                "recommended_fix": "Standardize to 2-3 durations (e.g., 150ms, 300ms, 500ms)",
                "effort": "small",
            })

        return findings

    def _check_layout_integrity(self, data: Dict, codebase=None) -> List[Dict]:
        """Check layout integrity bugs."""
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            layout_issues = snapshot.get("layout_issues", [])
            for issue in layout_issues:
                findings.append({
                    "id": f"layout-{issue.get('type', 'unknown')}-{url}",
                    "title": f"Layout issue: {issue.get('type', 'Unknown')}",
                    "category": "Layout Integrity Bugs",
                    "severity": "high" if issue.get("severity") == "high" else "medium",
                    "location": {"route": url, "element": issue.get("element", "unknown")},
                    "description": issue.get("description", ""),
                    "recommended_fix": issue.get("fix", "Fix layout issue"),
                    "effort": "small",
                })

        return findings

    def _check_truncation_consistency(self, data: Dict, codebase=None) -> List[Dict]:
        """Check data density/truncation consistency."""
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            # Check for text overflow issues
            elements = snapshot.get("elements", [])
            for el in elements:
                styles = el.get("computed_styles", {})
                overflow = styles.get("overflow", "")
                text_overflow = styles.get("text-overflow", "")
                if overflow == "visible" and el.get("text", "") and len(el.get("text", "")) > 100:
                    findings.append({
                        "id": f"truncation-{el.get('id', 'unknown')}-{url}",
                        "title": "Long text without truncation",
                        "category": "Data Density/Truncation Consistency",
                        "severity": "low",
                        "location": {"route": url, "component": el.get("tag", "unknown")},
                        "description": f"Element contains long text ({len(el.get('text', ''))} chars) without truncation",
                        "recommended_fix": "Add text-overflow: ellipsis and overflow: hidden for long text",
                        "effort": "trivial",
                    })
        return findings

    def _check_icon_color_semantics(self, data: Dict, codebase=None) -> List[Dict]:
        """Check iconography and color semantics."""
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        # Check for consistent color usage (red = danger, green = success, etc.)
        color_meanings = defaultdict(set)
        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            for element in snapshot.get("elements", []):
                color = element.get("computed_styles", {}).get("color", "")
                bg = element.get("computed_styles", {}).get("background-color", "")
                text = element.get("text", "").lower()

                if "delete" in text or "remove" in text or "danger" in text:
                    if bg and "red" not in bg.lower() and "danger" not in bg.lower():
                        color_meanings["danger-not-red"].add(url)

        if color_meanings.get("danger-not-red"):
            findings.append({
                "id": "color-semantics-danger",
                "title": "Danger actions not using red consistently",
                "category": "Iconography/Color Semantics",
                "severity": "medium",
                "description": "Delete/remove actions found without red/danger color styling",
                "evidence": f"Affected routes: {color_meanings['danger-not-red']}",
                "recommended_fix": "Use red/danger color for all destructive actions consistently",
                "effort": "small",
            })

        return findings

    def _check_grammar_correctness(self, data: Dict, codebase=None) -> List[Dict]:
        """Check empty/zero/singular-plural correctness."""
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            for element in snapshot.get("text_elements", []):
                text = element.get("text", "")
                # Check for "1 items", "1 reviews", etc.
                if re.search(r"\b1\s+(items|reviews|comments|users|posts|messages|notifications)\b", text):
                    findings.append({
                        "id": f"grammar-plural-{hash(text)}",
                        "title": "Incorrect pluralization",
                        "category": "Empty/Zero/Singular-Plural Correctness",
                        "severity": "low",
                        "location": {"route": url, "text": text},
                        "description": f"Found incorrect plural form: '{text}'",
                        "recommended_fix": "Use singular form for count of 1 (e.g., '1 item' not '1 items')",
                        "effort": "trivial",
                    })

        return findings

    def _check_pagination_consistency(self, data: Dict, codebase=None) -> List[Dict]:
        """Check pagination/infinite-scroll consistency."""
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        pagination_types = set()
        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            for lst in snapshot.get("lists", []):
                has_pagination = lst.get("has_pagination", False)
                has_infinite_scroll = lst.get("has_infinite_scroll", False)
                if has_pagination:
                    pagination_types.add("numbered")
                elif has_infinite_scroll:
                    pagination_types.add("infinite-scroll")

        if len(pagination_types) > 1:
            findings.append({
                "id": "pagination-inconsistent",
                "title": "Mixed pagination patterns",
                "category": "Pagination/Infinite-Scroll Consistency",
                "severity": "medium",
                "description": f"Found {len(pagination_types)} different pagination patterns: {pagination_types}",
                "recommended_fix": "Standardize on a single pagination pattern for similar list types",
                "effort": "small",
            })
        return findings

    def _check_notification_consistency(self, data: Dict, codebase=None) -> List[Dict]:
        """Check notification/toast consistency."""
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        toast_positions = set()
        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            for toast in snapshot.get("toasts", []):
                pos = toast.get("position", "unknown")
                toast_positions.add(pos)

        if len(toast_positions) > 1:
            findings.append({
                "id": "toast-position-inconsistent",
                "title": "Inconsistent toast notification positions",
                "category": "Notification/Toast Consistency",
                "severity": "low",
                "description": f"Found {len(toast_positions)} different toast positions: {toast_positions}",
                "recommended_fix": "Standardize toast position (e.g., top-right) across all notifications",
                "effort": "trivial",
            })

        return findings

    def _check_permission_consistency(self, data: Dict, codebase=None) -> List[Dict]:
        """Check permission/role-based UI consistency."""
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            elements = snapshot.get("elements", [])
            disabled_elements = [e for e in elements if e.get("disabled")]
            hidden_elements = [e for e in elements if e.get("hidden")]

            # Check for inconsistent disabled/hidden patterns
            if disabled_elements and hidden_elements:
                findings.append({
                    "id": f"permission-inconsistent-{url}",
                    "title": "Mixed permission handling patterns",
                    "category": "Permission/Role-Based UI Consistency",
                    "severity": "medium",
                    "location": {"route": url},
                    "description": f"Found {len(disabled_elements)} disabled and {len(hidden_elements)} hidden elements - inconsistent pattern",
                    "recommended_fix": "Standardize on either disabled (grayed out) or hidden for restricted features",
                    "effort": "small",
                })
        return findings

    def _check_theming_consistency(self, data: Dict, codebase=None) -> List[Dict]:
        """Check theming/dark mode consistency."""
        findings = []
        styles = data.get("computed_styles", {})

        css_files = styles.get("css_files", {})
        has_dark_mode = any("@media (prefers-color-scheme: dark)" in c or "dark" in f.lower()
                          for f, c in css_files.items())

        if not has_dark_mode and css_files:
            # Check for theme files
            theme_files = [f for f in css_files.keys() if "theme" in f.lower() or "dark" in f.lower()]
            if not theme_files:
                findings.append({
                    "id": "no-dark-mode",
                    "title": "No dark mode implementation detected",
                    "category": "Theming Consistency (Dark Mode)",
                    "severity": "low",
                    "description": "No dark mode styles or theme files found in the codebase",
                    "recommended_fix": "Consider adding dark mode support with a theme system",
                    "effort": "large",
                })

        return findings

    def _check_input_consistency(self, data: Dict, codebase=None) -> List[Dict]:
        """Check input affordance consistency."""
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        input_styles = defaultdict(list)
        for url, snapshot in dom_snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            for el in snapshot.get("elements", []):
                if el.get("tag") in ("input", "select", "textarea"):
                    styles = el.get("computed_styles", {})
                    key = self._style_signature(styles, ["border", "border-radius", "padding"])
                    input_styles[key].append({"url": url, "element": el})

        if len(input_styles) > 1:
            dominant = max(input_styles.values(), key=len)
            for sig, instances in input_styles.items():
                if instances != dominant and len(instances) < len(dominant):
                    findings.append({
                        "id": f"input-inconsistent-{sig[:20]}",
                        "title": "Input styling inconsistency",
                        "category": "Input Affordance Consistency",
                        "severity": "low",
                        "location": {"route": instances[0]["url"]},
                        "description": f"Found {len(instances)} inputs with non-standard styling",
                        "recommended_fix": "Standardize input styles across all forms",
                        "effort": "small",
                    })
        return findings

    def _check_print_consistency(self, data: Dict, codebase=None) -> List[Dict]:
        """Check print/export/PDF view consistency."""
        findings = []
        styles = data.get("computed_styles", {})

        css_files = styles.get("css_files", {})
        has_print_styles = any("@media print" in c for c in css_files.values())

        if not has_print_styles and css_files:
            findings.append({
                "id": "no-print-styles",
                "title": "No print media styles detected",
                "category": "Print/Export/PDF View Consistency",
                "severity": "low",
                "description": "No @media print styles found in the codebase",
                "recommended_fix": "Add print stylesheets for any printable views (invoices, reports, etc.)",
                "effort": "small",
            })

        return findings

    def _style_signature(self, styles: Dict, properties: list) -> str:
        """Create a signature string from style properties for comparison."""
        values = []
        for prop in properties:
            values.append(str(styles.get(prop, "unset")))
        return "|".join(values)
