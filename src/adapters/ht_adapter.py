"""HT adapter interface."""

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


class HtAdapter(BaseAdapter):
    """Validate HT mapped data and own the HT browser session."""

    REQUIRED_CONNECTION_FIELDS = {
        "name",
        "od",
        "weight",
        "material_family",
        "yield_strength",
        "type",
    }

    SUPPORTED_CONNECTION_TYPES = {"BOX", "PIN"}

    def __init__(
        self,
        base_url: str,
        datasheet_url: str,
        logs_dir: str | Path,
        headless: bool = False,
        slow_mo: int = 300,
        timeout_ms: int = 10000,
        navigation_timeout_ms: int = 60000,
        playwright_factory: Callable[[], Any] = sync_playwright,
    ) -> None:
        self.base_url = base_url
        self.datasheet_url = datasheet_url
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
        """Validate mapped data and open the HT datasheet search page."""
        self._validate_mapped_data(mapped_data)
        self.open_datasheet_page()
        self._wait_for_search_page_loaded()
        raise NotImplementedError("HT search selection is not implemented yet.")

    def open_datasheet_page(self) -> None:
        """Open the HT connection datasheet search page."""
        logger.info("Opening HT datasheet search page: %s", self.datasheet_url)
        self._goto_page(self.datasheet_url)

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
                logger.debug("Failed to stop HT Playwright runtime.", exc_info=True)
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
            logger.debug("Failed to close HT adapter %s.", name, exc_info=True)

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

    def _wait_for_search_page_loaded(self) -> None:
        page = self._require_page()
        page.wait_for_function(
            """
            () => {
                return Boolean(
                    window.jQuery
                    && window.kendo
                    && document.querySelector("#ConnectionStyle")
                    && document.querySelector("#ConnectionType")
                    && document.querySelector("#OD")
                    && document.querySelector("#NominalWeight")
                    && document.querySelector("#MaterialGrade")
                );
            }
            """,
            timeout=30000,
        )

        self._wait_for_kendo_dropdown_ready("ConnectionStyle")
        self._wait_for_kendo_dropdown_data("ConnectionStyle")

    def _wait_for_kendo_dropdown_ready(self, input_id: str) -> None:
        page = self._require_page()
        page.wait_for_function(
            """
            (inputId) => {
                if (!window.jQuery) return false;
                const ddl = window.jQuery("#" + inputId).data("kendoDropDownList");
                return Boolean(ddl);
            }
            """,
            arg=input_id,
            timeout=30000,
        )

    def _wait_for_kendo_dropdown_data(
        self,
        input_id: str,
        min_count: int = 1,
        timeout_ms: int = 30000,
    ) -> None:
        page = self._require_page()
        page.wait_for_function(
            """
            ({ inputId, minCount }) => {
                if (!window.jQuery) return false;

                const ddl = window.jQuery("#" + inputId).data("kendoDropDownList");
                if (!ddl) return false;

                const items = ddl.dataSource && ddl.dataSource.view
                    ? ddl.dataSource.view()
                    : [];

                return items && items.length >= minCount;
            }
            """,
            arg={
                "inputId": input_id,
                "minCount": min_count,
            },
            timeout=timeout_ms,
        )

    def _require_page(self) -> Page:
        if self.page is None:
            raise RuntimeError("HT adapter page is not available.")

        return self.page

    def _validate_mapped_data(self, mapped_data: dict[str, Any]) -> None:
        partner = (mapped_data.get("partner") or "").upper()
        if partner != "HT":
            raise ValueError(f"HtAdapter received non-HT data: {mapped_data.get('partner')}")

        side = mapped_data.get("side")
        if side not in {"upper", "lower"}:
            raise ValueError(f"HT mapped data has invalid side: {side}")

        connection = mapped_data.get("connection")
        if not isinstance(connection, dict):
            raise ValueError("HT mapped data is missing connection data.")

        missing = [
            field
            for field in sorted(self.REQUIRED_CONNECTION_FIELDS)
            if not connection.get(field)
        ]
        if missing:
            raise ValueError(f"HT mapped connection missing fields: {missing}")

        connection_type = str(connection.get("type") or "").upper()
        if connection_type not in self.SUPPORTED_CONNECTION_TYPES:
            raise ValueError(
                f"HT mapped data has unsupported connection.type: {connection_type}"
            )

        logger.debug("Validated HT mapped data for %s side.", side)
