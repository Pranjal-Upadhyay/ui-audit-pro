#!/usr/bin/env python3
"""
DOM Extractor — Extracts DOM snapshots with computed styles.

Captures the full DOM tree, computed styles for interactive elements,
and identifies semantic roles.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional


class DOMExtractor:
    """Extracts DOM snapshots from a live instance."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # Minimum touch-target size per WCAG 2.5.5 / Apple HIG (px).
    MIN_TOUCH_TARGET = 44

    def extract(self, url: str, viewport: Optional[Dict] = None) -> Optional[Dict]:
        """Extract DOM snapshot from a URL at an optional viewport.

        Returns None if the page could not be loaded. Callers must treat None
        as a capture failure rather than as an empty page. When `viewport` is
        given (e.g. {"width": 375, "height": 812}) the snapshot is tagged with
        it so multi-viewport captures don't collide.
        """
        return self._extract_with_playwright(url, viewport)

    def _extract_with_playwright(self, url: str, viewport: Optional[Dict] = None) -> Optional[Dict]:
        """Extract DOM using Playwright."""
        viewport = viewport or {"width": 1440, "height": 900}
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport=viewport)
                page.goto(url, wait_until="networkidle", timeout=30000)

                # Extract interactive elements with computed styles
                elements = page.evaluate("""() => {
                    const results = [];
                    const interactiveSelectors = 'button, a, input, select, textarea, [role="button"], [onclick], [tabindex]';

                    // Collect selector text from all readable stylesheets that carry
                    // :hover / :focus rules, so we can tell whether an element has any.
                    const hoverSelectors = [];
                    const focusSelectors = [];
                    for (const sheet of document.styleSheets) {
                        let rules;
                        try { rules = sheet.cssRules; } catch (e) { continue; } // cross-origin
                        if (!rules) continue;
                        for (const rule of rules) {
                            if (!rule.selectorText) continue;
                            if (rule.selectorText.includes(':hover')) hoverSelectors.push(rule.selectorText);
                            if (rule.selectorText.includes(':focus')) focusSelectors.push(rule.selectorText);
                        }
                    }
                    const matchesAny = (el, selectors, pseudo) => selectors.some(sel => {
                        // Strip the pseudo-class then test the element against the base.
                        const base = sel.split(',').map(s => s.trim())
                            .filter(s => s.includes(pseudo))
                            .map(s => s.replace(new RegExp(pseudo + '[-\\\\w()]*', 'g'), '').trim())
                            .filter(Boolean);
                        return base.some(b => { try { return el.matches(b); } catch (e) { return false; } });
                    });

                    document.querySelectorAll(interactiveSelectors).forEach(el => {
                        const styles = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();

                        results.push({
                            tag: el.tagName.toLowerCase(),
                            text: el.textContent?.trim().substring(0, 100) || '',
                            id: el.id || '',
                            classes: el.className || '',
                            semantic_role: el.getAttribute('role') || el.tagName.toLowerCase(),
                            computed_styles: {
                                'background-color': styles.backgroundColor,
                                'color': styles.color,
                                'border': styles.border,
                                'border-radius': styles.borderRadius,
                                'padding': styles.padding,
                                'font-size': styles.fontSize,
                                'font-weight': styles.fontWeight,
                                'box-shadow': styles.boxShadow,
                                'outline': styles.outline,
                            },
                            has_hover_style: matchesAny(el, hoverSelectors, ':hover'),
                            has_focus_style: matchesAny(el, focusSelectors, ':focus'),
                            rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
                        });
                    });

                    return results;
                }""")

                # Check for modals
                modals = page.evaluate("""() => {
                    const results = [];
                    document.querySelectorAll('[role="dialog"], .modal, [aria-modal="true"]').forEach(el => {
                        const styles = window.getComputedStyle(el);
                        // Detect actual close behavior from event handlers and attributes
                        const hasEscapeHandler = el.getAttribute('data-close-on-escape') !== 'false' && 
                                                !el.getAttribute('data-disable-escape');
                        const hasBackdropClickHandler = el.getAttribute('data-close-on-backdrop') !== 'false' &&
                                                      !el.getAttribute('data-disable-backdrop-close');
                        
                        // Check for close buttons
                        const hasCloseButton = !!el.querySelector('[data-dismiss], [aria-label="Close"], .close, button[type="button"]');
                        
                        results.push({
                            tag: el.tagName.toLowerCase(),
                            id: el.id || '',
                            classes: el.className || '',
                            has_backdrop: !!el.closest('.modal-backdrop, [data-backdrop]'),
                            closes_on_escape: hasEscapeHandler,
                            closes_on_backdrop_click: hasBackdropClickHandler,
                            has_close_button: hasCloseButton,
                        });
                    });
                    return results;
                }""")

                # Check for lists/grids
                lists = page.evaluate("""() => {
                    const results = [];
                    document.querySelectorAll('table, [role="list"], [role="grid"], .list, .grid').forEach(el => {
                        results.push({
                            tag: el.tagName.toLowerCase(),
                            type: el.getAttribute('role') || 'list',
                            has_loading_state: !!el.querySelector('.skeleton, .loading, [aria-busy="true"]'),
                            has_empty_state: !!el.querySelector('.empty, .no-data, [role="status"]'),
                        });
                    });
                    return results;
                }""")

                # Check for breadcrumbs
                has_breadcrumb = bool(page.query_selector('nav[aria-label="breadcrumb"], .breadcrumb, [role="navigation"] ol'))

                # Check for toast notifications
                toasts = page.evaluate("""() => {
                    const results = [];
                    document.querySelectorAll('.toast, .notification, [role="alert"]').forEach(el => {
                        const styles = window.getComputedStyle(el);
                        results.push({
                            position: styles.position,
                            classes: el.className || '',
                        });
                    });
                    return results;
                }""")

                # Check for forms and validation
                forms = page.evaluate("""() => {
                    const results = [];
                    document.querySelectorAll('form').forEach(el => {
                        const inputs = el.querySelectorAll('input, select, textarea');
                        const has_validation = el.querySelector('.error, .invalid, [aria-invalid="true"], [class*="error"]');
                        results.push({
                            action: el.action || '',
                            method: el.method || 'GET',
                            input_count: inputs.length,
                            has_validation: !!has_validation,
                            validation_style: has_validation ? 'inline' : 'none',
                        });
                    });
                    return results;
                }""")

                # A11y issues
                a11y_issues = page.evaluate("""() => {
                    const issues = [];

                    // Check images without alt
                    document.querySelectorAll('img:not([alt])').forEach(el => {
                        issues.push({
                            type: 'missing-alt',
                            element: el.src || 'unknown',
                            title: 'Image missing alt text',
                            description: 'Image does not have an alt attribute',
                            impact: 'critical',
                            fix: 'Add descriptive alt text to the image',
                        });
                    });

                    // Check inputs without labels
                    document.querySelectorAll('input:not([type="hidden"]):not([aria-label]):not([aria-labelledby])').forEach(el => {
                        const hasLabel = document.querySelector(`label[for="${el.id}"]`);
                        if (!hasLabel && el.type !== 'submit' && el.type !== 'hidden') {
                            issues.push({
                                type: 'missing-label',
                                element: el.name || el.id || 'unknown',
                                title: 'Input missing associated label',
                                description: 'Form input does not have an associated label',
                                impact: 'critical',
                                fix: 'Add a <label> element with for attribute matching the input id',
                            });
                        }
                    });

                    // Check buttons without accessible names
                    document.querySelectorAll('button').forEach(el => {
                        if (!el.textContent?.trim() && !el.getAttribute('aria-label') && !el.getAttribute('aria-labelledby')) {
                            issues.push({
                                type: 'missing-button-name',
                                element: el.id || 'unknown',
                                title: 'Button missing accessible name',
                                description: 'Button has no text content or aria-label',
                                impact: 'critical',
                                fix: 'Add text content or aria-label to the button',
                            });
                        }
                    });

                    return issues;
                }""")

                # Text elements for grammar checks
                text_elements = page.evaluate("""() => {
                    const results = [];
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                    let node;
                    while (node = walker.nextNode()) {
                        const text = node.textContent?.trim();
                        if (text && text.length > 5 && text.length < 200) {
                            results.push({ text: text });
                        }
                    }
                    return results.slice(0, 200);
                }""")

                # Layout integrity issues measured from the real rendered box model.
                layout_issues = page.evaluate("""(minTouch) => {
                    const issues = [];
                    const vw = document.documentElement.clientWidth;
                    const vh = document.documentElement.clientHeight;

                    // 1. Horizontal page overflow (a top offender on mobile widths).
                    const docWidth = document.documentElement.scrollWidth;
                    if (docWidth > vw + 1) {
                        issues.push({
                            type: 'horizontal-overflow',
                            element: 'document',
                            severity: 'high',
                            description: `Page content is ${docWidth}px wide but the viewport is ${vw}px, causing horizontal scroll`,
                            fix: 'Find the overflowing element (often a fixed width or unwrapped text) and constrain it with max-width:100% or overflow control',
                        });
                    }

                    const describe = (el) => {
                        const id = el.id ? `#${el.id}` : '';
                        const cls = (typeof el.className === 'string' && el.className)
                            ? '.' + el.className.trim().split(/\\s+/).join('.') : '';
                        let sel = el.tagName.toLowerCase() + id + cls;
                        // Disambiguate otherwise-identical elements (e.g. bare <a>)
                        // by position, so per-element findings get unique ids.
                        if (!id && !cls) {
                            const r = el.getBoundingClientRect();
                            sel += `@${Math.round(r.left)},${Math.round(r.top)}`;
                        }
                        return sel;
                    };

                    const seenClip = new Set();
                    document.querySelectorAll('*').forEach(el => {
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) return;
                        const styles = window.getComputedStyle(el);

                        // 2. Content clipped by an overflow:hidden ancestor's box.
                        if (el.scrollWidth > el.clientWidth + 1 && styles.overflowX === 'hidden') {
                            const key = describe(el) + ':clipx';
                            if (!seenClip.has(key)) {
                                seenClip.add(key);
                                issues.push({
                                    type: 'content-clipped',
                                    element: describe(el),
                                    severity: 'medium',
                                    description: `Element content (${el.scrollWidth}px) is wider than its box (${el.clientWidth}px) with overflow-x:hidden, so text/children are clipped`,
                                    fix: 'Allow wrapping, reduce content, or make the container wider',
                                });
                            }
                        }

                        // 3. Touch targets smaller than the accessible minimum.
                        const interactive = el.matches('button, a, input, select, textarea, [role="button"], [onclick]');
                        if (interactive && rect.width > 0 && (rect.width < minTouch || rect.height < minTouch)) {
                            issues.push({
                                type: 'touch-target-too-small',
                                element: describe(el),
                                severity: 'medium',
                                description: `Interactive target is ${Math.round(rect.width)}x${Math.round(rect.height)}px, below the ${minTouch}px minimum`,
                                fix: `Increase the tappable area to at least ${minTouch}x${minTouch}px`,
                            });
                        }

                        // 4. Element rendered partly or wholly off the left/top edge.
                        if (rect.right < 0 || rect.bottom < 0 || rect.left > vw) {
                            issues.push({
                                type: 'off-viewport',
                                element: describe(el),
                                severity: 'low',
                                description: `Element is positioned outside the viewport (left=${Math.round(rect.left)}, top=${Math.round(rect.top)})`,
                                fix: 'Check for stray absolute/negative positioning or an unclosed off-canvas panel',
                            });
                        }
                    });

                    return issues.slice(0, 100);
                }""", self.MIN_TOUCH_TARGET)

                browser.close()

                snapshot = {
                    "url": url,
                    "viewport": viewport,
                    "elements": elements,
                    "interactive_elements": elements,
                    "modals": modals,
                    "lists": lists,
                    "has_breadcrumb": has_breadcrumb,
                    "toasts": toasts,
                    "forms": forms,
                    "a11y_issues": a11y_issues,
                    "layout_issues": layout_issues,
                    "text_elements": text_elements,
                }

                # Save snapshot (viewport-tagged so multi-viewport captures don't collide)
                suffix = f"_{viewport['width']}x{viewport['height']}"
                snapshot_path = self.output_dir / f"{self._url_to_filename(url)}{suffix}.json"
                with open(snapshot_path, "w") as f:
                    json.dump(snapshot, f, indent=2)

                return snapshot

        except ImportError as e:
            from . import PLAYWRIGHT_MISSING_MSG, BrowserUnavailableError
            raise BrowserUnavailableError(PLAYWRIGHT_MISSING_MSG) from e
        except Exception as e:
            print(f"  ERROR: DOM extraction failed for {url}: {e}")
            return None

    def _url_to_filename(self, url: str) -> str:
        """Convert URL to safe filename."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path.strip("/").replace("/", "_") or "index"
        return f"{parsed.netloc}_{path}"
