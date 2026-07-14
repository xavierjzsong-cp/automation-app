"""Smoke checks for the JFE adapter interface."""

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
        self.timeout = None
        self.navigation_timeout = None

    def set_default_timeout(self, timeout: int) -> None:
        self.timeout = timeout

    def set_default_navigation_timeout(self, timeout: int) -> None:
        self.navigation_timeout = timeout


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
        base_url="https://productcatalog.jfe-steel.co.jp",
        datasheet_url="https://productcatalog.jfe-steel.co.jp/products/octg/index.php",
        blanking_url="https://productcatalog.jfe-steel.co.jp/products/octg/blanking.php",
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

        assert adapter.base_url == "https://productcatalog.jfe-steel.co.jp"
        assert adapter.datasheet_url == "https://productcatalog.jfe-steel.co.jp/products/octg/index.php"
        assert adapter.blanking_url == "https://productcatalog.jfe-steel.co.jp/products/octg/blanking.php"
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
            assert str(exc) == "JFE automation is not implemented yet."
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
