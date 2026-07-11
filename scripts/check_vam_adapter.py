"""Smoke checks for the VAM adapter."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.adapters.vam_adapter import VamAdapter  # noqa: E402


class FakeButton:
    def __init__(self, visible: bool) -> None:
        self.visible = visible
        self.clicked = False

    @property
    def first(self) -> "FakeButton":
        return self

    def is_visible(self, timeout: int) -> bool:
        return self.visible

    def click(self, force: bool) -> None:
        self.clicked = True


class FakePage:
    def __init__(self) -> None:
        self.timeout = None
        self.goto_calls: list[dict[str, Any]] = []
        self.load_states: list[dict[str, Any]] = []
        self.waits: list[int] = []
        self.role_queries: list[dict[str, Any]] = []
        self.cookie_button = FakeButton(visible=True)

    def set_default_timeout(self, timeout: int) -> None:
        self.timeout = timeout

    def goto(self, url: str, wait_until: str) -> None:
        self.goto_calls.append({"url": url, "wait_until": wait_until})

    def wait_for_load_state(self, state: str, timeout: int | None = None) -> None:
        self.load_states.append({"state": state, "timeout": timeout})

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)

    def get_by_role(self, role: str, name: str, exact: bool) -> FakeButton:
        self.role_queries.append({"role": role, "name": name, "exact": exact})
        if role == "button" and name == "Accept" and exact is True:
            return self.cookie_button
        return FakeButton(visible=False)


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


class RecordingVamAdapter(VamAdapter):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.connection_calls: list[str] = []
        self.cds_pages: list[object] = []
        self.dropdown_calls: list[tuple[str, str]] = []
        self.grade_calls: list[tuple[str | None, str | None]] = []
        self.open_result_cds_calls: list[int] = []
        self.wait_for_cds_content_loaded_calls: list[object] = []
        self.wait_for_results_calls = 0
        super().__init__(*args, **kwargs)

    def select_dropdown_option_by_index(
        self,
        field_label: str,
        option_text: str,
    ) -> None:
        self.dropdown_calls.append((field_label, option_text))

    def select_grade_option_if_available(
        self,
        material_family: str | None,
        yield_strength: str | None,
    ) -> bool:
        self.grade_calls.append((material_family, yield_strength))
        return True

    def select_connection(self, connection_name: str) -> None:
        self.connection_calls.append(connection_name)

    def wait_for_results(self) -> None:
        self.wait_for_results_calls += 1

    def open_result_cds(self, result_index: int = 0) -> object:
        cds_page = object()
        self.cds_pages.append(cds_page)
        self.open_result_cds_calls.append(result_index)
        return cds_page

    def _wait_for_cds_content_loaded(self, cds_page: object) -> None:
        self.wait_for_cds_content_loaded_calls.append(cds_page)


def build_mapped_data() -> dict[str, Any]:
    return {
        "partner": "VAM",
        "side": "upper",
        "drift_extraction": True,
        "connection": {
            "name": "TOP",
            "od": "5-1/2",
            "weight": "17.00",
            "material_family": "13CR",
            "yield_strength": "80",
            "type": "BOX",
        },
    }


def main() -> None:
    mapped = build_mapped_data()
    tmp = TemporaryDirectory()
    fake_playwright = FakePlaywright()
    adapter = RecordingVamAdapter(
        base_url="https://www.vamservices.com",
        configurator_url="https://www.vamservices.com/product/configurator",
        logs_dir=Path(tmp.name),
        headless=True,
        slow_mo=25,
        timeout_ms=1234,
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

        try:
            adapter.run({"partner": "VAM", "side": "upper", "connection": {}})
            raise AssertionError("Expected ValueError for incomplete VAM data.")
        except ValueError:
            pass

        try:
            adapter.run(mapped)
            raise AssertionError("Expected NotImplementedError for VAM automation.")
        except NotImplementedError as exc:
            assert str(exc) == "VAM data extraction is not implemented yet."

        assert adapter.page.goto_calls == [
            {
                "url": "https://www.vamservices.com/product/configurator",
                "wait_until": "domcontentloaded",
            }
        ]
        assert adapter.page.load_states == [
            {"state": "networkidle", "timeout": None}
        ]
        assert adapter.page.cookie_button.clicked is True
        assert adapter.page.waits == [1000]

        assert adapter.dropdown_calls == [
            ("OD (in)", "5-1/2"),
            ("Weight / WT (lb/ft)", "17.00"),
            ("Pipe specification", "API"),
            ("Material Family", "Carbon Steel"),
            ("Yield Strength (ksi)", "80"),
            ("Drift Option", "API Drift"),
        ]
        assert adapter.grade_calls == [("13CR", "80")]
        assert adapter.connection_calls == ["TOP"]
        assert adapter.wait_for_results_calls == 1
        assert adapter.open_result_cds_calls == [0]
        assert adapter.wait_for_cds_content_loaded_calls == adapter.cds_pages
        assert adapter._grade_option_matches("API 13CR 80", "13CR", "80")
        assert adapter._grade_option_matches("13CR 80 ksi", "13CR", "80.0")
        assert not adapter._grade_option_matches("Carbon Steel 80", "13CR", "80")
    finally:
        adapter.close()
        assert fake_playwright.chromium.browser.context.closed is True
        assert fake_playwright.chromium.browser.closed is True
        assert fake_playwright.stopped is True
        adapter.close()
        tmp.cleanup()

    print("vam adapter ok")


if __name__ == "__main__":
    main()
