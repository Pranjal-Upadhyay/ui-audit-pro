#!/usr/bin/env python3
"""
Consistency Checker — Runs UI/UX consistency checks against captured data.

Implements all 23 consistency categories from the audit spec.
"""

import re
from typing import Dict, List, Optional
from collections import defaultdict

# --- AI-slop lexicons (Phase 4) -------------------------------------------
# Kept module-level so they're easy to extend and unit-test in isolation.

# Generic LLM marketing/filler phrases. Curated to favour precision — each is a
# phrase a human copywriter would rarely ship verbatim.
AI_CLICHE_PHRASES = [
    "supercharge your", "seamless integration", "elevate your",
    "unlock the power", "unlock the full potential", "game-changer",
    "tapestry of", "paradigm shift", "cutting-edge solution",
    "revolutionize your", "take your", "to the next level",
    "in today's fast-paced world", "in the world of", "look no further",
    "harness the power", "whether you're", "designed to help you",
    "effortlessly", "with just a few clicks", "the possibilities are endless",
    "say goodbye to", "empower your", "at your fingertips",
    "delve into", "navigating the", "it's important to note",
    "when it comes to", "best-in-class", "one-stop shop",
    "robust and scalable", "streamline your workflow",
]

# Decorative emoji that LLMs pepper through headings and bullet lists. Plain
# functional emoji (✓, ✗) are intentionally excluded.
DECORATIVE_EMOJI = ["✨", "🚀", "🔥", "💡", "🎯", "⚡", "🌟", "🎉", "👉", "💪",
                    "🙌", "🤖", "📈", "💯", "🔑", "🎨", "🧠", "⭐"]

# Placeholder / lorem content that signals an unfinished, un-personalised build.
PLACEHOLDER_MARKERS = [
    "lorem ipsum", "dolor sit amet", "john doe", "jane doe",
    "example@example.com", "your company", "company name",
    "your product", "product name", "your brand", "brand name",
    "feature one", "feature two", "feature three", "lorem",
    "placeholder text", "insert text here", "your text here",
]

