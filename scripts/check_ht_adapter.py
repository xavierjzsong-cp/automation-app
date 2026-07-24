"""Smoke checks for the HT adapter datasheet selection flow."""

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


class FakePage:
    def __init__(self) -> None:
        self.goto_calls: list[dict[str, Any]] = []
        self.load_states: list[dict[str, Any]] = []
        self.function_checks: list[dict[str, Any]] = []
        self.evaluate_calls: list[dict[str, Any]] = []
        self.wait_timeouts: list[int] = []
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
                assert str(exc) == "HT report opening is not implemented yet."

            page = fake_playwright.chromium.browser.context.page
            assert page.goto_calls == [
                {
                    "url": (
                        "https://datasheet.hunting-intl.com/CommercialDatasheets"
                    ),
                    "wait_until": "domcontentloaded",
                    "timeout": 5678,
                }
            ]
            assert page.load_states[:2] == [
                {"state": "load", "timeout": 10000},
                {"state": "networkidle", "timeout": 10000},
            ]
            assert page.load_states[2:] == [
                {"state": "networkidle", "timeout": 5000},
            ] * 5
            assert [check["timeout"] for check in page.function_checks] == [
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
            ]
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

        check_repeated_lifecycle(logs_dir)

    print("ht adapter ok")


if __name__ == "__main__":
    main()
