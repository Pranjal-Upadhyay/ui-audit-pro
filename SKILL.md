---
name: ui-audit-pro
description: "Full-stack UI/UX consistency and frontend-backend integration audit. Two-layer architecture: Layer 1 (browser-level, framework-agnostic) + Layer 2 (source-level, pluggable adapters). Auto-detects stack. 23 visual/behavioral categories + 13 integration checks. Generates severity-ranked reports with evidence."
---

# UI Audit Pro — Consistency & Integration Audit Skill

Two-layer audit skill that performs full UI/UX visual/behavioral consistency checks and frontend-to-backend communication integrity validation across any web application.

## Architecture: Two-Layer Design

### Layer 1: Runtime/Browser-Level Checks (Framework-Agnostic)
Everything involving **rendered output** — screenshots, computed styles, DOM structure, network requests/responses, interaction behavior — is done via browser automation (Playwright) against the actual running app. This layer does NOT need to know whether the app is React, Next.js, Vue, Svelte, or raw HTML. It covers:
- All 23 UI/UX consistency categories
- All 13 frontend-backend integration checks (network layer)
- **Works with zero source code** — can audit a live URL only

### Layer 2: Source-Code-Level Checks (Framework-Aware, Pluggable Adapters)
Everything involving **reading the codebase directly** — finding exact file/line locations, tracing API call sites, validating type contracts, understanding routing — uses pluggable adapters that are **auto-detected**. Each adapter implements the same interface:
- `list_routes()` — enumerate pages/screens
- `find_api_call_sites()` — find where frontend calls backend
- `find_component_definitions()` — map DOM to source files
- `get_type_contracts()` — find TypeScript interfaces, PropTypes, OpenAPI specs

**Supported Adapters:**
| Adapter | Framework |
|---------|-----------|
| `nextjs` | Next.js (App Router + Pages Router) |
| `react` | React (CRA, Vite, etc.) |
| `vue` | Vue.js |
| `static-html` | Vanilla HTML/CSS/JS |
| `node-express` | Node.js/Express backend |

## When to Apply

Use this skill when:
- Auditing a web app for visual/behavioral consistency before a release
- Reviewing PRs for frontend-backend integration regressions
- Performing a quality audit on a live/staging deployment
- Checking a codebase for design system drift
- Validating API contract adherence between frontend and backend
- Running automated accessibility + consistency checks

## Operating Modes

| Mode | Requirements | What It Does |
|------|-------------|--------------|
| **Live-only** | Running URL | Browser-level checks only (Layer 1) — full audit with no source code |
| **Code-only** | Source code | Source-level checks only (Layer 2) — adapter-based analysis |
| **Combined (preferred)** | Both | Layer 1 detects visual/behavioral issues; Layer 2 pinpoints file/line locations |

## How to Use

### Step 1: Determine Audit Scope

Ask the user (or infer from context):
1. **Codebase path** — where is the source code? (optional)
2. **Live URL** — is there a running instance? (optional but recommended)
3. **Audit depth** — full audit or focused on specific categories?
4. **Previous report** — prior audit report to diff against?

### Step 2: Auto-Detect Stack (if source code provided)

```bash
python3 skills/ui-audit-pro/scripts/audit.py detect --codebase <path>
```

This inspects `package.json`, config files, and directory structure to determine:
- Frontend framework (Next.js, React, Vue, Svelte, Angular, vanilla)
- Backend framework (Express, Fastify, Python, Go)
- Language (JavaScript, TypeScript, Python)
- Which adapters to load

### Step 3: Discovery Phase

Enumerate all routes/screens/components:

**From source code (Layer 2):**
- Adapters parse framework-specific routing config
- Extract API call sites and type contracts
- Map components to source files

**From live instance (Layer 1):**
- Crawl all internal links
- Capture full-page screenshots
- Intercept all network requests

```bash
python3 skills/ui-audit-pro/scripts/audit.py discover \
  --codebase <path> --url <live-url> --output <dir>
```

### Step 4: Capture Phase

For each discovered route:

**Browser-level (Layer 1):**
- Full-page screenshot
- DOM snapshot with computed styles for all interactive elements
- Network request/response log with timing and payload shapes
- Accessibility audit

**Source-level (Layer 2):**
- CSS/style definitions extracted
- Component props and state patterns
- API endpoint URLs and expected shapes

```bash
python3 skills/ui-audit-pro/scripts/audit.py capture \
  --codebase <path> --url <live-url> --output <dir>
```

### Step 5: Classify Phase

Group captured elements by **semantic role**:
- "Primary CTA button" / "Danger action button"
- "Data card" / "List pagination control"
- "Modal/dialog" / "Form input"
- "Loading skeleton" / "Error state display"

