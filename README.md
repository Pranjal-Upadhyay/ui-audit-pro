# UI Audit Pro

> Full-stack UI/UX consistency and frontend-backend integration audit for any web application.

## What Is This?

UI Audit Pro is a two-layer audit engine that detects visual inconsistencies and integration bugs across your web application. It runs **36 automated checks** — 23 UI/UX consistency categories and 13 frontend-to-backend integration checks.

**Layer 1 (Browser-Level):** Runs against a live URL via Playwright. Framework-agnostic — works with any web app. Captures screenshots, DOM snapshots, computed styles, and network traffic.

**Layer 2 (Source-Level):** Reads your codebase directly using pluggable framework adapters. Pinpoints the exact file and line where issues originate. Auto-detects your stack.

### Supported Frameworks

| Layer | Frameworks |
|-------|-----------|
| Frontend | Next.js, React, Vue.js, Vanilla HTML/CSS/JS |
| Backend | Node.js/Express |
| Any | Works with just a live URL (no source code required) |

### What It Checks

**UI/UX Consistency (23 categories):** Visual identity, spacing rhythm, typography scale, icon consistency, interaction states, modal behavior, loading/empty/error states, form validation, microcopy, navigation, responsive breakpoints, accessibility, animation, layout integrity, truncation, color semantics, grammar correctness, pagination, notifications, role-based UI, dark mode, input affordance, print/PDF views.

**Integration (13 categories):** API contract drift, type mismatches, state wiring, unhandled promise rejections, race conditions, optimistic UI correctness, auth/session handling, latency/timeout behavior, pagination data, websocket sync, file upload/download edge cases, double-submit protection, timezone mismatches.

---

## Installation

### Prerequisites

- Python 3.10+
- Playwright (for browser-level checks on live URLs)

### Setup

```bash
# Clone the repo
git clone https://github.com/Pranjal-Upadhyay/ui-audit-pro.git
cd ui-audit-pro

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (needed for live URL audits)
playwright install chromium
```

---

## Usage

### As a CLI Tool

```bash
# Auto-detect your stack
python3 scripts/audit.py detect --codebase /path/to/your/app

# Run the full audit pipeline (stack detection → discovery → capture → checks → report)
python3 scripts/audit.py full --codebase /path/to/your/app --url http://localhost:3000 --output ./audit-output

# Run individual phases
python3 scripts/audit.py discover --codebase /path/to/your/app --output ./audit-output
python3 scripts/audit.py capture --codebase /path/to/your/app --url http://localhost:3000 --output ./audit-output
python3 scripts/audit.py audit --codebase /path/to/your/app --url http://localhost:3000 --output ./audit-output
python3 scripts/audit.py report --findings ./audit-output/findings.json --output ./audit-output
```

### Three Operating Modes

| Mode | Command | What Runs |
|------|---------|-----------|
| **Live-only** | `--url <url>` (no `--codebase`) | Layer 1 only — full UI audit with no source code |
| **Code-only** | `--codebase <path>` (no `--url`) | Layer 2 only — adapter-based source analysis |
| **Combined** | `--codebase <path> --url <url>` | Both layers — detects issues AND pinpoints source locations |

---

## Using as a Skill in Claude Code / Codex / Antigravity

UI Audit Pro is designed as an AI coding skill. It follows the standard `SKILL.md` format that AI assistants recognize.

### Option 1: Install via Skills CLI

```bash
npx skills add Pranjal-Upadhyay/ui-audit-pro --skill ui-audit-pro --yes
```

This installs the skill into `.agents/skills/ui-audit-pro/`. The AI assistant will automatically discover it.

### Option 2: Manual Installation

Copy the entire project into your agent's skills directory:

```bash
# For Claude Code (Freebuff)
cp -r ui-audit-pro .agents/skills/ui-audit-pro

# For other agents, place in their skills directory
# e.g., .codex/skills/ui-audit-pro/
```

### Option 3: Reference as MCP Server (Advanced)

For deeper integration, wrap the audit engine as an MCP server:

```json
{
  "mcpServers": {
    "ui-audit-pro": {
      "command": "python3",
      "args": ["scripts/audit.py"],
      "cwd": "/path/to/ui-audit-pro"
    }
  }
}
```

### How to Use in Your AI Assistant

Once installed, simply ask your AI assistant:

```
Audit this codebase for UI/UX consistency issues
Run a full integration audit against http://localhost:3000
Check for API contract drift between frontend and backend
```

The assistant will:
1. Load the `SKILL.md` to understand what UI Audit Pro does
2. Detect your stack automatically
3. Run the appropriate checks
4. Generate a severity-ranked report with evidence

---

## Output

Every audit produces a structured Markdown report:

```
audit-output/
├── stack.json           # Detected technology stack
├── discovery.json       # Routes, API calls, components found
├── capture.json         # Screenshots, DOM snapshots, network logs
├── findings.json        # All issues with severity and evidence
└── report.md            # Final human-readable report
```

### Report Structure

1. **Executive Summary** — total issues, severity breakdown, health score
2. **Findings by Severity** — Critical → High → Medium → Low, each with evidence and file locations
3. **Cross-Cutting Patterns** — root cause grouping
4. **Appendix** — routes scanned, tools used, areas not tested

---

## Project Structure

```
ui-audit-pro/
├── SKILL.md                          # AI skill definition
├── README.md
├── requirements.txt
├── references/
│   ├── consistency-categories.md     # 23 UI/UX categories
│   └── backend-integration-checks.md # 13 integration checks
└── scripts/
    ├── audit.py                      # Main engine
    ├── detect_stack.py               # Auto-detects framework
    ├── report_generator.py           # Generates reports
    ├── adapters/                     # Framework-specific analysis
    │   ├── base.py
    │   ├── nextjs.py
    │   ├── react.py
    │   ├── vue.py
    │   ├── static_html.py
    │   └── node_express.py
    ├── analyzers/                    # Check logic
    │   ├── consistency_checker.py
    │   ├── integration_checker.py
    │   ├── style_analyzer.py
    │   ├── component_analyzer.py
    │   └── api_analyzer.py
    └── capture/                      # Browser-level capture
        ├── screenshot_capture.py
        ├── network_interceptor.py
        └── dom_extractor.py
```

---

## Graceful Degradation

| Scenario | Behavior |
|----------|----------|
| No source code, only live URL | Layer 1 runs fully; report notes "no source-level tracing" |
| Source code only, no live URL | Layer 2 runs fully; report notes "no browser verification" |
| Unknown framework | `static-html` adapter as fallback |
| No TypeScript | Type contract checks skipped gracefully |

---

## License

MIT
