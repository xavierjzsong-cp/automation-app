"""Smoke checks for the JFE adapter datasheet extraction flow."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.adapters.jfe_adapter import JfeAdapter  # noqa: E402


class FakePage:
    def __init__(self) -> None:
        self.goto_calls: list[dict[str, Any]] = []
        self.load_states: list[dict[str, Any]] = []
        self.function_checks: list[dict[str, Any]] = []
        self.evaluate_calls: list[dict[str, str]] = []
        self.table_values: dict[tuple[str, str], str | None] = {
            ("CONNECTION PERFORMANCE", "Joint Strength"): "561,000 lbf",
            ("CONNECTION PERFORMANCE", "Compression Rating"): "540,000 lbf",
            ("CONNECTION PERFORMANCE", "Internal Yield Pressure"): "12,345 psi",
            ("CONNECTION PERFORMANCE", "Collapse Pressure"): "10,987 psi",
            ("PIPE", "Drift Diameter"): "4.767 in",
        }
        self.locator_waits: list[dict[str, Any]] = []
        self.timeout = None
        self.navigation_timeout = None
        self.closed = False

    def set_default_timeout(self, timeout: int) -> None:
        self.timeout = timeout

    def set_default_navigation_timeout(self, timeout: int) -> None:
        self.navigation_timeout = timeout

    def goto(self, url: str, wait_until: str, timeout: int) -> None:
        self.goto_calls.append(
            {
                "url": url,
                "wait_until": wait_until,
                "timeout": timeout,
            }
        )

    def wait_for_load_state(self, state: str, timeout: int) -> None:
        self.load_states.append({"state": state, "timeout": timeout})

    def wait_for_function(self, script: str, timeout: int) -> None:
        self.function_checks.append({"script": script, "timeout": timeout})

    def locator(self, selector: str) -> "FakeLocator":
        return FakeLocator(self, selector)

    def evaluate(self, script: str, args: dict[str, str]) -> str | None:
        assert "#datasheet_page tbody" in script
        self.evaluate_calls.append(args)
        return self.table_values.get(
            (args["identifier"], args["fieldLabel"])
        )

    def close(self) -> None:
        self.closed = True


class FakeLocator:
    def __init__(self, page: FakePage, selector: str, index: int | None = None) -> None:
        self.page = page
        self.selector = selector
        self.index = index

    def nth(self, index: int) -> "FakeLocator":
        return FakeLocator(self.page, self.selector, index)

    def wait_for(self, state: str, timeout: int) -> None:
        self.page.locator_waits.append(
            {
                "selector": self.selector,
                "index": self.index,
                "state": state,
                "timeout": timeout,
            }
        )


class FakeContext:
    def __init__(self) -> None:
        self.closed = False
        self.pages: list[FakePage] = []

    def new_page(self) -> FakePage:
        page = FakePage()
        self.pages.append(page)
        return page

    def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self) -> None:
        self.closed = False
        self.context = FakeContext()

    def new_context(self) -> FakeContext:
        return self.context

    def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self) -> None:
        self.launch_args: dict[str, Any] | None = None
        self.browser = FakeBrowser()

    def launch(self, headless: bool, slow_mo: int) -> FakeBrowser:
        self.launch_args = {"headless": headless, "slow_mo": slow_mo}
        return self.browser


class FakePlaywright:
    def __init__(self) -> None:
        self.chromium = FakeChromium()
        self.started = False
        self.stopped = False

    def start(self) -> "FakePlaywright":
        self.started = True
        return self

    def stop(self) -> None:
        self.stopped = True


class RecordingJfeAdapter(JfeAdapter):
    """Replace page interaction while preserving adapter orchestration."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.dropdown_selections: list[dict[str, str]] = []
        super().__init__(*args, **kwargs)

    def _select_dropdown_by_field_label(
        self,
        field_label: str,
        option_text: str,
    ) -> None:
        self.dropdown_selections.append(
            {
                "field_label": field_label,
                "option_text": option_text,
            }
        )


