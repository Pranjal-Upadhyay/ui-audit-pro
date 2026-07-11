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

    def extract(self, url: str) -> Dict:
        """Extract DOM snapshot from a URL."""
        snapshot = self._extract_with_playwright(url)
        if snapshot:
            return snapshot

        # Fallback: empty snapshot
        return {"url": url, "elements": [], "interactive_elements": [], "modals": []}

    def _extract_with_playwright(self, url: str) -> Optional[Dict]:
        """Extract DOM using Playwright."""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.goto(url, wait_until="networkidle", timeout=30000)

                # Extract interactive elements with computed styles
                elements = page.evaluate("""() => {
                    const results = [];
                    const interactiveSelectors = 'button, a, input, select, textarea, [role="button"], [onclick], [tabindex]';

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
                            },
                            has_hover_style: false,
                            has_focus_style: false,
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

                browser.close()

                snapshot = {
                    "url": url,
                    "elements": elements,
                    "interactive_elements": elements,
                    "modals": modals,
                    "lists": lists,
                    "has_breadcrumb": has_breadcrumb,
                    "toasts": toasts,
                    "forms": forms,
                    "a11y_issues": a11y_issues,
                    "text_elements": text_elements,
                }

                # Save snapshot
                snapshot_path = self.output_dir / f"{self._url_to_filename(url)}.json"
                with open(snapshot_path, "w") as f:
                    json.dump(snapshot, f, indent=2)

                return snapshot

        except ImportError:
            return None
        except Exception as e:
            print(f"  Warning: DOM extraction failed for {url}: {e}")
            return None

    def _url_to_filename(self, url: str) -> str:
        """Convert URL to safe filename."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path.strip("/").replace("/", "_") or "index"
        return f"{parsed.netloc}_{path}"
