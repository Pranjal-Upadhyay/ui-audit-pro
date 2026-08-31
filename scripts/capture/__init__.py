# Capture package

PLAYWRIGHT_MISSING_MSG = (
    "Playwright is required for browser-level (Layer 1) checks but is not available.\n"
    "  Install it with:\n"
    "    pip install playwright\n"
    "    playwright install chromium\n"
    "  Or omit --url to run source-only (Layer 2) analysis."
)


class BrowserUnavailableError(RuntimeError):
    """Raised when browser automation is required but cannot be started."""


def ensure_playwright():
    """Verify Playwright is importable and its browser binary is installed.

    Layer 1 previously degraded silently to empty snapshots, which made the
    report claim a clean bill of health for an app it had never loaded.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise BrowserUnavailableError(PLAYWRIGHT_MISSING_MSG) from e

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
    except Exception as e:
        raise BrowserUnavailableError(
            f"Playwright is installed but Chromium could not be launched: {e}\n"
            "  Try: playwright install chromium"
        ) from e
