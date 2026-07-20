"""JFE adapter interface."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from src.adapters.base_adapter import BaseAdapter


logger = logging.getLogger(__name__)


class JfeAdapter(BaseAdapter):
    """Validate JFE mapped data and own the JFE browser session."""

    REQUIRED_CONNECTION_FIELDS = {
        "name",
        "od",
        "weight",
        "material_family",
        "yield_strength",
        "grade_source",
        "friction",
        "coupling",
        "type",
    }

    SUPPORTED_CONNECTION_TYPES = {"BOX", "PIN"}
    SUPPORTED_GRADE_SOURCES = {"standard", "jfe"}

    def __init__(
        self,
        base_url: str,
        datasheet_url: str,
        blanking_url: str,
        logs_dir: str | Path,
        headless: bool = False,
        slow_mo: int = 300,
        timeout_ms: int = 10000,
        navigation_timeout_ms: int = 60000,
        playwright_factory: Callable[[], Any] = sync_playwright,
    ) -> None:
        self.base_url = base_url
        self.datasheet_url = datasheet_url
        self.blanking_url = blanking_url
        self.logs_dir = Path(logs_dir)
        self.headless = headless
        self.slow_mo = slow_mo
        self.timeout_ms = timeout_ms
        self.navigation_timeout_ms = navigation_timeout_ms

        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._closed = False

        self._start_browser(playwright_factory)

    def run(self, mapped_data: dict[str, Any]) -> dict[str, Any]:
        """Validate mapped data and open the JFE datasheet page."""
        self._validate_mapped_data(mapped_data)
        self.open_datasheet_page()
        self._wait_for_datasheet_page_loaded()
        raise NotImplementedError(
            "JFE datasheet selection is not implemented yet."
        )

    def open_datasheet_page(self) -> None:
        """Open the JFE connection datasheet page."""
        logger.info(
            "Opening JFE connection datasheet page: %s",
            self.datasheet_url,
        )
        self._goto_page(self.datasheet_url)

    def open_blanking_page(self) -> None:
        """Open the JFE blanking dimensions page in a fresh page."""
        logger.info(
            "Opening JFE blanking dimensions page: %s",
            self.blanking_url,
        )

        page = self._require_page()
        context = self._require_context()
        self._safe_close("page", page)

        self.page = context.new_page()
        self.page.set_default_timeout(self.timeout_ms)
        self.page.set_default_navigation_timeout(self.navigation_timeout_ms)
        self._goto_page(self.blanking_url)

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
                logger.debug("Failed to stop JFE Playwright runtime.", exc_info=True)
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
            self.page.set_default_navigation_timeout(self.navigation_timeout_ms)
        except Exception:
            self.close()
            raise

    def _safe_close(self, name: str, resource: Any) -> None:
        if resource is None:
            return

        try:
            resource.close()
        except Exception:
            logger.debug("Failed to close JFE adapter %s.", name, exc_info=True)

    def _goto_page(self, url: str) -> None:
        page = self._require_page()

        try:
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.navigation_timeout_ms,
            )
        except PlaywrightTimeoutError:
            logger.warning(
                "Navigation timeout. Continue with page readiness check: %s",
                url,
            )

        try:
            page.wait_for_load_state("load", timeout=10000)
        except PlaywrightTimeoutError:
            pass

        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeoutError:
            pass

    def _wait_for_datasheet_page_loaded(self) -> None:
        page = self._require_page()
        page.wait_for_function(
            """
            () => {
                const builder = document.querySelector("#datasheet_builder");
                if (!builder) return false;

                const selects = Array.from(builder.querySelectorAll("select"));
                if (selects.length < 2) return false;

                const connectionSelect = selects.find(select => {
                    const options = Array.from(select.options || []);
                    return options.some(o => (o.textContent || "").trim() === "JFEBEAR");
                });

                return Boolean(connectionSelect);
            }
            """,
            timeout=30000,
        )
        self._wait_for_loading_overlay_hidden()

    def _wait_for_blanking_page_loaded(self) -> None:
        page = self._require_page()
        self._wait_for_loading_overlay_hidden()

        page.locator("#datasheet_builder").wait_for(
            state="visible",
            timeout=30000,
        )
        page.locator("#datasheet_builder select").nth(3).wait_for(
            state="visible",
            timeout=30000,
        )

        self._wait_for_loading_overlay_hidden()

    def _wait_for_loading_overlay_hidden(self) -> None:
        page = self._require_page()

        try:
            page.wait_for_function(
                """
                () => {
                    const overlays = Array.from(
                        document.querySelectorAll(".loading-overlay")
                    );

                    if (overlays.length === 0) return true;

                    return overlays.every((overlay) => {
                        const style = window.getComputedStyle(overlay);

                        return style.display === "none"
                            || style.visibility === "hidden"
                            || !overlay.classList.contains("is-active");
                    });
                }
                """,
                timeout=15000,
            )
        except PlaywrightTimeoutError:
            pass

    def _require_page(self) -> Page:
        if self.page is None:
            raise RuntimeError("JFE adapter page is not available.")

        return self.page

    def _require_context(self) -> BrowserContext:
        if self.context is None:
            raise RuntimeError("JFE adapter browser context is not available.")

        return self.context

    def _validate_mapped_data(self, mapped_data: dict[str, Any]) -> None:
        partner = (mapped_data.get("partner") or "").upper()
        if partner != "JFE":
            raise ValueError(f"JfeAdapter received non-JFE data: {mapped_data.get('partner')}")

        side = mapped_data.get("side")
        if side not in {"upper", "lower"}:
            raise ValueError(f"JFE mapped data has invalid side: {side}")

        connection = mapped_data.get("connection")
        if not isinstance(connection, dict):
            raise ValueError("JFE mapped data is missing connection data.")

        missing = [
            field
            for field in sorted(self.REQUIRED_CONNECTION_FIELDS)
            if not connection.get(field)
        ]
        if missing:
            raise ValueError(f"JFE mapped connection missing fields: {missing}")

        connection_type = str(connection.get("type") or "").upper()
        if connection_type not in self.SUPPORTED_CONNECTION_TYPES:
            raise ValueError(
                f"JFE mapped data has unsupported connection.type: {connection_type}"
            )

        grade_source = str(connection.get("grade_source") or "").lower()
        if grade_source not in self.SUPPORTED_GRADE_SOURCES:
            raise ValueError(
                f"JFE mapped data has unsupported connection.grade_source: {grade_source}"
            )

        logger.debug("Validated JFE mapped data for %s side.", side)
