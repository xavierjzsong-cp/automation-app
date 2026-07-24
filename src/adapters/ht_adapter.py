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

    CONNECTION_STYLE = "Threaded and Coupled"

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
        """Validate mapped data and select the HT datasheet search options."""
        self._validate_mapped_data(mapped_data)
        connection = mapped_data["connection"]
        connection_type = self._map_connection_type(str(connection["name"]))
        material_grade = self._map_material_grade(mapped_data)
        if not material_grade:
            raise ValueError(
                "HT mapped_data missing material grade information. "
                "Expected connection.material_family + connection.yield_strength."
            )

        self.open_datasheet_page()
        self._wait_for_search_page_loaded()
        self._select_search_options(
            connection_type=connection_type,
            od_value=str(connection["od"]).strip(),
            weight_value=str(connection["weight"]).strip(),
            material_grade=material_grade,
        )
        raise NotImplementedError("HT report opening is not implemented yet.")

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

    def _select_search_options(
        self,
        connection_type: str,
        od_value: str,
        weight_value: str,
        material_grade: str,
    ) -> None:
        self._select_kendo_dropdown_by_text(
            input_id="ConnectionStyle",
            target_text=self.CONNECTION_STYLE,
            match_mode="text",
        )

        self._wait_for_kendo_dropdown_data("ConnectionType")

        self._select_kendo_dropdown_by_text(
            input_id="ConnectionType",
            target_text=connection_type,
            match_mode="text",
        )

        self._wait_for_kendo_dropdown_data("OD")

        self._select_kendo_dropdown_by_text(
            input_id="OD",
            target_text=od_value,
            match_mode="numeric",
        )

        self._wait_for_kendo_dropdown_data("NominalWeight")

        self._select_kendo_dropdown_by_text(
            input_id="NominalWeight",
            target_text=weight_value,
            match_mode="numeric",
        )

        self._wait_for_kendo_dropdown_data("MaterialGrade")

        self._select_kendo_dropdown_by_text(
            input_id="MaterialGrade",
            target_text=material_grade,
            match_mode="material",
        )

    def _select_kendo_dropdown_by_text(
        self,
        input_id: str,
        target_text: str,
        match_mode: str,
    ) -> None:
        page = self._require_page()
        result = page.evaluate(
            """
            async ({ inputId, targetText, matchMode }) => {
                const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms));

                const normalizeText = (value) => {
                    return String(value || "")
                        .replace(/\\u00a0/g, " ")
                        .replace(/\\s+/g, " ")
                        .trim();
                };

                const extractNumber = (value) => {
                    const text = normalizeText(value).replace(/,/g, "");
                    const match = text.match(/[-+]?\\d+(?:\\.\\d+)?/);
                    return match ? Number(match[0]) : null;
                };

                const normalizeMaterial = (value) => {
                    return normalizeText(value)
                        .toUpperCase()
                        .replace(/[\\s\\-_/()]/g, "");
                };

                const extractYieldStrength = (value) => {
                    const text = normalizeText(value).replace(/,/g, "");
                    const matches = text.match(/\\d+(?:\\.\\d+)?/g);

                    if (!matches || matches.length === 0) {
                        return null;
                    }

                    return Number(matches[matches.length - 1]);
                };

                const scoreItem = (itemText) => {
                    const optionText = normalizeText(itemText);
                    const optionUpper = optionText.toUpperCase();
                    const target = normalizeText(targetText);
                    const targetUpper = target.toUpperCase();

                    if (!optionText || !target) return null;

                    if (optionUpper === targetUpper) {
                        return 10000;
                    }

                    if (matchMode === "numeric") {
                        const optionNumber = extractNumber(optionText);
                        const targetNumber = extractNumber(target);

                        if (
                            optionNumber !== null
                            && targetNumber !== null
                            && Math.abs(optionNumber - targetNumber) < 0.000001
                        ) {
                            return 9000 - optionText.length;
                        }

                        return null;
                    }

                    if (matchMode === "material") {
                        const optionMaterial = normalizeMaterial(optionText);
                        const targetMaterial = normalizeMaterial(target);

                        if (optionMaterial === targetMaterial) {
                            return 10000;
                        }

                        const optionYield = extractYieldStrength(optionText);
                        const targetYield = extractYieldStrength(target);

                        if (
                            optionYield !== null
                            && targetYield !== null
                            && Math.abs(optionYield - targetYield) < 0.000001
                        ) {
                            return 5000;
                        }

                        return null;
                    }

                    if (optionUpper.includes(targetUpper)) {
                        return 7000 - optionText.length;
                    }

                    return null;
                };

                const ddl = window.jQuery("#" + inputId).data("kendoDropDownList");

                if (!ddl) {
                    return {
                        ok: false,
                        reason: "Kendo DropDownList not found",
                        inputId,
                    };
                }

                for (let i = 0; i < 20; i++) {
                    const view = ddl.dataSource && ddl.dataSource.view
                        ? ddl.dataSource.view()
                        : [];

                    if (view && view.length > 0) {
                        break;
                    }

                    try {
                        ddl.dataSource.read();
                    } catch (e) {
                        // ignore
                    }

                    await wait(500);
                }

                const data = ddl.dataSource && ddl.dataSource.view
                    ? ddl.dataSource.view()
                    : [];

                let bestItem = null;
                let bestScore = null;

                for (const item of data) {
                    const itemText = normalizeText(item.Text ?? item.text ?? item.Name ?? "");
                    const itemValue = item.Value ?? item.value ?? item.Id ?? itemText;

                    if (!itemText) continue;

                    const score = scoreItem(itemText);
                    if (score === null) continue;

                    if (bestScore === null || score > bestScore) {
                        bestScore = score;
                        bestItem = {
                            text: itemText,
                            value: itemValue,
                        };
                    }
                }

                if (!bestItem) {
                    return {
                        ok: false,
                        reason: "Option not found",
                        inputId,
                        targetText,
                        matchMode,
                        availableOptions: data.map(item =>
                            normalizeText(item.Text ?? item.text ?? item.Name ?? "")
                        ).filter(Boolean),
                    };
                }

                ddl.value(bestItem.value);
                ddl.trigger("change");
                ddl.element.trigger("change");

                return {
                    ok: true,
                    inputId,
                    selectedText: bestItem.text,
                    selectedValue: bestItem.value,
                };
            }
            """,
            {
                "inputId": input_id,
                "targetText": target_text,
                "matchMode": match_mode,
            },
        )

        if not result or not result.get("ok"):
            raise RuntimeError(f"Failed to select HT dropdown option: {result}")

        logger.info(
            "Selected HT dropdown %s -> %s",
            input_id,
            result.get("selectedText"),
        )

        page.wait_for_timeout(1200)

        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except PlaywrightTimeoutError:
            pass

    def _require_page(self) -> Page:
        if self.page is None:
            raise RuntimeError("HT adapter page is not available.")

        return self.page

    def _map_connection_type(self, connection_name: str) -> str:
        text = connection_name.strip().upper()
        text = text.replace(" ", "")

        if "SLHT-S" in text or "SLHTS" in text or "HT-S" in text or "HTS" in text:
            return "SEAL-LOCK HT-S"

        if "SLHT" in text or text == "HT":
            return "SEAL-LOCK HT"

        raise ValueError(f"Unsupported HT connection name: {connection_name}")

    def _map_material_grade(self, mapped_data: dict[str, Any]) -> str | None:
        connection = mapped_data.get("connection") or {}

        material_family = connection.get("material_family")
        yield_strength = connection.get("yield_strength")

        if not material_family or not yield_strength:
            return None

        return self._build_material_grade(
            material_family=str(material_family),
            yield_strength=str(yield_strength),
        )

    def _build_material_grade(
        self,
        material_family: str,
        yield_strength: str,
    ) -> str:
        family = material_family.strip().upper()
        strength = yield_strength.strip().upper()

        if strength.endswith(".0"):
            strength = strength[:-2]

        return f"{family}-{strength}"

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
