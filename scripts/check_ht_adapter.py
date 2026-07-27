"""Smoke checks for the HT adapter report-opening flow."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.adapters.ht_adapter import HtAdapter  # noqa: E402


def build_report_blocks() -> list[dict[str, Any]]:
    return [
        {"text": "Pipe Body Data", "left": 10, "top": 10},
        {"text": "API Drift Diameter", "left": 50, "top": 20},
        {"text": "4.767 in", "left": 200, "top": 20.5},
        {"text": "Connection Data", "left": 10, "top": 100},
        {"text": "Longitudinal Yield Strength", "left": 50, "top": 110},
        {"text": "561,000 lbf", "left": 200, "top": 110},
        {"text": "999,999 decoy", "left": 300, "top": 110},
        {"text": "Compressive Limit", "left": 50, "top": 120},
        {"text": "540,000 lbf", "left": 200, "top": 120},
        {"text": "Internal Pressure Rating", "left": 50, "top": 130},
        {"text": "12,345 psi", "left": 200, "top": 130},
        {"text": "External Pressure Rating", "left": 50, "top": 140},
        {"text": "10,987 psi", "left": 200, "top": 140},
        {"text": "Operational Data", "left": 10, "top": 200},
        {"text": "Longitudinal Yield Strength", "left": 50, "top": 210},
        {"text": "111,111 out of section", "left": 200, "top": 210},
        {"text": "Notes", "left": 10, "top": 300},
    ]


class FakePage:
    def __init__(self) -> None:
        self.goto_calls: list[dict[str, Any]] = []
        self.load_states: list[dict[str, Any]] = []
        self.function_checks: list[dict[str, Any]] = []
        self.evaluate_calls: list[dict[str, Any]] = []
        self.wait_timeouts: list[int] = []
        self.locator_waits: list[dict[str, Any]] = []
        self.locator_clicks: list[str] = []
        self.locator_attributes: dict[tuple[str, str], str | None] = {
            (
                "#MasterDataGrid a.k-button[href*='/ConnectorSheets/GenerateReport/']:has-text('View Datasheet')",
                "href",
            ): "/ConnectorSheets/GenerateReport/123",
        }
        self.report_frame = FakeFrame()
        self.report_frame_handle_available = True
        self.report_content_frame_available = True
        self.timeout = None
        self.navigation_timeout = None
        self.goto_timeout = False
        self.load_state_timeouts: set[str] = set()
        self.selection_failure_input: str | None = None

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
        if self.goto_timeout:
            raise PlaywrightTimeoutError("fake navigation timeout")

    def wait_for_load_state(self, state: str, timeout: int) -> None:
        self.load_states.append({"state": state, "timeout": timeout})
        if state in self.load_state_timeouts:
            raise PlaywrightTimeoutError(f"fake {state} timeout")

    def wait_for_function(
        self,
        script: str,
        arg: Any = None,
        timeout: int = 0,
    ) -> None:
        self.function_checks.append(
            {
                "script": script,
                "arg": arg,
                "timeout": timeout,
            }
        )

    def evaluate(self, script: str, args: dict[str, Any]) -> dict[str, Any]:
        assert "kendoDropDownList" in script
        self.evaluate_calls.append(args)
        if args["inputId"] == self.selection_failure_input:
            return {
                "ok": False,
                "reason": "Option not found",
                "inputId": args["inputId"],
            }
        return {
            "ok": True,
            "inputId": args["inputId"],
            "selectedText": args["targetText"],
            "selectedValue": args["targetText"],
        }

    def wait_for_timeout(self, timeout: int) -> None:
        self.wait_timeouts.append(timeout)

    def locator(self, selector: str) -> "FakeLocator":
        return FakeLocator(self, selector)


class FakeFrame:
    def __init__(self) -> None:
        self.evaluate_calls: list[str] = []
        self.report_blocks = build_report_blocks()
        self.evaluate_failures = 0

    def evaluate(self, script: str) -> list[dict[str, Any]]:
        assert 'document.querySelectorAll("div[data-id]")' in script
        self.evaluate_calls.append(script)
        if self.evaluate_failures:
            self.evaluate_failures -= 1
            raise RuntimeError("fake report frame not ready")
        return self.report_blocks


class FakeElementHandle:
    def __init__(self, page: FakePage) -> None:
        self.page = page

    def content_frame(self) -> FakeFrame | None:
        if not self.page.report_content_frame_available:
            return None
        return self.page.report_frame


class FakeLocator:
    def __init__(self, page: FakePage, selector: str) -> None:
        self.page = page
        self.selector = selector

    @property
    def first(self) -> "FakeLocator":
        return self

    def wait_for(self, state: str, timeout: int) -> None:
        self.page.locator_waits.append(
            {
                "selector": self.selector,
                "state": state,
                "timeout": timeout,
            }
        )

    def click(self) -> None:
        self.page.locator_clicks.append(self.selector)

    def get_attribute(self, name: str) -> str | None:
        return self.page.locator_attributes.get((self.selector, name))

    def element_handle(self) -> FakeElementHandle | None:
        if not self.page.report_frame_handle_available:
            return None
        return FakeElementHandle(self.page)


class FakeContext:
    def __init__(self) -> None:
        self.closed = False
        self.page = FakePage()

    def new_page(self) -> FakePage:
        return self.page

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
    def __init__(self, fail_launch: bool = False) -> None:
        self.fail_launch = fail_launch
        self.launch_args: dict[str, Any] | None = None
        self.browser = FakeBrowser()

    def launch(self, headless: bool, slow_mo: int) -> FakeBrowser:
        self.launch_args = {"headless": headless, "slow_mo": slow_mo}
        if self.fail_launch:
            raise RuntimeError("fake launch failed")
        return self.browser


class FakePlaywright:
    def __init__(self, fail_launch: bool = False) -> None:
        self.chromium = FakeChromium(fail_launch=fail_launch)
        self.started = False
        self.stopped = False

    def start(self) -> "FakePlaywright":
        self.started = True
        return self

    def stop(self) -> None:
        self.stopped = True


def build_mapped_data() -> dict[str, Any]:
    return {
        "partner": "HT",
        "side": "upper",
        "drift_extraction": True,
        "connection": {
            "name": "SLHT",
            "od": "5.500",
            "weight": "17.000",
            "material_family": "13CR",
            "yield_strength": "80",
            "type": "BOX",
        },
    }


def build_adapter(
    logs_dir: Path,
    fake_playwright: FakePlaywright,
) -> HtAdapter:
    return HtAdapter(
        base_url="https://datasheet.hunting-intl.com",
        datasheet_url="https://datasheet.hunting-intl.com/CommercialDatasheets",
        logs_dir=logs_dir,
        headless=True,
        slow_mo=25,
        timeout_ms=1234,
        navigation_timeout_ms=5678,
        playwright_factory=lambda: fake_playwright,
    )


def check_repeated_lifecycle(logs_dir: Path) -> None:
    """Exercise the replaceable browser boundary without network traffic."""
    for _ in range(250):
        fake_playwright = FakePlaywright()
        adapter = build_adapter(logs_dir, fake_playwright)
        adapter.close()
        assert fake_playwright.chromium.browser.context.closed is True
        assert fake_playwright.chromium.browser.closed is True
        assert fake_playwright.stopped is True
        assert adapter._closed is True


def check_repeated_selection(adapter: HtAdapter) -> None:
    """Exercise deterministic selection orchestration without website traffic."""
    page = adapter._require_page()
    start_evaluate_count = len(page.evaluate_calls)

    for _ in range(250):
        adapter._select_search_options(
            connection_type="SEAL-LOCK HT-S",
            od_value="7.000",
            weight_value="29.500",
            material_grade="13CR-95",
        )

    assert len(page.evaluate_calls) - start_evaluate_count == 1250
    assert page.evaluate_calls[-5:] == [
        {
            "inputId": "ConnectionStyle",
            "targetText": "Threaded and Coupled",
            "matchMode": "text",
        },
        {
            "inputId": "ConnectionType",
            "targetText": "SEAL-LOCK HT-S",
            "matchMode": "text",
        },
        {
            "inputId": "OD",
            "targetText": "7.000",
            "matchMode": "numeric",
        },
        {
            "inputId": "NominalWeight",
            "targetText": "29.500",
            "matchMode": "numeric",
        },
        {
            "inputId": "MaterialGrade",
            "targetText": "13CR-95",
            "matchMode": "material",
        },
    ]


def check_repeated_report_opening(
    logs_dir: Path,
) -> None:
    """Exercise deterministic report opening without website traffic."""
    fake_playwright = FakePlaywright()
    adapter = build_adapter(logs_dir, fake_playwright)
    page = fake_playwright.chromium.browser.context.page

    try:
        for _ in range(250):
            adapter._click_filter_and_open_report()
            adapter._wait_for_report_loaded()

        assert len(page.locator_clicks) == 250
        assert len(page.goto_calls) == 250
        assert page.goto_calls[-1]["url"] == (
            "https://datasheet.hunting-intl.com"
            "/ConnectorSheets/GenerateReport/123"
        )
        assert len(page.report_frame.evaluate_calls) == 250
    finally:
        adapter.close()


def check_repeated_extraction(adapter: HtAdapter) -> None:
    """Exercise deterministic report extraction without website traffic."""
    page = adapter._require_page()
    start_evaluate_count = len(page.report_frame.evaluate_calls)

    for _ in range(250):
        result = adapter.extract_required_data(build_mapped_data())
        assert result == {
            "tensile": "561,000",
            "compression": "540,000",
            "burst": "12,345",
            "collapse": "10,987",
            "drift": "4.767",
        }

    assert len(page.report_frame.evaluate_calls) - start_evaluate_count == 1250


def main() -> None:
    with TemporaryDirectory() as tmp_name:
        logs_dir = Path(tmp_name) / "logs"
        fake_playwright = FakePlaywright()
        adapter = build_adapter(logs_dir, fake_playwright)

        try:
            assert fake_playwright.started is True
            assert fake_playwright.chromium.launch_args == {
                "headless": True,
                "slow_mo": 25,
            }
            assert adapter.browser is fake_playwright.chromium.browser
            assert adapter.context is fake_playwright.chromium.browser.context
            assert adapter.page is fake_playwright.chromium.browser.context.page
            assert adapter.page.timeout == 1234
            assert adapter.page.navigation_timeout == 5678

            assert adapter.base_url == "https://datasheet.hunting-intl.com"
            assert adapter.datasheet_url == (
                "https://datasheet.hunting-intl.com/CommercialDatasheets"
            )
            assert adapter.logs_dir == logs_dir
            assert adapter.headless is True
            assert adapter.slow_mo == 25
            assert adapter.timeout_ms == 1234
            assert adapter.navigation_timeout_ms == 5678

            try:
                adapter.run({"partner": "HT", "side": "upper", "connection": {}})
                raise AssertionError("Expected ValueError for incomplete HT data.")
            except ValueError:
                pass

            invalid_partner = build_mapped_data()
            invalid_partner["partner"] = "JFE"
            try:
                adapter.run(invalid_partner)
                raise AssertionError("Expected ValueError for non-HT data.")
            except ValueError:
                pass

            invalid_side = build_mapped_data()
            invalid_side["side"] = "middle"
            try:
                adapter.run(invalid_side)
                raise AssertionError("Expected ValueError for invalid HT side.")
            except ValueError:
                pass

            invalid_type = build_mapped_data()
            invalid_type["connection"]["type"] = "COUPLING"
            try:
                adapter.run(invalid_type)
                raise AssertionError("Expected ValueError for unsupported HT type.")
            except ValueError:
                pass

            assert fake_playwright.chromium.browser.context.page.goto_calls == []

            try:
                adapter.run(build_mapped_data())
                raise AssertionError("Expected NotImplementedError for HT automation.")
            except NotImplementedError as exc:
                assert (
                    str(exc)
                    == "HT blanking report opening is not implemented yet."
                )

            page = fake_playwright.chromium.browser.context.page
            assert page.goto_calls == [
                {
                    "url": (
                        "https://datasheet.hunting-intl.com/CommercialDatasheets"
                    ),
                    "wait_until": "domcontentloaded",
                    "timeout": 5678,
                },
                {
                    "url": (
                        "https://datasheet.hunting-intl.com"
                        "/ConnectorSheets/GenerateReport/123"
                    ),
                    "wait_until": "domcontentloaded",
                    "timeout": 5678,
                },
            ]
            assert page.load_states[:2] == [
                {"state": "load", "timeout": 10000},
                {"state": "networkidle", "timeout": 10000},
            ]
            assert page.load_states[2:] == [
                {"state": "networkidle", "timeout": 5000},
            ] * 5 + [
                {"state": "load", "timeout": 10000},
                {"state": "networkidle", "timeout": 10000},
            ]
            assert [check["timeout"] for check in page.function_checks] == [
                30000,
                30000,
                30000,
                30000,
                30000,
                30000,
                30000,
                30000,
                30000,
            ]
            assert "#ConnectionStyle" in page.function_checks[0]["script"]
            assert "#ConnectionType" in page.function_checks[0]["script"]
            assert "#OD" in page.function_checks[0]["script"]
            assert "#NominalWeight" in page.function_checks[0]["script"]
            assert "#MaterialGrade" in page.function_checks[0]["script"]
            assert page.function_checks[1]["arg"] == "ConnectionStyle"
            assert page.function_checks[2]["arg"] == {
                "inputId": "ConnectionStyle",
                "minCount": 1,
            }
            assert [check["arg"] for check in page.function_checks[3:]] == [
                {"inputId": "ConnectionType", "minCount": 1},
                {"inputId": "OD", "minCount": 1},
                {"inputId": "NominalWeight", "minCount": 1},
                {"inputId": "MaterialGrade", "minCount": 1},
                None,
                None,
            ]
            assert "#result-grid" in page.function_checks[7]["script"]
            assert "/ConnectorSheets/GenerateReport/" in (
                page.function_checks[8]["script"]
            )
            assert page.evaluate_calls == [
                {
                    "inputId": "ConnectionStyle",
                    "targetText": "Threaded and Coupled",
                    "matchMode": "text",
                },
                {
                    "inputId": "ConnectionType",
                    "targetText": "SEAL-LOCK HT",
                    "matchMode": "text",
                },
                {
                    "inputId": "OD",
                    "targetText": "5.500",
                    "matchMode": "numeric",
                },
                {
                    "inputId": "NominalWeight",
                    "targetText": "17.000",
                    "matchMode": "numeric",
                },
                {
                    "inputId": "MaterialGrade",
                    "targetText": "13CR-80",
                    "matchMode": "material",
                },
            ]
            assert page.wait_timeouts == [1200] * 5
            assert page.locator_clicks == [
                "#searchtable a.k-button:has-text('Filter')"
            ]
            assert page.locator_waits == [
                {
                    "selector": "#searchtable a.k-button:has-text('Filter')",
                    "state": "visible",
                    "timeout": 15000,
                },
                {
                    "selector": (
                        "#MasterDataGrid a.k-button"
                        "[href*='/ConnectorSheets/GenerateReport/']"
                        ":has-text('View Datasheet')"
                    ),
                    "state": "visible",
                    "timeout": 30000,
                },
            ] + [
                {
                    "selector": "#ReportViewerReportFrame",
                    "state": "attached",
                    "timeout": 30000,
                },
            ] * 7
            assert len(page.report_frame.evaluate_calls) == 6

            assert adapter.extract_required_data(build_mapped_data()) == {
                "tensile": "561,000",
                "compression": "540,000",
                "burst": "12,345",
                "collapse": "10,987",
                "drift": "4.767",
            }
            no_drift_data = build_mapped_data()
            no_drift_data["drift_extraction"] = False
            assert adapter.extract_required_data(no_drift_data) == {
                "tensile": "561,000",
                "compression": "540,000",
                "burst": "12,345",
                "collapse": "10,987",
                "drift": "NA",
            }
            assert len(page.report_frame.evaluate_calls) == 15
            assert adapter._normalize_report_label("  Connection\u00a0Data: ") == (
                "connection data"
            )
            assert adapter._extract_first_number("value: -1,234.50 psi") == (
                "-1,234.50"
            )

            try:
                adapter._find_report_section_bounds(
                    blocks=build_report_blocks(),
                    section_label="Missing Data",
                )
                raise AssertionError("Expected missing HT report section.")
            except RuntimeError as exc:
                assert str(exc) == "HT report section not found: Missing Data"

            missing_label_blocks = [
                block
                for block in build_report_blocks()
                if block["text"] != "Compressive Limit"
            ]
            try:
                adapter._find_report_label_block(
                    blocks=missing_label_blocks,
                    section_start=100,
                    section_end=200,
                    field_label="Compressive Limit",
                )
                raise AssertionError("Expected missing HT report field label.")
            except RuntimeError as exc:
                assert str(exc) == (
                    "HT report field label not found: Compressive Limit"
                )

            external_label = next(
                block
                for block in build_report_blocks()
                if block["text"] == "External Pressure Rating"
            )
            blocks_without_external_value = [
                block
                for block in build_report_blocks()
                if block["text"] != "10,987 psi"
            ]
            try:
                adapter._find_report_value_for_label(
                    blocks=blocks_without_external_value,
                    label_block=external_label,
                    section_start=100,
                    section_end=200,
                )
                raise AssertionError("Expected missing HT report value.")
            except RuntimeError as exc:
                assert str(exc) == (
                    "HT report value not found for label: "
                    "External Pressure Rating"
                )

            assert adapter._map_connection_type("SLHT") == "SEAL-LOCK HT"
            assert adapter._map_connection_type("HT") == "SEAL-LOCK HT"
            for name in ("SLHT-S", "SLHTS", "HT-S", "HTS"):
                assert adapter._map_connection_type(name) == "SEAL-LOCK HT-S"
            try:
                adapter._map_connection_type("UNKNOWN")
                raise AssertionError("Expected unsupported HT connection name.")
            except ValueError:
                pass

            assert adapter._build_material_grade("13cr", "80.0") == "13CR-80"
            assert adapter._map_material_grade(build_mapped_data()) == "13CR-80"

            page.selection_failure_input = "OD"
            try:
                adapter._select_kendo_dropdown_by_text(
                    input_id="OD",
                    target_text="99.000",
                    match_mode="numeric",
                )
                raise AssertionError("Expected HT option selection failure.")
            except RuntimeError as exc:
                assert "Failed to select HT dropdown option" in str(exc)
            page.selection_failure_input = None

            check_repeated_selection(adapter)
            check_repeated_extraction(adapter)
        finally:
            adapter.close()
            assert fake_playwright.chromium.browser.context.closed is True
            assert fake_playwright.chromium.browser.closed is True
            assert fake_playwright.stopped is True
            assert adapter._closed is True
            adapter.close()

        failed_playwright = FakePlaywright(fail_launch=True)
        try:
            build_adapter(logs_dir, failed_playwright)
            raise AssertionError("Expected browser startup failure.")
        except RuntimeError as exc:
            assert str(exc) == "fake launch failed"
        assert failed_playwright.started is True
        assert failed_playwright.stopped is True

        timeout_playwright = FakePlaywright()
        timeout_adapter = build_adapter(logs_dir, timeout_playwright)
        timeout_page = timeout_playwright.chromium.browser.context.page
        timeout_page.goto_timeout = True
        timeout_page.load_state_timeouts = {"load", "networkidle"}
        timeout_adapter.open_datasheet_page()
        assert len(timeout_page.goto_calls) == 1
        assert timeout_page.load_states == [
            {"state": "load", "timeout": 10000},
            {"state": "networkidle", "timeout": 10000},
        ]
        timeout_adapter.close()

        missing_href_playwright = FakePlaywright()
        missing_href_adapter = build_adapter(logs_dir, missing_href_playwright)
        missing_href_page = missing_href_playwright.chromium.browser.context.page
        missing_href_page.locator_attributes.clear()
        try:
            missing_href_adapter._click_filter_and_open_report()
            raise AssertionError("Expected missing HT datasheet href failure.")
        except RuntimeError as exc:
            assert str(exc) == "HT View Datasheet link found but href is empty."
        missing_href_adapter.close()

        retry_playwright = FakePlaywright()
        retry_adapter = build_adapter(logs_dir, retry_playwright)
        retry_page = retry_playwright.chromium.browser.context.page
        retry_page.report_frame.evaluate_failures = 1
        retry_adapter._wait_for_report_loaded()
        assert retry_page.wait_timeouts == [1000]
        retry_adapter.close()

        incomplete_report_playwright = FakePlaywright()
        incomplete_report_adapter = build_adapter(
            logs_dir,
            incomplete_report_playwright,
        )
        incomplete_report_page = (
            incomplete_report_playwright.chromium.browser.context.page
        )
        incomplete_report_page.report_frame.report_blocks = [
            {"text": "Connection Data"},
        ]
        try:
            incomplete_report_adapter._wait_for_report_loaded()
            raise AssertionError("Expected incomplete HT report failure.")
        except RuntimeError as exc:
            assert str(exc) == "HT report content did not finish loading."
        assert incomplete_report_page.wait_timeouts == [1000] * 45
        incomplete_report_adapter.close()

        check_repeated_report_opening(logs_dir)
        check_repeated_lifecycle(logs_dir)

    print("ht adapter ok")


if __name__ == "__main__":
    main()
