"""TSH adapter interface."""

from __future__ import annotations

import logging
import re
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


class TshAdapter(BaseAdapter):
    """Automate TSH datasheet and blanking pages."""

    NA = "NA"

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
        """Validate mapped data and extract TSH datasheet and blanking values."""
        self._validate_mapped_data(mapped_data)
        connection = mapped_data["connection"]
        connection_type = str(connection["type"]).upper()
        drift_extraction = bool(mapped_data.get("drift_extraction"))

        self.open_datasheet_page()
        self._select_od(connection["od"])
        self._select_weight(connection["weight"])
        self._select_grade(
            material_family=connection["material_family"],
            yield_strength=connection["yield_strength"],
        )
        self._select_connection(connection["name"])

        self._wait_for_connection_loaded()

        drift_data: dict[str, Any] = {"drift": self.NA}
        if drift_extraction:
            drift_data = {"drift": self._extract_drift_size()}

        datasheet_result = self._extract_connection_performance()

        self.open_blanking_page()
        self._select_blanking_od(connection["od"])
        self._select_blanking_weight(connection["weight"])
        self._select_blanking_connection(connection["name"])

        self._wait_for_blanking_dimensions_loaded()
        blanking_result = self._extract_blanking_dimensions(connection_type)

        return {
            **datasheet_result,
            **blanking_result,
            **drift_data,
        }

    def open_datasheet_page(self) -> None:
        self._goto_page(self.datasheet_url)
        self._wait_for_dropdowns_ready(expected_count=4)

    def open_blanking_page(self) -> None:
        self._goto_page(self.blanking_url)
        self._wait_for_dropdowns_ready(expected_count=3)

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
                logger.debug("Failed to stop TSH Playwright runtime.", exc_info=True)
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
            logger.debug("Failed to close TSH adapter %s.", name, exc_info=True)

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

    def _wait_for_dropdowns_ready(self, expected_count: int) -> None:
        page = self._require_page()
        page.wait_for_function(
            """
            (expectedCount) => {
                const scope = document.querySelector(
                    "div.select-search div.drop-downs-container"
                );

                if (!scope) {
                    return false;
                }

                function isVisible(el) {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();

                    return style
                        && style.display !== "none"
                        && style.visibility !== "hidden"
                        && rect.width > 0
                        && rect.height > 0;
                }

                const roots = Array.from(
                    scope.querySelectorAll("div.select-dropdown[data-component='dropdown']")
                ).filter(root => {
                    const optionCount = root.querySelectorAll("option.dropdown-option").length;
                    const trigger = root.querySelector(
                        ".select2-selection, .select2-selection__rendered, [role='combobox'], .dropdownicon"
                    );

                    return optionCount > 1 && (isVisible(root) || isVisible(trigger));
                });

                return roots.length >= expectedCount;
            }
            """,
            arg=expected_count,
            timeout=20000,
        )

    def _select_od(self, od_value: str) -> None:
        self._select_dropdown_by_search(
            dropdown_index=0,
            search_text=od_value,
            match_mode="exact_or_numeric",
            target_value=od_value,
        )

    def _select_weight(self, weight_value: str) -> None:
        self._select_dropdown_by_search(
            dropdown_index=1,
            search_text=weight_value,
            match_mode="weight_datasheet",
            target_value=weight_value,
        )

    def _select_grade(
        self,
        material_family: str,
        yield_strength: str,
    ) -> None:
        grade_value = f"{material_family} {yield_strength}".strip()
        self._select_dropdown_by_search(
            dropdown_index=2,
            search_text=grade_value,
            match_mode="grade",
            target_value=grade_value,
        )

    def _select_connection(self, connection_target: str) -> None:
        self._select_dropdown_by_search(
            dropdown_index=3,
            search_text=connection_target,
            match_mode="connection",
            target_value=connection_target,
        )

    def _select_blanking_od(self, od_value: str) -> None:
        self._select_dropdown_by_search(
            dropdown_index=0,
            search_text=od_value,
            match_mode="exact_or_numeric",
            target_value=od_value,
        )

    def _select_blanking_weight(self, weight_value: str) -> None:
        search_text = self._strip_trailing_zero_for_search(weight_value)
        self._select_dropdown_by_search(
            dropdown_index=1,
            search_text=search_text,
            match_mode="weight_blanking",
            target_value=weight_value,
        )

    def _select_blanking_connection(self, connection_target: str) -> None:
        self._select_dropdown_by_search(
            dropdown_index=2,
            search_text=connection_target,
            match_mode="connection",
            target_value=connection_target,
        )

    def _select_dropdown_by_search(
        self,
        dropdown_index: int,
        search_text: str,
        match_mode: str,
        target_value: str | None = None,
    ) -> None:
        page = self._require_page()
        root = self._get_dropdown_root(dropdown_index)

        self._open_select2_dropdown(root)

        search_input = self._get_visible_select2_search_input()
        search_input.click(force=True)
        search_input.fill(search_text)
        page.wait_for_timeout(700)

        option = self._find_visible_select2_option(
            target_value=target_value or search_text,
            match_mode=match_mode,
        )

        if option is None:
            visible_options = self._get_visible_select2_option_texts()
            hidden_options = self._get_dropdown_option_texts(dropdown_index)
            raise RuntimeError(
                f"Could not find TSH dropdown option. "
                f"dropdown_index={dropdown_index}, search_text=[{search_text}], "
                f"target_value=[{target_value}], match_mode=[{match_mode}], "
                f"visible_options={visible_options}, hidden_options={hidden_options}"
            )

        option.scroll_into_view_if_needed()
        option.click(force=True)
        page.wait_for_timeout(1200)

        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

    def _open_select2_dropdown(self, root: Any) -> None:
        page = self._require_page()

        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            pass

        trigger_candidates = [
            root.locator(".select2-selection").first,
            root.locator(".select2-selection__rendered").first,
            root.locator(".select2-selection__arrow").first,
            root.locator("[role='combobox']").first,
            root.locator(".dropdownicon").first,
            root.locator(".select2-container").first,
            root,
        ]

        last_error: Exception | None = None

        for trigger in trigger_candidates:
            try:
                if not trigger.is_visible(timeout=1000):
                    continue

                trigger.scroll_into_view_if_needed()
                page.wait_for_timeout(300)

                try:
                    trigger.click(timeout=2000)
                except Exception:
                    trigger.click(force=True, timeout=2000)

                if self._wait_for_select2_dropdown_opened(timeout_ms=3000):
                    return
            except Exception as exc:
                last_error = exc
                continue

        try:
            handle = root.element_handle()
            if handle:
                handle.evaluate(
                    """
                    (root) => {
                        const targets = [
                            root.querySelector(".select2-selection"),
                            root.querySelector(".select2-selection__rendered"),
                            root.querySelector(".select2-selection__arrow"),
                            root.querySelector("[role='combobox']"),
                            root.querySelector(".dropdownicon"),
                            root.querySelector(".select2-container"),
                            root
                        ].filter(Boolean);

                        for (const target of targets) {
                            target.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
                            target.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
                            target.dispatchEvent(new MouseEvent("click", { bubbles: true }));
                        }
                    }
                    """
                )

                if self._wait_for_select2_dropdown_opened(timeout_ms=3000):
                    return
        except Exception as exc:
            last_error = exc

        raise RuntimeError("TSH Select2 dropdown did not enter open state.") from last_error

    def _wait_for_select2_dropdown_opened(self, timeout_ms: int = 3000) -> bool:
        page = self._require_page()
        selectors = [
            ".select2-container--open input.select2-search__field",
            ".select2-container--open input[role='searchbox']",
            ".select2-dropdown input.select2-search__field",
            ".select2-dropdown input[role='searchbox']",
            ".select2-results__option[role='option']",
            "li.select2-results__option",
        ]

        elapsed = 0
        interval = 200

        while elapsed < timeout_ms:
            for selector in selectors:
                try:
                    locator = page.locator(selector).first
                    if locator.is_visible(timeout=200):
                        return True
                except Exception:
                    continue

            page.wait_for_timeout(interval)
            elapsed += interval

        return False

    def _get_visible_select2_search_input(self) -> Any:
        page = self._require_page()
        candidates = [
            page.locator(".select2-container--open input.select2-search__field").first,
            page.locator(".select2-container--open input[role='searchbox']").first,
            page.locator(".select2-dropdown input.select2-search__field").first,
            page.locator(".select2-dropdown input[role='searchbox']").first,
            page.locator("input.select2-search__field").first,
            page.locator("input[role='searchbox']").first,
        ]

        for candidate in candidates:
            try:
                if candidate.is_visible(timeout=3000):
                    return candidate
            except Exception:
                continue

        raise RuntimeError("Could not locate visible Select2 search input.")

    def _find_visible_select2_option(
        self,
        target_value: str,
        match_mode: str,
    ) -> Any | None:
        options = self._require_page().locator(
            ".select2-container--open .select2-results__option[role='option'], "
            ".select2-results__option[role='option'], "
            "li.select2-results__option, "
            "[role='option']"
        )

        best_option = None
        best_score = None

        try:
            count = options.count()
        except Exception:
            count = 0

        for index in range(count):
            try:
                option = options.nth(index)

                if not option.is_visible(timeout=500):
                    continue

                if option.get_attribute("aria-disabled") == "true":
                    continue

                option_text = (option.text_content(timeout=1000) or "").strip()
                if not option_text:
                    continue

                score = self._score_visible_option(
                    option_text=option_text,
                    target_value=target_value,
                    match_mode=match_mode,
                )

                if score is None:
                    continue

                if best_score is None or score > best_score:
                    best_score = score
                    best_option = option
            except Exception:
                continue

        return best_option

    def _get_visible_select2_option_texts(self) -> list[str]:
        options = self._require_page().locator(
            ".select2-container--open .select2-results__option[role='option'], "
            ".select2-results__option[role='option'], "
            "li.select2-results__option, "
            "[role='option']"
        )

        texts: list[str] = []

        try:
            count = options.count()
        except Exception:
            return texts

        for index in range(count):
            try:
                option = options.nth(index)
                if option.is_visible(timeout=300):
                    text = (option.text_content(timeout=500) or "").strip()
                    if text:
                        texts.append(text)
            except Exception:
                continue

        return texts

    def _get_dropdown_roots(self) -> Any:
        page = self._require_page()
        return page.locator(
            "div.select-search div.drop-downs-container "
            "div.select-dropdown[data-component='dropdown']"
        ).filter(has=page.locator("option.dropdown-option"))

    def _is_dropdown_root_interactable(self, root: Any) -> bool:
        trigger_candidates = [
            root.locator(".select2-selection").first,
            root.locator(".select2-selection__rendered").first,
            root.locator("[role='combobox']").first,
            root.locator(".dropdownicon").first,
            root,
        ]

        for trigger in trigger_candidates:
            try:
                if trigger.is_visible(timeout=500):
                    return True
            except Exception:
                continue

        return False

    def _get_dropdown_root(self, dropdown_index: int) -> Any:
        roots = self._get_dropdown_roots()

        try:
            raw_count = roots.count()
        except Exception:
            raw_count = 0

        visible_index = 0

        for raw_index in range(raw_count):
            root = roots.nth(raw_index)

            if not self._is_dropdown_root_interactable(root):
                continue

            if visible_index == dropdown_index:
                return root

            visible_index += 1

        raise RuntimeError(
            f"TSH dropdown root index {dropdown_index} not found. "
            f"raw_count={raw_count}, interactable_count={visible_index}"
        )

    def _get_dropdown_option_texts(self, dropdown_index: int) -> list[str]:
        root = self._get_dropdown_root(dropdown_index)
        options = root.locator("option.dropdown-option")

        texts: list[str] = []
        option_count = options.count()

        for index in range(option_count):
            text = (options.nth(index).text_content(timeout=1000) or "").strip()
            if text:
                texts.append(text)

        return texts

    def _score_visible_option(
        self,
        option_text: str,
        target_value: str,
        match_mode: str,
    ) -> int | None:
        if match_mode == "exact_or_numeric":
            return self._score_exact_or_numeric_option(option_text, target_value)

        if match_mode == "contains":
            return self._score_contains_option(option_text, target_value)

        if match_mode == "weight_datasheet":
            return self._score_weight_option_datasheet(option_text, target_value)

        if match_mode == "weight_blanking":
            return self._score_weight_option_blanking(option_text, target_value)

        if match_mode == "grade":
            return self._score_grade_option(option_text, target_value)

        if match_mode == "connection":
            return self._score_connection_option(option_text, target_value)

        return self._score_contains_option(option_text, target_value)

    def _score_exact_or_numeric_option(
        self,
        option_text: str,
        target_value: str,
    ) -> int | None:
        option_clean = self._normalize_dropdown_option_text(option_text)
        target_clean = self._normalize_dropdown_option_text(target_value)

        if option_clean == target_clean:
            return 10000

        try:
            if float(option_clean) == float(target_clean):
                return 9000
        except ValueError:
            pass

        return None

    def _score_contains_option(
        self,
        option_text: str,
        target_value: str,
    ) -> int | None:
        option_clean = self._normalize_dropdown_option_text(option_text).upper()
        target_clean = self._normalize_dropdown_option_text(target_value).upper()

        if option_clean == target_clean:
            return 10000

        if target_clean in option_clean:
            return 8000 - len(option_clean)

        return None

    def _score_weight_option_datasheet(
        self,
        option_text: str,
        target_weight: str,
    ) -> int | None:
        target_num = self._safe_float(target_weight)

        if target_num is None:
            return self._score_contains_option(option_text, target_weight)

        option_clean = self._normalize_dropdown_option_text(option_text)

        paren_match = re.search(r"\((.*?)\)", option_clean)
        if paren_match:
            raw_tokens = [token.strip() for token in paren_match.group(1).split(",")]
            for token in raw_tokens:
                token_num = self._safe_float(token)
                if token_num is not None and token_num == target_num:
                    return 10000

        if str(target_weight).strip() in option_clean:
            return 7000 - len(option_clean)

        return None

    def _score_weight_option_blanking(
        self,
        option_text: str,
        target_weight: str,
    ) -> int | None:
        target_num = self._safe_float(target_weight)

        if target_num is None:
            return self._score_contains_option(option_text, target_weight)

        option_clean = self._normalize_dropdown_option_text(option_text)

        paren_match = re.search(r"\((.*?)\)", option_clean)
        if paren_match:
            token = paren_match.group(1).strip()
            token_num = self._safe_float(token)
            if token_num is not None and token_num == target_num:
                return 10000

        if self._strip_trailing_zero_for_search(target_weight) in option_clean:
            return 7000 - len(option_clean)

        return None

    def _score_grade_option(self, option_text: str, target_value: str) -> int | None:
        option_clean = self._normalize_dropdown_option_text(option_text).upper()
        target_clean = self._normalize_dropdown_option_text(target_value).upper()

        if not option_clean or not target_clean:
            return None

        if option_clean == target_clean:
            return 10000

        target_tokens = re.findall(r"[A-Z0-9.]+", target_clean)

        if len(target_tokens) < 2:
            return self._score_contains_option(option_text, target_value)

        material_family = target_tokens[0]
        yield_strength = target_tokens[1]

        material_family_matched = material_family in option_clean
        yield_strength_matched = bool(
            re.search(rf"(^|[^0-9]){re.escape(yield_strength)}([^0-9]|$)", option_clean)
            or re.search(rf"\bL{re.escape(yield_strength)}\b", option_clean)
        )

        if material_family_matched and yield_strength_matched:
            return 10000 - len(option_clean)

        if material_family_matched:
            return 4000 - len(option_clean)

        return None

    def _score_connection_option(self, option_text: str, target_value: str) -> int | None:
        normalized_target = self._normalize_connection_text(target_value)
        normalized_option = self._normalize_connection_text(option_text)

        if not normalized_target or not normalized_option:
            return None

        if normalized_option == normalized_target:
            return 100000

        target_tokens = self._tokenize_connection(normalized_target)
        option_tokens = self._tokenize_connection(normalized_option)

        target_token_set = set(target_tokens)
        option_token_set = set(option_tokens)

        if not target_token_set.issubset(option_token_set):
            return None

        target_numbers = self._extract_number_tokens(normalized_target)
        option_numbers = self._extract_number_tokens(normalized_option)

        score = 50000

        if target_numbers:
            if option_numbers == target_numbers:
                score += 30000
            elif set(target_numbers).issubset(set(option_numbers)):
                score += 15000
            else:
                return None

        if normalized_option.startswith(normalized_target):
            score += 5000

        extra_tokens = len(option_tokens) - len(target_tokens)
        score -= extra_tokens * 500
        score -= len(normalized_option)

        return score

    def _normalize_dropdown_option_text(self, text: str | None) -> str:
        if not text:
            return ""

        text = text.replace("\u00a0", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _normalize_connection_text(self, text: str | None) -> str:
        if not text:
            return ""

        normalized = text.upper().strip()
        normalized = re.sub(r"^\s*TSH\s+", "", normalized)
        normalized = normalized.replace("\u00c2\u00ae", " ")
        normalized = normalized.replace("\u00e2\u201e\u00a2", " ")
        normalized = re.sub(r"[-_/]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _tokenize_connection(self, normalized_text: str) -> list[str]:
        return re.findall(r"[A-Z0-9.]+", normalized_text)

    def _extract_number_tokens(self, normalized_text: str) -> list[str]:
        return re.findall(r"\d+(?:\.\d+)?", normalized_text)

    def _strip_trailing_zero_for_search(self, value: str) -> str:
        try:
            return str(float(value)).rstrip("0").rstrip(".")
        except ValueError:
            return value.strip()

    def _safe_float(self, value: str) -> float | None:
        if value is None:
            return None

        try:
            return float(str(value).replace(",", "").strip())
        except ValueError:
            return None

    def _wait_for_connection_loaded(self) -> None:
        self._require_page().wait_for_function(
            """
            () => {
                const txt = document.body.innerText || "";
                return txt.includes("Pipe Body Data")
                    && txt.includes("Connection Data")
                    && txt.includes("Performance")
                    && txt.includes("Joint Yield Strength")
                    && txt.includes("Compression Strength");
            }
            """,
            timeout=20000,
        )

    def _extract_connection_performance(self) -> dict[str, Any]:
        body_text = self._require_page().locator("body").inner_text(timeout=5000)
        normalized = self._normalize_text(body_text)

        connection_section = self._extract_section(
            text=normalized,
            start_label="Connection Data",
            end_candidates=["Make-Up Torques", "Operation Limit Torques"],
        )

        performance_section = self._extract_section(
            text=connection_section,
            start_label="Performance",
            end_candidates=["Make-Up Torques", "Operation Limit Torques"],
        )

        return {
            "tensile": self._extract_first_number_after_label(
                performance_section,
                "Joint Yield Strength",
            ),
            "compression": self._extract_first_number_after_label(
                performance_section,
                "Compression Strength",
            ),
            "burst": self._extract_first_number_after_label(
                performance_section,
                "Internal Pressure Capacity",
            ),
            "collapse": self._extract_first_number_after_label(
                performance_section,
                "External Pressure Capacity",
            ),
        }

    def _extract_drift_size(self) -> str | None:
        body_text = self._require_page().locator("body").inner_text(timeout=5000)
        normalized = self._normalize_text(body_text)

        pipe_body_section = self._extract_section(
            text=normalized,
            start_label="Pipe Body Data",
            end_candidates=["Connection Data"],
        )

        geometry_section = self._extract_section(
            text=pipe_body_section,
            start_label="Geometry",
            end_candidates=["Performance"],
        )

        drift = self._extract_first_number_after_label(
            geometry_section,
            "Drift",
        )

        if drift:
            return drift

        raise RuntimeError(
            f"Could not extract TSH Drift from datasheet Pipe Body Data -> Geometry section: "
            f"{geometry_section[:500]}"
        )

    def _wait_for_blanking_dimensions_loaded(self) -> None:
        self._require_page().wait_for_function(
            """
            () => {
                const txt = document.body.innerText || "";
                return txt.includes("Blanking Dimensions")
                    && txt.includes("Selected Product")
                    && txt.includes("Box")
                    && txt.includes("Pin")
                    && txt.includes("Inside Diameter Min")
                    && txt.includes("Outside Diameter Max");
            }
            """,
            timeout=20000,
        )

    def _extract_blanking_dimensions(self, connection_type: str) -> dict[str, Any]:
        body_text = self._require_page().locator("body").inner_text(timeout=5000)
        normalized = self._normalize_text(body_text)

        if connection_type == "BOX":
            section_text = self._extract_section(
                text=normalized,
                start_label="Box",
                end_candidates=["Pin"],
            )
        elif connection_type == "PIN":
            section_text = self._extract_section(
                text=normalized,
                start_label="Pin",
                end_candidates=[],
            )
        else:
            raise RuntimeError(f"Unsupported TSH connection type: {connection_type}")

        length_min = self._extract_length_min(section_text)
        outside_min = self._extract_first_number_after_label(
            section_text,
            "Outside Diameter Min",
        )
        outside_max = self._extract_first_number_after_label(
            section_text,
            "Outside Diameter Max",
        )
        inside_min = self._extract_first_number_after_label(
            section_text,
            "Inside Diameter Min",
        )
        inside_max = self._extract_first_number_after_label(
            section_text,
            "Inside Diameter Max",
        )

        if not outside_min or not outside_max:
            raise RuntimeError(f"TSH blanking {connection_type} missing Outside Diameter Min/Max")

        if not inside_min or not inside_max:
            raise RuntimeError(f"TSH blanking {connection_type} missing Inside Diameter Min/Max")

        return {
            "od": {
                "min": outside_min,
                "max": outside_max,
            },
            "id": {
                "min": inside_min,
                "max": inside_max,
            },
            "external_length": length_min,
            "internal_length": length_min,
        }

    def _extract_section(
        self,
        text: str,
        start_label: str,
        end_candidates: list[str],
    ) -> str:
        start_index = text.find(start_label)
        if start_index == -1:
            return text

        end_index = len(text)
        for candidate in end_candidates:
            index = text.find(candidate, start_index + len(start_label))
            if index != -1 and index < end_index:
                end_index = index

        return text[start_index:end_index].strip()

    def _extract_length_min(self, section_text: str) -> str | None:
        value = self._extract_first_number_after_label(section_text, "Length Min")

        if value is None:
            raise RuntimeError(
                f"TSH blanking section missing Length Min: {section_text[:500]}"
            )

        try:
            return f"{float(value.replace(',', '').strip()):.3f}"
        except ValueError as exc:
            raise RuntimeError(f"Invalid TSH Length Min value: {value}") from exc

    def _extract_first_number_after_label(self, text: str, label: str) -> str | None:
        pattern = rf"{re.escape(label)}\s+([+\-]?\d+(?:,\d{{3}})*(?:\.\d+)?)"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\u00a0", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _require_page(self) -> Page:
        if self.page is None:
            raise RuntimeError("TSH adapter page is not available.")

        return self.page

    def _validate_mapped_data(self, mapped_data: dict[str, Any]) -> None:
        partner = (mapped_data.get("partner") or "").upper()
        if partner != "TSH":
            raise ValueError(f"TshAdapter received non-TSH data: {mapped_data.get('partner')}")

        side = mapped_data.get("side")
        if side not in {"upper", "lower"}:
            raise ValueError(f"TSH mapped data has invalid side: {side}")

        connection = mapped_data.get("connection")
        if not isinstance(connection, dict):
            raise ValueError("TSH mapped data is missing connection data.")

        missing = [
            field
            for field in sorted(self.REQUIRED_CONNECTION_FIELDS)
            if not connection.get(field)
        ]
        if missing:
            raise ValueError(f"TSH mapped connection missing fields: {missing}")

        connection_type = str(connection.get("type") or "").upper()
        if connection_type not in self.SUPPORTED_CONNECTION_TYPES:
            raise ValueError(
                f"TSH mapped data has unsupported connection.type: {connection_type}"
            )

        logger.debug("Validated TSH mapped data for %s side.", side)
