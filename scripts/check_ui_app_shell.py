"""Import-safe structure checks for the partial desktop application shell."""

from __future__ import annotations

import inspect
import os
from pathlib import Path
import sys
import tkinter
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

assert tkinter._default_root is None

import customtkinter as ctk  # noqa: E402

from src.ui.app import TemplateAutomationApp  # noqa: E402
from src.ui.styles import AppStyle  # noqa: E402
from src.utils.app_paths import (  # noqa: E402
    configure_playwright_browsers,
    get_ui_settings_path,
)


EXPECTED_METHOD_PARAMETERS = {
    "__init__": ["self"],
    "_build_ui": ["self"],
    "_add_label": ["self", "parent", "text", "row"],
    "_create_entry": ["self", "parent", "variable"],
    "_create_primary_button": [
        "self",
        "parent",
        "text",
        "command",
        "width",
        "height",
    ],
}

EXPECTED_LAYOUT_TEXT = {
    "Template Automation Tool",
    "Input Settings",
    "User Name",
    "Input POTS File",
    "Template Excel File",
    "Target Sheet",
    "Output Folder",
    "Show browser during automation",
    "Generate Template",
    "Open Output Folder",
    "Progress",
    "Ready.",
}


def check_playwright_path_boundary() -> None:
    with TemporaryDirectory() as tmp_name:
        browsers = Path(tmp_name) / "ms-playwright"
        browsers.mkdir()

        with patch(
            "src.utils.app_paths.resource_path",
            return_value=browsers,
        ):
            previous = os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
            try:
                configure_playwright_browsers()
                assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(browsers)
            finally:
                if previous is None:
                    os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
                else:
                    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = previous


def check_shell_structure() -> None:
    assert tkinter._default_root is None
    assert issubclass(TemplateAutomationApp, AppStyle)
    assert issubclass(TemplateAutomationApp, ctk.CTk)
    assert TemplateAutomationApp.SETTINGS_PATH == get_ui_settings_path()
    assert TemplateAutomationApp.TEMPLATE_SHEET_OPTIONS == [
        f"CP_ACCESSORY-{index:02d}"
        for index in range(1, 21)
    ]

    for method_name, expected_parameters in EXPECTED_METHOD_PARAMETERS.items():
        method = getattr(TemplateAutomationApp, method_name)
        assert list(inspect.signature(method).parameters) == expected_parameters

    layout_source = inspect.getsource(TemplateAutomationApp._build_ui)
    for label in EXPECTED_LAYOUT_TEXT:
        assert label in layout_source

    entrypoint = (ROOT_DIR / "run_ui.py").read_text(encoding="utf-8")
    assert "src.ui.app" not in entrypoint
    assert "TemplateGenerationService" in entrypoint
    assert tkinter._default_root is None


def main() -> None:
    check_playwright_path_boundary()
    check_shell_structure()

    for _ in range(1000):
        check_shell_structure()

    print("ui app shell ok")


if __name__ == "__main__":
    main()
