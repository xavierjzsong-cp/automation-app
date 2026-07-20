"""Smoke checks for the JFE adapter navigation flow."""

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


def main() -> None:
    tmp = TemporaryDirectory()
    fake_playwright = FakePlaywright()
    adapter = JfeAdapter(
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

        try:
            adapter.run(build_mapped_data())
            raise AssertionError("Expected NotImplementedError for JFE automation.")
        except NotImplementedError as exc:
            assert str(exc) == "JFE datasheet selection is not implemented yet."

        datasheet_page = fake_playwright.chromium.browser.context.pages[0]
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
        ]
        assert "#datasheet_builder" in datasheet_page.function_checks[0]["script"]
        assert "JFEBEAR" in datasheet_page.function_checks[0]["script"]

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
