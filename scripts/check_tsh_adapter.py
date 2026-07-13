"""Smoke checks for the TSH adapter interface."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.adapters.tsh_adapter import TshAdapter  # noqa: E402


class FakePage:
    def __init__(self) -> None:
        self.goto_calls: list[dict[str, Any]] = []
        self.load_states: list[dict[str, Any]] = []
        self.ready_checks: list[dict[str, Any]] = []
        self.function_checks: list[dict[str, Any]] = []
        self.body_text = """
            Product Datasheet
            Pipe Body Data
            Geometry
            Drift 4.767 in
            Performance
            Connection Data
            Performance
            Joint Yield Strength 561,000 lbf
            Compression Strength 540,000 lbf
            Internal Pressure Capacity 12,345 psi
            External Pressure Capacity 10,987 psi
            Make-Up Torques
        """
        self.timeout = None
        self.navigation_timeout = None

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

    def wait_for_function(
        self,
        script: str,
        arg: int | None = None,
        timeout: int = 0,
    ) -> None:
        if arg is None:
            self.function_checks.append({"timeout": timeout})
        else:
            self.ready_checks.append({"arg": arg, "timeout": timeout})

    def locator(self, selector: str) -> "FakeLocator":
        if selector == "body":
            return FakeLocator(text=self.body_text)
        return FakeLocator()


class FakeLocator:
    def __init__(self, text: str = "") -> None:
        self.text = text

    def inner_text(self, timeout: int) -> str:
        return self.text


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


class RecordingTshAdapter(TshAdapter):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.dropdown_selections: list[dict[str, Any]] = []
        super().__init__(*args, **kwargs)

    def _select_dropdown_by_search(
        self,
        dropdown_index: int,
        search_text: str,
        match_mode: str,
        target_value: str | None = None,
    ) -> None:
        self.dropdown_selections.append(
            {
                "dropdown_index": dropdown_index,
                "search_text": search_text,
                "match_mode": match_mode,
                "target_value": target_value,
            }
        )


def build_mapped_data() -> dict[str, Any]:
    return {
        "partner": "TSH",
        "side": "lower",
        "drift_extraction": True,
        "connection": {
            "name": "WEDGE",
            "od": "5.500",
            "weight": "17.00",
            "material_family": "13CR",
            "yield_strength": "80",
            "type": "PIN",
        },
    }


def main() -> None:
    tmp = TemporaryDirectory()
    fake_playwright = FakePlaywright()
    adapter = RecordingTshAdapter(
        base_url="https://dcp.tenaris.com/en",
        datasheet_url="https://dcp.tenaris.com/Product_Datasheet",
        blanking_url="https://dcp.tenaris.com/BlankingDimensions",
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
        assert adapter.page is fake_playwright.chromium.browser.context.page
        assert adapter.page.timeout == 1234
        assert adapter.page.navigation_timeout == 5678

        assert adapter.base_url == "https://dcp.tenaris.com/en"
        assert adapter.datasheet_url == "https://dcp.tenaris.com/Product_Datasheet"
        assert adapter.blanking_url == "https://dcp.tenaris.com/BlankingDimensions"
        assert adapter.logs_dir == Path(tmp.name)
        assert adapter.headless is True
        assert adapter.slow_mo == 25
        assert adapter.timeout_ms == 1234
        assert adapter.navigation_timeout_ms == 5678

        try:
            adapter.run({"partner": "TSH", "side": "lower", "connection": {}})
            raise AssertionError("Expected ValueError for incomplete TSH data.")
        except ValueError:
            pass

        invalid_type = build_mapped_data()
        invalid_type["connection"]["type"] = "COUPLING"
        try:
            adapter.run(invalid_type)
            raise AssertionError("Expected ValueError for unsupported TSH type.")
        except ValueError:
            pass

        result = adapter.run(build_mapped_data())
        assert result == {
            "tensile": "561,000",
            "compression": "540,000",
            "burst": "12,345",
            "collapse": "10,987",
            "drift": "4.767",
        }

        assert adapter.page.goto_calls == [
            {
                "url": "https://dcp.tenaris.com/Product_Datasheet",
                "wait_until": "domcontentloaded",
                "timeout": 5678,
            }
        ]
        assert adapter.page.load_states == [{"state": "load", "timeout": 10000}]
        assert adapter.page.ready_checks == [{"arg": 4, "timeout": 20000}]
        assert adapter.page.function_checks == [{"timeout": 20000}]
        assert adapter.dropdown_selections == [
            {
                "dropdown_index": 0,
                "search_text": "5.500",
                "match_mode": "exact_or_numeric",
                "target_value": "5.500",
            },
            {
                "dropdown_index": 1,
                "search_text": "17.00",
                "match_mode": "weight_datasheet",
                "target_value": "17.00",
            },
            {
                "dropdown_index": 2,
                "search_text": "13CR 80",
                "match_mode": "grade",
                "target_value": "13CR 80",
            },
            {
                "dropdown_index": 3,
                "search_text": "WEDGE",
                "match_mode": "connection",
                "target_value": "WEDGE",
            },
        ]

        assert adapter._score_exact_or_numeric_option("5.5", "5.500") == 9000
        assert adapter._score_weight_option_datasheet("17.00 LB/FT (16.90, 17.00)", "17.00") == 10000
        assert adapter._score_grade_option("13CR-L80", "13CR 80") is not None
        assert adapter._score_connection_option("TSH WEDGE 523", "WEDGE") is not None
        assert adapter._extract_first_number_after_label(
            "Joint Yield Strength 561,000 lbf",
            "Joint Yield Strength",
        ) == "561,000"

        no_drift_data = build_mapped_data()
        no_drift_data["drift_extraction"] = False
        no_drift_result = adapter.run(no_drift_data)
        assert no_drift_result["drift"] == "NA"

        adapter.open_blanking_page()
        assert adapter.page.goto_calls[-1] == {
            "url": "https://dcp.tenaris.com/BlankingDimensions",
            "wait_until": "domcontentloaded",
            "timeout": 5678,
        }
        assert adapter.page.ready_checks[-1] == {"arg": 3, "timeout": 20000}
    finally:
        adapter.close()
        assert fake_playwright.chromium.browser.context.closed is True
        assert fake_playwright.chromium.browser.closed is True
        assert fake_playwright.stopped is True
        assert adapter._closed is True
        adapter.close()
        tmp.cleanup()

    print("tsh adapter ok")


if __name__ == "__main__":
    main()