class FakeOption:
    def __init__(
        self,
        text: str,
        value: str | None,
        *,
        disabled: bool = False,
        hidden: bool = False,
    ) -> None:
        self.text = text
        self.value = value
        self.disabled = disabled
        self.hidden = hidden

    def get_attribute(self, name: str) -> str | None:
        if name == "value":
            return self.value
        if name == "disabled" and self.disabled:
            return "disabled"
        if name == "hidden" and self.hidden:
            return "hidden"
        return None

    def text_content(self, timeout: int) -> str:
        assert timeout == 500
        return self.text


class FakeOptionCollection:
    def __init__(self, options: list[FakeOption]) -> None:
        self.options = options

    def count(self) -> int:
        return len(self.options)

    def nth(self, index: int) -> FakeOption:
        return self.options[index]


class FakeSelect:
    def __init__(self, options: list[FakeOption]) -> None:
        self.options = FakeOptionCollection(options)

    def locator(self, selector: str) -> FakeOptionCollection:
        assert selector == "option"
        return self.options


def build_mapped_data() -> dict[str, Any]:
    return {
        "partner": "JFE",
        "side": "upper",
        "drift_extraction": True,
        "connection": {
            "name": "JFEBEAR",
            "od": "5.500",
            "weight": "17",
            "material_family": "13CR",
            "yield_strength": "80",
            "grade_source": "standard",
            "friction": "API Modified",
            "coupling": "STD",
            "type": "BOX",
        },
    }


def check_repeated_option_matching(adapter: JfeAdapter) -> None:
    """Exercise deterministic matching repeatedly without website traffic."""
    select_cases = [
        (
            "Connection",
            "JFEBEAR",
            FakeSelect(
                [
                    FakeOption("Connection", "", disabled=True),
                    FakeOption("JFE BEAR", "connection-bear"),
                    FakeOption("JFE FOX", "connection-fox"),
                ]
            ),
            "connection-bear",
        ),
        (
            "Size",
            "5.500",
            FakeSelect(
                [
                    FakeOption("5.000 in", "size-5"),
                    FakeOption("5.500 in", "size-5.5"),
                    FakeOption("5.500", "hidden-exact", hidden=True),
                ]
            ),
            "size-5.5",
        ),
        (
            "Weight",
            "17",
            FakeSelect(
                [
                    FakeOption("15.50 lb/ft", "weight-15.5"),
                    FakeOption("17.00 lb/ft", "weight-17"),
                ]
            ),
            "weight-17",
        ),
        (
            "Grade",
            "L80-13CR",
            FakeSelect(
                [
                    FakeOption("L80 13CR", "grade-l80"),
                    FakeOption("L95 13CR", "grade-l95"),
                ]
            ),
            "grade-l80",
        ),
        (
            "Friction",
            "API Modified",
            FakeSelect(
                [
                    FakeOption("API", "friction-api"),
                    FakeOption("API Modified", "friction-api-modified"),
                ]
            ),
            "friction-api-modified",
        ),
        (
            "Coupling",
            "STD",
            FakeSelect(
                [
                    FakeOption("Special Clearance", "coupling-special"),
                    FakeOption("STD", "coupling-std"),
                ]
            ),
            "coupling-std",
        ),
    ]

    for _ in range(250):
        for field_label, target, select, expected in select_cases:
            actual = adapter._find_option_value_by_text(
                select=select,
                target_text=target,
                field_label=field_label,
            )
            assert actual == expected

    unmatched = FakeSelect([FakeOption("9.625 in", "size-9.625")])
    assert adapter._find_option_value_by_text(
        select=unmatched,
        target_text="5.500",
        field_label="Size",
    ) is None