# Interchangeable CTA labels. A page leaning on several of these has no
# distinct voice — a hallmark of template output.
GENERIC_CTA_LABELS = [
    "get started", "learn more", "sign up free", "try it free",
    "try it now", "start free trial", "get started for free",
    "start now", "join now", "get started today", "explore now",
]


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

        Works in two modes:
        - Layer 1 (live URL): reads from dom_snapshots with computed styles.
        - Layer 2 (code-only): parses inline_styles from StyleAnalyzer output,
          building pseudo-elements grouped by source file (route proxy).
        """
        findings = []
        dom_snapshots = data.get("dom_snapshots", {})

        # Collect all interactive elements with their semantic role
        role_groups = defaultdict(list)

        # --- Layer 1: Live DOM snapshots ---
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

                semantic_role = f"{tag}:{text}"
                if tag in ("button", "a"):
                    style_sig = self._style_signature(styles_dict, [
                        "background-color", "border-radius", "padding",
                        "font-size", "font-weight", "color",
                    ])
                else:
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

        # --- Layer 2: Code-only fallback — parse inline style objects ---
        if not dom_snapshots:
            inline_styles = data.get("computed_styles", {}).get("inline_styles", [])
            for entry in inline_styles:
                file_path = entry.get("file", "source")
                raw_style = entry.get("style", "")

                # Extract key: value pairs from React inline style strings
                parsed = self._parse_inline_style_string(raw_style)

                # Heuristic: classify as button if it has button-like markers (cursor: pointer, or font-weight + padding + bg/color)
                # and filter out full-screen modal overlays or alert banner container boxes
                bg_val = str(parsed.get("backgroundColor", parsed.get("background", "")))
                is_overlay = "rgba(0,0,0" in bg_val or "fixed" in str(parsed.get("position", "")) or "fixed" in raw_style
                is_button_like = ("cursor" in parsed or ("padding" in parsed and "fontWeight" in parsed and ("backgroundColor" in parsed or "color" in parsed))) and not is_overlay

                if is_button_like:
                    # Normalise camelCase -> kebab-case for signature
                    normalized = {
                        "background-color": parsed.get("backgroundColor", parsed.get("background", "")),
                        "border-radius": parsed.get("borderRadius", ""),
                        "padding": parsed.get("padding", ""),
                        "font-size": parsed.get("fontSize", ""),
                        "font-weight": str(parsed.get("fontWeight", "")),
                        "color": parsed.get("color", ""),
                    }
                    style_sig = self._style_signature(normalized, list(normalized.keys()))
                    # Use file as a proxy for "route"
                    route_proxy = file_path
                    semantic_role = "button:primary-cta"
                    role_groups[semantic_role].append({
                        "url": route_proxy,
                        "element": {"tag": "button", "text": "primary-cta"},
                        "style_sig": style_sig,
                        "tag": "button",
                        "text": "primary-cta",
                        "raw_style": raw_style,
                    })

        # For each semantic role, check if all instances share the same style
        for role, instances in role_groups.items():
            if len(instances) < 2:
                continue

            sig_groups = defaultdict(list)
            for inst in instances:
                sig_groups[inst["style_sig"]].append(inst)

            if len(sig_groups) > 1:
                dominant_sig = max(sig_groups.keys(), key=lambda s: len(sig_groups[s]))
                dominant_count = len(sig_groups[dominant_sig])

                for sig, variant_instances in sig_groups.items():
                    if sig == dominant_sig:
                        continue

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
        """Check spacing follows a consistent grid.

        Works in two modes:
        - CSS files: regex over raw CSS for margin/padding px values.
        - Inline styles (code-only): parses React inline style objects from
          StyleAnalyzer's inline_styles list, extracting numeric padding/margin.
        """
        findings = []
        styles = data.get("computed_styles", {})
        non_grid_values = set()

        # --- CSS file analysis ---
        css_files = styles.get("css_files", {})
        for file_path, content in css_files.items():
            for match in re.finditer(
                r"(?:margin|padding)(?:-(?:top|right|bottom|left))?:\s*([\d.]+)px",
                content,
            ):
                value = float(match.group(1))
                if value % 4 != 0:
                    non_grid_values.add(value)

        # --- Inline styles analysis (code-only mode) ---
        inline_styles = styles.get("inline_styles", [])
        for entry in inline_styles:
            raw = entry.get("style", "")
            parsed = self._parse_inline_style_string(raw)
            for prop in ("padding", "margin", "paddingTop", "paddingRight",
                          "paddingBottom", "paddingLeft", "marginTop",
                          "marginRight", "marginBottom", "marginLeft"):
                val = parsed.get(prop, "")
                if val is None:
                    continue
                val_str = str(val).strip()
                # Handle shorthand strings like '13px 17px'
                for part in val_str.replace("'", "").replace('"', "").split():
                    part = part.rstrip(",")
                    if part.endswith("px"):
                        try:
                            num = float(part[:-2])
                            if num % 4 != 0:
                                non_grid_values.add(num)
                        except ValueError:
                            pass
                    elif isinstance(val, (int, float)):
                        # Numeric values (React uses unitless px by convention)
                        try:
                            num = float(val)
                            if num > 0 and num % 4 != 0:
                                non_grid_values.add(num)
                        except (ValueError, TypeError):
                            pass

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
        """Check typography follows a consistent scale.

        Works in two modes:
        - CSS files: regex over raw CSS for font-size declarations.
        - Inline styles (code-only): parses fontSize from React inline style objects.
        """
        findings = []
        styles = data.get("computed_styles", {})
        font_sizes = set()

        # --- CSS file analysis ---
        css_files = styles.get("css_files", {})
        for file_path, content in css_files.items():
            for match in re.finditer(r"font-size:\s*([\d.]+)(?:px|rem|em)", content):
                try:
                    value = float(match.group(1))
                    if "rem" in match.group(0) or "em" in match.group(0):
                        value *= 16
                    font_sizes.add(value)
                except ValueError:
                    continue

        # --- Inline styles analysis (code-only mode) ---
        inline_styles = styles.get("inline_styles", [])
        for entry in inline_styles:
            raw = entry.get("style", "")
            parsed = self._parse_inline_style_string(raw)
            fs = parsed.get("fontSize", "")
            if fs:
                fs_str = str(fs).strip().rstrip(",").replace("'", "").replace('"', "")
                if fs_str.endswith("px"):
                    try:
                        font_sizes.add(float(fs_str[:-2]))
                    except ValueError:
                        pass
                elif isinstance(fs, (int, float)):
                    font_sizes.add(float(fs))

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
                    # Elements often have no id (id == ''), so build a stable,
                    # unique signature from route + tag + text to avoid every
                    # finding colliding on the same key (which would let
                    # baseline-diffing silently collapse them into one).
                    ident = el.get("id") or el.get("text", "") or "anon"
                    sig = self._slug(f"{url}-{tag}-{ident}")
                    findings.append({
                        "id": f"missing-hover-{sig}",
                        "title": "Interactive element missing hover state",
                        "category": "Interaction State Consistency",
                        "severity": "low",
                        "location": {"route": url, "component": tag, "element": ident},
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
                # axe-core supplies a mapped `severity` and precise impact;
                # the legacy heuristic path only sets impact=='critical'.
                severity = issue.get("severity")
                if not severity:
                    severity = "high" if issue.get("impact") == "critical" else "medium"
                element = issue.get("element", "unknown")
                rule = issue.get("type", "unknown")
                evidence = issue.get("evidence", "")
                help_url = issue.get("help_url")
                if help_url:
                    evidence = f"{evidence}\nRule: {rule} — {help_url}".strip()
                findings.append({
                    "id": f"a11y-{rule}-{self._slug(url + '-' + str(element))}",
                    "title": issue.get("title", "Accessibility issue"),
                    "category": "Accessibility as Consistency Signal",
                    "severity": severity,
                    "location": {"route": url, "element": element},
                    "description": issue.get("description", ""),
                    "evidence": evidence,
                    "recommended_fix": issue.get("fix", "Fix accessibility issue"),
                    "effort": issue.get("effort", "small"),
                })

        return findings

    def _check_animation_consistency(self, data: Dict, codebase=None) -> List[Dict]:
        """Check motion/animation consistency."""
        findings = []
        styles = data.get("computed_styles", {})

        style_text = styles.get("all_style_text", "")
        transition_durations = set()

        for match in re.finditer(
            r"(?:transition-duration|animation-duration|transition|animation)\s*:[^;{}]*?"
            r"([\d.]+)(ms|s)\b",
            style_text,
        ):
            try:
                value = float(match.group(1))
            except ValueError:
                continue
            if match.group(2) == "s":
                value *= 1000
            transition_durations.add(value)

        # Tailwind duration utilities (duration-150 == 150ms)
        for cls in styles.get("tailwind_classes", {}):
            m = re.fullmatch(r"duration-(\d+)", cls)
            if m:
                transition_durations.add(float(m.group(1)))

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
                    "id": f"layout-{issue.get('type', 'unknown')}-{self._slug(url + '-' + str(issue.get('element', '')))}",
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
        style_text = styles.get("all_style_text", "")
        modifiers = styles.get("tailwind_modifiers", [])

        if not self._has_source_styles(styles):
            return findings

        has_dark_mode = (
            "prefers-color-scheme: dark" in style_text
            or "dark" in modifiers
            or any("theme" in f.lower() or "dark" in f.lower() for f in css_files)
        )

        if not has_dark_mode:
            findings.append({
                "id": "no-dark-mode",
                "title": "No dark mode implementation detected",
                "category": "Theming Consistency (Dark Mode)",
                "severity": "low",
                "description": "No dark mode styles, `dark:` variants, or theme files found in the codebase",
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

        has_print_styles = (
            "@media print" in styles.get("all_style_text", "")
            or "print" in styles.get("tailwind_modifiers", [])
        )

        if not has_print_styles and self._has_source_styles(styles):
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

    def _check_ai_design_tropes(self, data: Dict, codebase=None) -> List[Dict]:
        """Check for common AI design tropes and brand originality markers (Category 24).

        Flags uncustomized AI starter defaults:
        - Default indigo/slate color palettes (#6366f1 / indigo-500)
        - Font monoculture (100% Inter/Geist without brand headline pairing)
        - AI marketing copy clichés ("supercharge your workflow", "seamless integration", etc.)
        - Excessive em-dashes (—) in UI copy
        - Decorative emoji overuse (✨🚀🔥…) in headings/copy
        - Placeholder / lorem content still shipped in the UI
        - Interchangeable generic CTA labels ("Get Started"/"Learn More")
        - Overuse of radial blur overlays, glassmorphism, cliché gradients, and
          "Introducing/Powered by AI" hero pill badges
        """
        findings = []
        styles = data.get("computed_styles", {})
        dom_snapshots = data.get("dom_snapshots", {})
        ai_tropes = styles.get("ai_tropes", {})

        # 1. Uncustomized Palette Check (Indigo-500 / Slate defaults)
        colors = set([str(c).lower() for c in styles.get("colors", [])])
        ai_default_accents = {"#6366f1", "#8b5cf6", "#4f46e5", "#3b82f6", "rgb(99, 102, 241)", "rgba(99, 102, 241)"}
        ai_default_surfaces = {"#0f172a", "#090d16", "#020617", "#1e293b"}

        accent_matches = colors & ai_default_accents
        surface_matches = colors & ai_default_surfaces

        if accent_matches and surface_matches:
            findings.append({
                "id": "ai-trope-default-palette",
                "title": "Uncustomized AI default color palette detected",
                "category": "AI Design Tropes & Brand Originality",
                "severity": "medium",
                "description": f"Found default AI template colors: accents {accent_matches}, dark slate surfaces {surface_matches}. Overuse of standard indigo-500/slate causes visual homogenization across AI-generated sites.",
                "evidence": f"Accent colors: {list(accent_matches)}, Slate surfaces: {list(surface_matches)}",
                "recommended_fix": "Define custom brand CSS variables for primary/secondary colors rather than relying on default Tailwind indigo/slate tokens.",
                "effort": "small",
            })

        # 2. Font Monoculture Check (100% Inter/Geist with no custom header pairing)
        font_families = set([str(f).lower() for f in styles.get("font_families", [])])
        is_default_font = any("inter" in f or "geist" in f or "system-ui" in f for f in font_families)
        if font_families and is_default_font and len(font_families) == 1:
            findings.append({
                "id": "ai-trope-font-monoculture",
                "title": "Generic font monoculture (Inter/Geist system default)",
                "category": "AI Design Tropes & Brand Originality",
                "severity": "low",
                "description": "The entire UI uses a single default font family without a distinct brand heading font.",
                "evidence": f"Font families found: {list(font_families)}",
                "recommended_fix": "Pair body sans-serif text with a distinct display font for H1/H2 headlines.",
                "effort": "small",
            })

        # 3. Text-level AI slop — clichés, em-dashes, decorative emoji,
        #    placeholder/lorem content, interchangeable CTAs. Scanned in one
        #    pass over rendered text (preferred) or source text (fallback).
        text_samples = []
        for url, snapshot in dom_snapshots.items():
            if isinstance(snapshot, dict):
                for el in snapshot.get("text_elements", []):
                    txt = el.get("text", "")
                    if txt:
                        text_samples.append(txt)

        # Also scan inline text in codebase if provided
        if codebase and not text_samples:
            for ext in [".tsx", ".jsx", ".ts", ".js", ".html"]:
                for f in codebase.rglob(f"*{ext}"):
                    if ".git" in str(f) or "node_modules" in str(f) or ".next" in str(f):
                        continue
                    try:
                        c = f.read_text(encoding="utf-8")
                        text_samples.append(c)
                    except (UnicodeDecodeError, OSError):
                        continue

        slop = self._scan_text_slop(text_samples)

        if slop["cliches"]:
            unique_cliches = sorted(set(slop["cliches"]))
            findings.append({
                "id": "ai-trope-microcopy-cliches",
                "title": "AI copywriting clichés detected in UI text",
                "category": "AI Design Tropes & Brand Originality",
                "severity": "low",
                "description": f"Found {len(slop['cliches'])} instance(s) of generic AI marketing copy: {unique_cliches}",
                "evidence": f"Clichés found: {unique_cliches}",
                "recommended_fix": "Rewrite headline microcopy to focus on specific user outcomes rather than generic AI marketing buzzwords.",
                "effort": "trivial",
            })

        if slop["em_dashes"] > 5:
            findings.append({
                "id": "ai-trope-em-dash-overuse",
                "title": "Excessive em-dash (—) usage in UI text",
                "category": "AI Design Tropes & Brand Originality",
                "severity": "low",
                "description": f"Found {slop['em_dashes']} em-dashes across UI microcopy, a common hallmark of raw LLM text generation.",
                "evidence": f"Em-dash count: {slop['em_dashes']}",
                "recommended_fix": "Vary sentence structure and split compound sentences to sound more natural.",
                "effort": "trivial",
            })

        if slop["emoji"] > 4:
            emoji_list = sorted(set(slop["emoji_chars"]))
            findings.append({
                "id": "ai-trope-emoji-decoration",
                "title": "Decorative emoji overuse in UI copy",
                "category": "AI Design Tropes & Brand Originality",
                "severity": "low",
                "description": f"Found {slop['emoji']} decorative emoji ({''.join(emoji_list)}) sprinkled through headings/copy — a common LLM output signature.",
                "evidence": f"Decorative emoji: {''.join(emoji_list)} (count {slop['emoji']})",
                "recommended_fix": "Reserve emoji for genuine functional cues; strip decorative sparkles/rockets from headings and body copy.",
                "effort": "trivial",
            })

        if slop["placeholders"]:
            unique_ph = sorted(set(slop["placeholders"]))
            findings.append({
                "id": "ai-trope-placeholder-content",
                "title": "Placeholder / lorem content shipped in UI",
                "category": "AI Design Tropes & Brand Originality",
                "severity": "medium",
                "description": f"Found un-personalised placeholder content still in the UI: {unique_ph}. This signals an unfinished, generic build.",
                "evidence": f"Placeholders found: {unique_ph}",
                "recommended_fix": "Replace lorem ipsum and template names/emails with real brand-specific content before shipping.",
                "effort": "small",
            })

        if len(set(slop["ctas"])) >= 3:
            unique_ctas = sorted(set(slop["ctas"]))
            findings.append({
                "id": "ai-trope-generic-cta",
                "title": "Interchangeable generic CTA labels",
                "category": "AI Design Tropes & Brand Originality",
                "severity": "low",
                "description": f"The UI leans on {len(unique_ctas)} generic, voiceless CTA labels: {unique_ctas}. Distinct products use action-specific verbs.",
                "evidence": f"Generic CTAs: {unique_ctas}",
                "recommended_fix": "Rewrite CTAs to name the specific action ('Start your 14-day trial', 'See pricing') instead of boilerplate 'Get Started'/'Learn More'.",
                "effort": "trivial",
            })

        # 4. Overused Visual Tropes (Blur Overlays, Glassmorphism, gradients, pills)
        blur_overlays = ai_tropes.get("blur_overlays", [])
        glass_count = ai_tropes.get("glassmorphism_count", 0)
        ai_gradients = ai_tropes.get("ai_gradients", [])
        ai_pill_badges = ai_tropes.get("ai_pill_badges", [])

        if len(blur_overlays) > 2:
            findings.append({
                "id": "ai-trope-blur-overlays",
                "title": "Overuse of radial blur glow overlays (blur-3xl)",
                "category": "AI Design Tropes & Brand Originality",
                "severity": "low",
                "description": f"Found radial background blur overlays across {len(blur_overlays)} files: {blur_overlays[:5]}",
                "evidence": f"Affected files: {blur_overlays[:5]}",
                "recommended_fix": "Use purposeful lighting and contrast instead of decorative background glow blobs.",
                "effort": "small",
            })

        if glass_count > 5:
            findings.append({
                "id": "ai-trope-glassmorphism-overuse",
                "title": "Overuse of glassmorphism (backdrop-blur)",
                "category": "AI Design Tropes & Brand Originality",
                "severity": "low",
                "description": f"Found {glass_count} instances of backdrop-blur glass container cards.",
                "evidence": f"Glassmorphism instances: {glass_count}",
                "recommended_fix": "Use solid surface colors with subtle borders instead of applying glass blur to every card.",
                "effort": "small",
            })

        if len(ai_gradients) > 1:
            findings.append({
                "id": "ai-trope-gradient-overuse",
                "title": "Cliché purple/indigo/cyan gradient overuse",
                "category": "AI Design Tropes & Brand Originality",
                "severity": "low",
                "description": f"Found the signature purple→pink / indigo→cyan AI gradient across {len(ai_gradients)} files: {ai_gradients[:5]}",
                "evidence": f"Affected files: {ai_gradients[:5]}",
                "recommended_fix": "Derive gradients from your brand palette, or use flat brand colors, instead of the default indigo/violet/cyan template gradient.",
                "effort": "small",
            })

        if len(ai_pill_badges) > 0:
            findings.append({
                "id": "ai-trope-pill-badges",
                "title": "\"Introducing / Powered by AI\" pill badge cliché",
                "category": "AI Design Tropes & Brand Originality",
                "severity": "low",
                "description": f"Found the rounded-full 'Introducing…/✨ Powered by…/New' hero pill badge in {len(ai_pill_badges)} file(s): {ai_pill_badges[:5]}",
                "evidence": f"Affected files: {ai_pill_badges[:5]}",
                "recommended_fix": "Drop the decorative announcement pill above the hero headline, or replace it with a specific, dated announcement.",
                "effort": "trivial",
            })

        return findings

    @staticmethod
    def _scan_text_slop(text_samples: List[str]) -> Dict:
        """Scan raw UI/source text for AI-slop signals (browser-free, testable).

        Returns counts/lists for clichés, em-dashes, decorative emoji,
        placeholder content, and generic CTA labels.
        """
        result = {
            "cliches": [], "em_dashes": 0, "emoji": 0, "emoji_chars": [],
            "placeholders": [], "ctas": [],
        }
        for txt in text_samples:
            if not txt:
                continue
            result["em_dashes"] += txt.count("—")
            lower = txt.lower()
            for phrase in AI_CLICHE_PHRASES:
                if phrase in lower:
                    result["cliches"].append(phrase)
            for ch in DECORATIVE_EMOJI:
                n = txt.count(ch)
                if n:
                    result["emoji"] += n
                    result["emoji_chars"].append(ch)
            for marker in PLACEHOLDER_MARKERS:
                if marker in lower:
                    result["placeholders"].append(marker)
            # CTAs: only count a short standalone label as a CTA, so body prose
            # containing the words doesn't produce false positives.
            stripped = lower.strip().strip(".!→>»")
            if len(stripped) <= 30:
                for cta in GENERIC_CTA_LABELS:
                    if stripped == cta or stripped.startswith(cta):
                        result["ctas"].append(cta)
        return result

    @staticmethod
    def _slug(text: str, maxlen: int = 60) -> str:
        """Deterministic, filesystem/id-safe slug from arbitrary element text."""
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", str(text)).strip("-").lower()
        return cleaned[:maxlen] or "anon"

    @staticmethod
    def _has_source_styles(styles: Dict) -> bool:
        """True if any styling was found in source, regardless of authoring method.

        Absence-of-feature checks must gate on this rather than on `css_files`,
        which is empty for Tailwind-only and inline-style codebases.
        """
        return bool(
            styles.get("all_style_text")
            or styles.get("tailwind_classes")
            or styles.get("inline_styles")
        )

    def _style_signature(self, styles: Dict, properties: list) -> str:
        """Create a signature string from style properties for comparison."""
        values = []
        for prop in properties:
            values.append(str(styles.get(prop, "unset")))
        return "|".join(values)

    def _parse_inline_style_string(self, raw: str) -> Dict:
        """Parse a React inline style string into a key->value dict.

        Handles patterns like:
          "backgroundColor: '#0070f3', borderRadius: '6px', padding: '13px 17px'"
          "padding: 24"
        Returns a dict of camelCase property names to string values.
        """
        result = {}
        if not raw:
            return result
        # Match key: value pairs (value may be quoted string or bare number)
        for match in re.finditer(
            r"(\w+)\s*:\s*(?:'([^']*)'|\"([^\"]*)\"|([-\d.]+))",
            raw,
        ):
            key = match.group(1)
            # Pick whichever capture group matched
            value = match.group(2) or match.group(3) or match.group(4) or ""
            if match.group(4):  # bare number
                try:
                    result[key] = float(match.group(4))
                except ValueError:
                    result[key] = value
            else:
                result[key] = value
        return result
