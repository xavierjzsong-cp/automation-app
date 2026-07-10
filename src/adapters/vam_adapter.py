"""VAM adapter interface."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from src.adapters.base_adapter import BaseAdapter


logger = logging.getLogger(__name__)


class VamAdapter(BaseAdapter):
    """Validate VAM mapped data and own the VAM browser session."""

    COOKIE_BUTTON_TEXTS = (
        "Accept",
        "Accept All",
        "I Accept",
        "Allow all",
        "Got it",
        "Agree",
        "Continue",
    )

    REQUIRED_CONNECTION_FIELDS = {
        "name",
        "od",
        "weight",
        "material_family",
        "yield_strength",
        "type",
    }

    def __init__(
        self,
        base_url: str,
        configurator_url: str,
        logs_dir: str | Path,
        headless: bool = False,
        slow_mo: int = 300,
        timeout_ms: int = 10000,
        playwright_factory: Callable[[], Any] = sync_playwright,
    ) -> None:
        self.base_url = base_url
        self.configurator_url = configurator_url
        self.logs_dir = Path(logs_dir)
        self.headless = headless
        self.slow_mo = slow_mo
        self.timeout_ms = timeout_ms

        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._closed = False

        self._start_browser(playwright_factory)

    def run(self, mapped_data: dict[str, Any]) -> dict[str, Any]:
        """Validate mapped data and open the VAM configurator."""
        self._validate_mapped_data(mapped_data)
        self.open_configurator()
        self.handle_cookie_popup_if_any()
        raise NotImplementedError(
            "VAM filter selection is not implemented yet."
        )

    def close(self) -> None:
        """Release browser resources idempotently."""
        if self._closed:
            return

        self._safe_close("context", self.context)
        self.context = None

        self._safe_close("browser", self.browser)
        self.browser = None

        if self.playwright is not None:
            try:
                self.playwright.stop()
            except Exception:
                logger.debug("Failed to stop VAM Playwright runtime.", exc_info=True)
            finally:
                self.playwright = None

        self.page = None
        self._closed = True

    def _start_browser(self, playwright_factory: Callable[[], Any]) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        try:
            self.playwright = playwright_factory().start()
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo,
            )
            self.context = self.browser.new_context()
            self.page = self.context.new_page()
            self.page.set_default_timeout(self.timeout_ms)
        except Exception:
            self.close()
            raise

    def _safe_close(self, name: str, resource: Any) -> None:
        if resource is None:
            return

        try:
            resource.close()
        except Exception:
            logger.debug("Failed to close VAM adapter %s.", name, exc_info=True)

    def open_configurator(self) -> None:
        """Open the VAM configurator and wait for the page shell to settle."""
        page = self._require_page()
        logger.info("Opening VAM configurator: %s", self.configurator_url)

        try:
            page.goto(self.configurator_url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")
        except Exception as exc:
            raise RuntimeError(
                f"Failed to open VAM configurator: {self.configurator_url}"
            ) from exc

    def handle_cookie_popup_if_any(self) -> bool:
        """Dismiss a common cookie popup if one appears."""
        page = self._require_page()

        for text in self.COOKIE_BUTTON_TEXTS:
            try:
                button = page.get_by_role("button", name=text, exact=True).first
                if button.is_visible(timeout=1200):
                    button.click(force=True)
                    page.wait_for_timeout(1000)
                    logger.info("Accepted VAM cookie popup with button: %s", text)
                    return True
            except Exception:
                continue

        return False

    def _require_page(self) -> Page:
        if self.page is None:
            raise RuntimeError("VAM adapter page is not available.")

        return self.page

    def _validate_mapped_data(self, mapped_data: dict[str, Any]) -> None:
        partner = (mapped_data.get("partner") or "").upper()
        if partner != "VAM":
            raise ValueError(f"VamAdapter received non-VAM data: {mapped_data.get('partner')}")

        side = mapped_data.get("side")
        if side not in {"upper", "lower"}:
            raise ValueError(f"VAM mapped data has invalid side: {side}")

        connection = mapped_data.get("connection")
        if not isinstance(connection, dict):
            raise ValueError("VAM mapped data is missing connection data.")

        missing = [
            field
            for field in sorted(self.REQUIRED_CONNECTION_FIELDS)
            if not connection.get(field)
        ]
        if missing:
            raise ValueError(f"VAM mapped connection missing fields: {missing}")

        logger.debug("Validated VAM mapped data for %s side.", side)