def check_repeated_extraction(adapter: JfeAdapter) -> None:
    """Exercise extraction repeatedly through the replaceable page boundary."""
    mapped_data = build_mapped_data()
    expected = {
        "tensile": "561000",
        "compression": "540000",
        "burst": "12345",
        "collapse": "10987",
        "drift": "4.767",
    }

    for _ in range(250):
        assert adapter.extract_required_data(mapped_data) == expected


def main() -> None:
    tmp = TemporaryDirectory()
    fake_playwright = FakePlaywright()
    adapter = RecordingJfeAdapter(
        base_url="https://www.jfetools.com/",
        datasheet_url="https://www.jfetools.com/datasheet_generator",
        blanking_url="https://www.jfetools.com/blanking_dimensions",
        logs_dir=Path(tmp.name),
        headless=True,
        slow_mo=25,
        timeout_ms=1234,
        navigation_timeout_ms=5678,
        playwright_factory=lambda: fake_playwright,
    )

    try:
        assert fake_playwright.started is True
        assert fake_playwright.chromium.launch_args == {
            "headless": True,
            "slow_mo": 25,
        }
        assert adapter.browser is fake_playwright.chromium.browser
        assert adapter.context is fake_playwright.chromium.browser.context
        assert adapter.page is fake_playwright.chromium.browser.context.pages[0]
        assert adapter.page.timeout == 1234
        assert adapter.page.navigation_timeout == 5678

        assert adapter.base_url == "https://www.jfetools.com/"
        assert adapter.datasheet_url == "https://www.jfetools.com/datasheet_generator"
        assert adapter.blanking_url == "https://www.jfetools.com/blanking_dimensions"
        assert adapter.logs_dir == Path(tmp.name)
        assert adapter.headless is True
        assert adapter.slow_mo == 25
        assert adapter.timeout_ms == 1234
        assert adapter.navigation_timeout_ms == 5678

        try:
            adapter.run({"partner": "JFE", "side": "upper", "connection": {}})
            raise AssertionError("Expected ValueError for incomplete JFE data.")
        except ValueError:
            pass
        assert adapter.page.goto_calls == []
        assert adapter.dropdown_selections == []

        invalid_type = build_mapped_data()
        invalid_type["connection"]["type"] = "COUPLING"
        try:
            adapter.run(invalid_type)
            raise AssertionError("Expected ValueError for unsupported JFE type.")
        except ValueError:
            pass

        invalid_grade_source = build_mapped_data()
        invalid_grade_source["connection"]["grade_source"] = "unknown"
        try:
            adapter.run(invalid_grade_source)
            raise AssertionError("Expected ValueError for unsupported JFE grade source.")
        except ValueError:
            pass

        result = adapter.run(build_mapped_data())
        assert result == {
            "tensile": "561000",
            "compression": "540000",
            "burst": "12345",
            "collapse": "10987",
            "drift": "4.767",
        }

        assert adapter.dropdown_selections == [
            {"field_label": "Connection", "option_text": "JFEBEAR"},
            {"field_label": "Size", "option_text": "5.500"},
            {"field_label": "Weight", "option_text": "17"},
            {"field_label": "Grade", "option_text": "L80-13CR"},
            {"field_label": "Friction", "option_text": "API Modified"},
            {"field_label": "Coupling", "option_text": "STD"},
        ]

        jfe_grade_data = build_mapped_data()
        jfe_grade_data["connection"]["grade_source"] = "jfe"
        jfe_grade_data["connection"]["yield_strength"] = "95"
        assert adapter._build_grade_option_text(
            jfe_grade_data["connection"]
        ) == "JFE-13CR-95"
        assert adapter._build_standard_grade("carbon", "80") == "CARBON-80"

        incomplete_selection = build_mapped_data()
        incomplete_selection["connection"]["friction"] = ""
        try:
            adapter._build_datasheet_selections(incomplete_selection)
            raise AssertionError("Expected ValueError for missing JFE friction.")
        except ValueError as exc:
            assert "Friction" in str(exc)

        check_repeated_option_matching(adapter)

        no_drift_data = build_mapped_data()
        no_drift_data["drift_extraction"] = False
        no_drift_result = adapter.extract_required_data(no_drift_data)
        assert no_drift_result["drift"] == "NA"

        datasheet_page = fake_playwright.chromium.browser.context.pages[0]
        missing_key = ("CONNECTION PERFORMANCE", "Joint Strength")
        datasheet_page.table_values[missing_key] = None
        try:
            adapter._extract_first_number_from_table_field(*missing_key)
            raise AssertionError("Expected RuntimeError for missing JFE field.")
        except RuntimeError as exc:
            assert "Could not extract JFE field" in str(exc)

        datasheet_page.table_values[missing_key] = "Not available"
        try:
            adapter._extract_first_number_from_table_field(*missing_key)
            raise AssertionError("Expected RuntimeError for nonnumeric JFE field.")
        except RuntimeError as exc:
            assert "Could not extract numeric value" in str(exc)

        datasheet_page.table_values[missing_key] = "561,000 lbf"
        check_repeated_extraction(adapter)

        assert datasheet_page.goto_calls == [
            {
                "url": "https://www.jfetools.com/datasheet_generator",
                "wait_until": "domcontentloaded",
                "timeout": 5678,
            }
        ]
        assert datasheet_page.load_states == [
            {"state": "load", "timeout": 10000},
            {"state": "networkidle", "timeout": 10000},
        ]
        assert [check["timeout"] for check in datasheet_page.function_checks] == [
            30000,
            15000,
            15000,
            30000,
        ]
        assert "#datasheet_builder" in datasheet_page.function_checks[0]["script"]
        assert "JFEBEAR" in datasheet_page.function_checks[0]["script"]
        assert "CONNECTION PERFORMANCE" in datasheet_page.function_checks[3]["script"]
        assert datasheet_page.evaluate_calls[:5] == [
            {
                "identifier": "CONNECTION PERFORMANCE",
                "fieldLabel": "Joint Strength",
            },
            {
                "identifier": "CONNECTION PERFORMANCE",
                "fieldLabel": "Compression Rating",
            },
            {
                "identifier": "CONNECTION PERFORMANCE",
                "fieldLabel": "Internal Yield Pressure",
            },
            {
                "identifier": "CONNECTION PERFORMANCE",
                "fieldLabel": "Collapse Pressure",
            },
            {"identifier": "PIPE", "fieldLabel": "Drift Diameter"},
        ]

        adapter.open_blanking_page()
        assert datasheet_page.closed is True
        assert len(fake_playwright.chromium.browser.context.pages) == 2

        blanking_page = fake_playwright.chromium.browser.context.pages[1]
        assert adapter.page is blanking_page
        assert blanking_page.timeout == 1234
        assert blanking_page.navigation_timeout == 5678
        assert blanking_page.goto_calls == [
            {
                "url": "https://www.jfetools.com/blanking_dimensions",
                "wait_until": "domcontentloaded",
                "timeout": 5678,
            }
        ]
        assert blanking_page.load_states == [
            {"state": "load", "timeout": 10000},
            {"state": "networkidle", "timeout": 10000},
        ]

        adapter._wait_for_blanking_page_loaded()
        assert [check["timeout"] for check in blanking_page.function_checks] == [
            15000,
            15000,
        ]
        assert blanking_page.locator_waits == [
            {
                "selector": "#datasheet_builder",
                "index": None,
                "state": "visible",
                "timeout": 30000,
            },
            {
                "selector": "#datasheet_builder select",
                "index": 3,
                "state": "visible",
                "timeout": 30000,
            },
        ]
    finally:
        adapter.close()
        assert fake_playwright.chromium.browser.context.closed is True
        assert fake_playwright.chromium.browser.closed is True
        assert fake_playwright.stopped is True
        assert adapter._closed is True
        adapter.close()
        tmp.cleanup()

    print("jfe adapter ok")


if __name__ == "__main__":
    main()