### Step 6: Audit Phase

Run all 36 checks (23 UI/UX + 13 integration):

```bash
python3 skills/ui-audit-pro/scripts/audit.py audit \
  --codebase <path> --url <live-url> --output <dir>
```

### Step 7: Generate Report

```bash
python3 skills/ui-audit-pro/scripts/audit.py report \
  --findings <findings-json> --output <dir> \
  --previous-report <optional-previous-report.md>
```

## Full Pipeline

```bash
python3 skills/ui-audit-pro/scripts/audit.py full \
  --codebase <path> --url <live-url> --output ./audit-output
```

## Folder Structure

```
skills/ui-audit-pro/
├── SKILL.md                          # This file
├── requirements.txt                  # Python dependencies
├── references/
│   ├── consistency-categories.md     # 23 UI/UX categories reference
│   └── backend-integration-checks.md # 13 integration checks reference
└── scripts/
    ├── audit.py                      # Main engine (two-layer orchestrator)
    ├── detect_stack.py               # Auto-detects framework stack
    ├── report_generator.py           # Generates structured audit reports
    ├── __init__.py
    ├── __main__.py
    ├── analyzers/                    # Check logic
    │   ├── consistency_checker.py    # 23 UI/UX consistency checks
    │   ├── integration_checker.py    # 13 integration checks
    │   └── ...
    ├── adapters/                     # Framework-specific source analysis
    │   ├── base.py                   # BaseAdapter interface
    │   ├── nextjs.py                 # Next.js adapter
    │   ├── react.py                  # React adapter
    │   ├── vue.py                    # Vue adapter
    │   ├── static_html.py            # Vanilla HTML/CSS/JS adapter
    │   └── node_express.py           # Node.js/Express backend adapter
    └── capture/                      # Browser-level data capture
        ├── screenshot_capture.py     # Playwright screenshot capture
        ├── network_interceptor.py    # Network traffic interception
        └── dom_extractor.py          # DOM snapshot extraction
```

## Graceful Degradation

| Scenario | Behavior |
|----------|----------|
| No source code, only live URL | Layer 1 runs fully; Layer 2 skipped; report notes "no source-level tracing" |
| Source code only, no live URL | Layer 2 runs fully; Layer 1 skipped; report notes "no browser verification" |
| Unknown framework | `static-html` adapter used as fallback; limited source tracing |
| No TypeScript | Type contract checks skipped gracefully |
| No adapters match | Full Layer 1 audit; report clearly states source tracing unavailable |

## Report Structure

Every audit produces a structured report with:
1. **Executive Summary** — total issues, severity breakdown, health narrative
2. **Findings by Severity** — Critical > High > Medium > Low, each with evidence
3. **Cross-Cutting Patterns** — root cause grouping
4. **Appendix** — routes scanned, tools used, areas not tested

## Audit Checklist

### UI/UX Categories (23)
- [ ] 1. Visual identity consistency
- [ ] 2. Spacing rhythm
- [ ] 3. Typography scale
- [ ] 4. Icon set consistency
- [ ] 5. Interaction state consistency
- [ ] 6. Modal/popup/overlay behavior
- [ ] 7. Loading/empty/error state consistency
- [ ] 8. Form validation consistency
- [ ] 9. Content/microcopy consistency
- [ ] 10. Structural/navigational consistency
- [ ] 11. Responsive/cross-breakpoint consistency
- [ ] 12. Accessibility as consistency signal
- [ ] 13. Motion/animation consistency
- [ ] 14. Layout integrity bugs
- [ ] 15. Data density/truncation consistency
- [ ] 16. Iconography/color semantics
- [ ] 17. Empty/zero/singular-plural correctness
- [ ] 18. Pagination/infinite-scroll consistency
- [ ] 19. Notification/toast consistency
- [ ] 20. Permission/role-based UI consistency
- [ ] 21. Theming consistency (dark mode)
- [ ] 22. Input affordance consistency
- [ ] 23. Print/export/PDF view consistency

### Integration Categories (13)
- [ ] 1. API contract/schema drift
- [ ] 2. Type mismatches
- [ ] 3. Loading/error/empty state wiring
- [ ] 4. Unhandled promise rejections
- [ ] 5. Race conditions/stale data
- [ ] 6. Optimistic UI correctness
- [ ] 7. Auth/session boundary handling
- [ ] 8. Latency/timeout behavior
- [ ] 9. Pagination/data consistency
- [ ] 10. Real-time/websocket sync
- [ ] 11. File upload/download edge cases
- [ ] 12. Idempotency/double-submit
- [ ] 13. Localization/timezone mismatches
