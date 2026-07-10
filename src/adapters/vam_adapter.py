"""VAM adapter interface."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from src.adapters.base_adapter import BaseAdapter


logger = logging.getLogger(__name__)


class VamAdapter(BaseAdapter):
    """Validate VAM mapped data and own the VAM browser session."""

    DEFAULT_DRIFT_OPTION = "API Drift"
    DEFAULT_MATERIAL_FAMILY = "Carbon Steel"
    DEFAULT_PIPE_SPECIFICATION = "API"

    DROPDOWN_INDEX_MAP = {
        "OD (in)": 0,
        "Weight / WT (lb/ft)": 1,
        "Pipe specification": 2,
        "Material Family": 3,
        "Yield Strength (ksi)": 4,
        "Grade": 5,
        "Drift Option": 6,
    }

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

        filters = self._build_filters_from_mapped_data(mapped_data)
        for field_label, value in filters:
            if value is None:
                continue

            if field_label == "Grade":
                self.select_grade_option_if_available(
                    material_family=value.get("material_family"),
                    yield_strength=value.get("yield_strength"),
                )
                continue

            self.select_dropdown_option_by_index(field_label, value)

        raise NotImplementedError(
            "VAM connection selection is not implemented yet."
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

    def select_dropdown_option_by_index(
        self,
        field_label: str,
        option_text: str,
    ) -> None:
        if field_label not in self.DROPDOWN_INDEX_MAP:
            raise KeyError(f"Field label not found in DROPDOWN_INDEX_MAP: {field_label}")

        page = self._require_page()
        dropdown_index = self.DROPDOWN_INDEX_MAP[field_label]
        trigger = self._get_dropdown_trigger_by_index(dropdown_index, field_label)

        try:
            trigger.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            trigger.click(force=True)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to click dropdown trigger for field [{field_label}]"
            ) from exc

        if field_label == "Weight / WT (lb/ft)":
            self._select_weight_option_from_overlay(option_text, field_label)
        else:
            self._select_option_from_overlay(option_text, field_label)

        page.wait_for_timeout(1200)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

    def select_grade_option_if_available(
        self,
        material_family: str | None,
        yield_strength: str | None,
    ) -> bool:
        if not material_family or not yield_strength:
            logger.info(
                "Skip VAM Grade selection because material_family or "
                "yield_strength is missing. material_family=%s, yield_strength=%s",
                material_family,
                yield_strength,
            )
            return False

        page = self._require_page()
        field_label = "Grade"
        dropdown_index = self.DROPDOWN_INDEX_MAP[field_label]
        trigger = self._get_dropdown_trigger_by_index(dropdown_index, field_label)

        try:
            trigger.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            trigger.click(force=True)
        except Exception:
            logger.warning("Failed to open VAM Grade dropdown. Skip Grade selection.")
            return False

        selected = self._select_grade_option_from_overlay(
            material_family=material_family,
            yield_strength=yield_strength,
            field_label=field_label,
        )

        page.wait_for_timeout(1200)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        return selected

    def _require_page(self) -> Page:
        if self.page is None:
            raise RuntimeError("VAM adapter page is not available.")

        return self.page

    def _build_filters_from_mapped_data(
        self,
        mapped_data: dict[str, Any],
    ) -> list[tuple[str, Any]]:
        connection = mapped_data.get("connection") or {}

        return [
            ("OD (in)", connection.get("od")),
            ("Weight / WT (lb/ft)", connection.get("weight")),
            ("Pipe specification", self.DEFAULT_PIPE_SPECIFICATION),
            ("Material Family", self.DEFAULT_MATERIAL_FAMILY),
            ("Yield Strength (ksi)", connection.get("yield_strength")),
            (
                "Grade",
                {
                    "material_family": connection.get("material_family"),
                    "yield_strength": connection.get("yield_strength"),
                },
            ),
            ("Drift Option", self.DEFAULT_DRIFT_OPTION),
        ]

    def _get_filter_area(self) -> Any:
        page = self._require_page()
        candidates = [
            page.locator("div.filter").first,
            page.locator("app-configurator .filter").first,
            page.locator("app-configurator").locator(".filter").first,
        ]

        for candidate in candidates:
            try:
                if candidate.is_visible(timeout=5000):
                    return candidate
            except Exception:
                continue

        raise RuntimeError("Could not find filter area")

    def _get_dropdown_trigger_by_index(
        self,
        dropdown_index: int,
        field_label: str,
    ) -> Any:
        filter_area = self._get_filter_area()

        candidates = [
            filter_area.locator("[role='combobox']"),
            filter_area.locator("mat-select"),
            filter_area.locator("input"),
            filter_area.locator(".mat-select-trigger"),
            filter_area.locator(".mat-mdc-select-trigger"),
            filter_area.locator(".mat-input-element"),
        ]

        for group in candidates:
            try:
                count = group.count()
                if count > dropdown_index:
                    trigger = group.nth(dropdown_index)
                    if trigger.is_visible(timeout=1500):
                        return trigger
            except Exception:
                continue

        divs = filter_area.locator("div")
        matched_blocks = []

        try:
            div_count = divs.count()
        except Exception:
            div_count = 0

        for index in range(min(div_count, 400)):
            try:
                div = divs.nth(index)
                if not div.is_visible(timeout=100):
                    continue

                text = div.inner_text(timeout=300).strip().lower()
                if text and "select" in text:
                    matched_blocks.append(div)
            except Exception:
                continue

        if len(matched_blocks) > dropdown_index:
            return matched_blocks[dropdown_index]

        raise RuntimeError(
            f"Could not find dropdown trigger for field [{field_label}] "
            f"at index [{dropdown_index}]"
        )

    def _select_option_from_overlay(self, option_text: str, field_label: str) -> None:
        page = self._require_page()
        overlay_candidates = [
            page.locator("div[role='listbox']").first,
            page.locator(".mat-autocomplete-panel").first,
            page.locator(".cdk-overlay-pane").first,
        ]

        overlay_found = False
        for overlay in overlay_candidates:
            try:
                overlay.wait_for(state="visible", timeout=5000)
                overlay_found = True
                break
            except Exception:
                continue

        if not overlay_found:
            raise RuntimeError(f"Dropdown overlay not found for field [{field_label}]")

        option_candidates = [
            page.locator("mat-option[role='option']").filter(has_text=option_text).first,
            page.locator("mat-option .mat-option-text").filter(has_text=option_text).first,
            page.locator(".mat-option-text").filter(has_text=option_text).first,
            page.locator("[role='option']").filter(has_text=option_text).first,
            page.get_by_text(option_text, exact=False).first,
        ]

        for option in option_candidates:
            try:
                option.wait_for(state="visible", timeout=4000)
                option.scroll_into_view_if_needed()
                page.wait_for_timeout(300)
                option.click(force=True)
                return
            except Exception:
                continue

        raise RuntimeError(
            f"Could not select option [{option_text}] for field [{field_label}]"
        )

    def _select_weight_option_from_overlay(
        self,
        weight_text: str,
        field_label: str,
    ) -> None:
        page = self._require_page()
        overlay_candidates = [
            page.locator("div[role='listbox']").first,
            page.locator(".mat-autocomplete-panel").first,
            page.locator(".cdk-overlay-pane").first,
        ]

        overlay_found = False
        for overlay in overlay_candidates:
            try:
                overlay.wait_for(state="visible", timeout=5000)
                overlay_found = True
                break
            except Exception:
                continue

        if not overlay_found:
            raise RuntimeError(f"Dropdown overlay not found for field [{field_label}]")

        prefix = f"{weight_text}#"
        option_candidates = page.locator("[role='option'], mat-option")
        matched_options = []

        try:
            count = option_candidates.count()
        except Exception:
            count = 0

        for index in range(count):
            try:
                option = option_candidates.nth(index)
                if not option.is_visible(timeout=500):
                    continue

                text = option.inner_text(timeout=1000).strip()
                if text.startswith(prefix):
                    matched_options.append(option)
            except Exception:
                continue

        if len(matched_options) == 0:
            raise RuntimeError(
                f"No weight option found for prefix [{prefix}] under current "
                "OD/material context."
            )

        if len(matched_options) > 1:
            raise RuntimeError(f"Multiple weight options found for prefix [{prefix}]")

        target_option = matched_options[0]
        target_option.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        target_option.click(force=True)

    def _select_grade_option_from_overlay(
        self,
        material_family: str,
        yield_strength: str,
        field_label: str,
    ) -> bool:
        page = self._require_page()
        overlay_candidates = [
            page.locator("div[role='listbox']").first,
            page.locator(".mat-autocomplete-panel").first,
            page.locator(".cdk-overlay-pane").first,
        ]

        overlay_found = False
        for overlay in overlay_candidates:
            try:
                overlay.wait_for(state="visible", timeout=5000)
                overlay_found = True
                break
            except Exception:
                continue

        if not overlay_found:
            logger.warning(
                "Dropdown overlay not found for field [%s]. Skip Grade selection.",
                field_label,
            )
            return False

        option_candidates = page.locator("[role='option'], mat-option")
        matched_option = None
        matched_text = None

        try:
            count = option_candidates.count()
        except Exception:
            count = 0

        for index in range(count):
            try:
                option = option_candidates.nth(index)

                if not option.is_visible(timeout=500):
                    continue

                option_text = option.inner_text(timeout=1000).strip()
                if not option_text:
                    continue

                if self._grade_option_matches(
                    option_text=option_text,
                    material_family=material_family,
                    yield_strength=yield_strength,
                ):
                    matched_option = option
                    matched_text = option_text
                    break
            except Exception:
                continue

        if matched_option is None:
            logger.info(
                "No VAM Grade option matched. Skip Grade selection. "
                "material_family=%s, yield_strength=%s",
                material_family,
                yield_strength,
            )

            try:
                page.keyboard.press("Escape")
            except Exception:
                pass

            return False

        matched_option.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        matched_option.click(force=True)

        logger.info(
            "Selected VAM Grade option: %s for material_family=%s, "
            "yield_strength=%s",
            matched_text,
            material_family,
            yield_strength,
        )

        return True

    def _grade_option_matches(
        self,
        option_text: str,
        material_family: str,
        yield_strength: str,
    ) -> bool:
        parts = self._split_grade_option_parts(option_text)
        if not parts:
            return False

        used_indexes: set[int] = set()
        targets = [
            self._normalize_grade_match_token(material_family),
            self._normalize_grade_match_token(
                self._normalize_strength_for_grade_match(yield_strength)
            ),
        ]

        for target in targets:
            if not target:
                return False

            matched_index = None
            for index, part in enumerate(parts):
                if index in used_indexes:
                    continue

                normalized_part = self._normalize_grade_match_token(part)
                if target in normalized_part:
                    matched_index = index
                    break

            if matched_index is None:
                return False

            used_indexes.add(matched_index)

        return True

    def _split_grade_option_parts(self, option_text: str) -> list[str]:
        text = str(option_text or "").replace("\u00a0", " ")
        return [
            part.strip()
            for part in re.split(r"\s+", text)
            if part and part.strip()
        ]

    def _normalize_grade_match_token(self, value: str | None) -> str:
        if not value:
            return ""

        text = str(value).upper()
        return re.sub(r"[^A-Z0-9.]+", "", text)

    def _normalize_strength_for_grade_match(self, value: str | None) -> str:
        if not value:
            return ""

        text = str(value).strip()

        try:
            number = float(text)
        except ValueError:
            return text

        if number.is_integer():
            return str(int(number))

        return f"{number:.6f}".rstrip("0").rstrip(".")

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
