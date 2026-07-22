"""Smoke and lifecycle repeatability checks for the HT adapter interface."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.adapters.ht_adapter import HtAdapter  # noqa: E402


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

            try:
                adapter.run(build_mapped_data())
                raise AssertionError("Expected NotImplementedError for HT automation.")
            except NotImplementedError as exc:
                assert str(exc) == "HT automation is not implemented yet."
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

        check_repeated_lifecycle(logs_dir)

    print("ht adapter ok")


if __name__ == "__main__":
    main()
