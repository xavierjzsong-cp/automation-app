"""Import-safe structure checks for the partial desktop application shell."""

from __future__ import annotations

import inspect
import json
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


class FakeVariable:
    def __init__(self, value=None) -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


class FakeWidget:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.configure_calls = []
        self.grid_calls = []
        self.grid_remove_calls = 0
        self.destroyed = False

    def configure(self, **kwargs) -> None:
        self.configure_calls.append(kwargs)

    def grid(self, **kwargs) -> None:
        self.grid_calls.append(kwargs)

    def grid_remove(self) -> None:
        self.grid_remove_calls += 1

    def destroy(self) -> None:
        self.destroyed = True


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
    "_browse_input_pdf": ["self"],
    "_browse_template_file": ["self"],
    "_browse_output_dir": ["self"],
    "_toggle_target_sheet_dropdown": ["self"],
    "_show_target_sheet_dropdown": ["self", "show_all"],
    "_hide_target_sheet_dropdown": ["self"],
    "_on_target_sheet_input_changed": ["self"],
    "_refresh_target_sheet_matches": ["self", "show_all"],
    "_get_target_sheet_matches": ["self", "query", "show_all"],
    "_normalize_target_sheet_text": ["self", "value"],
    "_select_target_sheet_option": ["self", "sheet_name"],
    "_load_settings": ["self"],
    "_save_settings": ["self"],
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


def build_app_stub(settings_path: Path) -> TemplateAutomationApp:
    app = TemplateAutomationApp.__new__(TemplateAutomationApp)
    app.SETTINGS_PATH = settings_path
    app.user_name_var = FakeVariable("")
    app.input_pdf_var = FakeVariable("")
    app.template_file_var = FakeVariable("")
    app.target_sheet_var = FakeVariable(app.TEMPLATE_SHEET_OPTIONS[0])
    app.output_dir_var = FakeVariable("")
    app.show_browser_var = FakeVariable(True)
    app.target_sheet_dropdown_visible = False
    app.target_sheet_result_widgets = []
    app.target_sheet_dropdown = FakeWidget()
    app.target_sheet_results_frame = FakeWidget()
    return app


def check_settings_round_trip() -> None:
    with TemporaryDirectory() as tmp_name:
        settings_path = Path(tmp_name) / "config" / "ui_settings.json"
        app = build_app_stub(settings_path)

        app.user_name_var.set("  Test User  ")
        app.input_pdf_var.set("  input.pdf  ")
        app.template_file_var.set("  template.xlsx  ")
        app.target_sheet_var.set("  CP_ACCESSORY-03  ")
        app.output_dir_var.set("  output  ")
        app.show_browser_var.set(False)
        app._save_settings()

        assert json.loads(settings_path.read_text(encoding="utf-8")) == {
            "user_name": "Test User",
            "input_pdf": "input.pdf",
            "template_file": "template.xlsx",
            "target_sheet": "CP_ACCESSORY-03",
            "output_dir": "output",
            "show_browser": False,
        }

        loaded_app = build_app_stub(settings_path)
        loaded_app._load_settings()
        assert loaded_app.user_name_var.get() == "Test User"
        assert loaded_app.input_pdf_var.get() == "input.pdf"
        assert loaded_app.template_file_var.get() == "template.xlsx"
        assert loaded_app.target_sheet_var.get() == "CP_ACCESSORY-03"
        assert loaded_app.output_dir_var.get() == "output"
        assert loaded_app.show_browser_var.get() is False

        settings_path.write_text("not valid json", encoding="utf-8")
        loaded_app.user_name_var.set("unchanged")
        loaded_app._load_settings()
        assert loaded_app.user_name_var.get() == "unchanged"


def check_browse_callbacks() -> None:
    with TemporaryDirectory() as tmp_name:
        app = build_app_stub(Path(tmp_name) / "ui_settings.json")
        save_calls = []
        app._save_settings = lambda: save_calls.append(True)

        with patch(
            "src.ui.app.filedialog.askopenfilename",
            return_value="selected.pdf",
        ) as dialog:
            app._browse_input_pdf()
            dialog.assert_called_once_with(
                title="Select Input POTS PDF",
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            )
        assert app.input_pdf_var.get() == "selected.pdf"

        with patch(
            "src.ui.app.filedialog.askopenfilename",
            return_value="template.xlsx",
        ) as dialog:
            app._browse_template_file()
            dialog.assert_called_once_with(
                title="Select Template Excel File",
                filetypes=[
                    ("Excel files", "*.xlsx *.xlsm *.xltx *.xltm"),
                    ("All files", "*.*"),
                ],
            )
        assert app.template_file_var.get() == "template.xlsx"

        with patch(
            "src.ui.app.filedialog.askdirectory",
            return_value="output",
        ) as dialog:
            app._browse_output_dir()
            dialog.assert_called_once_with(title="Select Output Folder")
        assert app.output_dir_var.get() == "output"
        assert len(save_calls) == 3

        with patch("src.ui.app.filedialog.askopenfilename", return_value=""):
            app._browse_input_pdf()
        assert len(save_calls) == 3


def check_target_sheet_matching() -> None:
    app = build_app_stub(Path("unused.json"))

    assert app._normalize_target_sheet_text(" cp_accessory-03 ") == "CP_ACCESSORY-03"
    assert app._get_target_sheet_matches("") == app.TEMPLATE_SHEET_OPTIONS
    assert app._get_target_sheet_matches("03") == ["CP_ACCESSORY-03"]
    assert app._get_target_sheet_matches("accessory") == app.TEMPLATE_SHEET_OPTIONS
    assert app._get_target_sheet_matches("missing") == []

    all_matches = app._get_target_sheet_matches("missing", show_all=True)
    assert all_matches == app.TEMPLATE_SHEET_OPTIONS
    assert all_matches is not app.TEMPLATE_SHEET_OPTIONS


def check_target_sheet_dropdown() -> None:
    app = build_app_stub(Path("unused.json"))
    previous_widget = FakeWidget()
    app.target_sheet_result_widgets = [previous_widget]
    app.target_sheet_var.set("03")

    with patch("src.ui.app.ctk.CTkButton", side_effect=FakeWidget):
        app._show_target_sheet_dropdown(show_all=False)

    assert previous_widget.destroyed is True
    assert app.target_sheet_dropdown_visible is True
    assert app.target_sheet_dropdown.grid_calls == [
        {
            "row": 5,
            "column": 1,
            "sticky": "w",
            "padx": (14, 24),
            "pady": (0, 8),
        }
    ]
    assert app.target_sheet_results_frame.configure_calls[-1] == {
        "height": app.TARGET_SHEET_OPTION_HEIGHT + 12
    }
    assert len(app.target_sheet_result_widgets) == 1
    assert app.target_sheet_result_widgets[0].kwargs["text"] == "CP_ACCESSORY-03"

    app._toggle_target_sheet_dropdown()
    assert app.target_sheet_dropdown_visible is False
    assert app.target_sheet_dropdown.grid_remove_calls == 1

    app.target_sheet_var.set("missing")
    with (
        patch("src.ui.app.ctk.CTkLabel", side_effect=FakeWidget),
        patch("src.ui.app.ctk.CTkFont", return_value="font"),
    ):
        app._on_target_sheet_input_changed()

    assert app.target_sheet_dropdown_visible is True
    assert app.target_sheet_results_frame.configure_calls[-1] == {
        "height": app.TARGET_SHEET_NO_MATCH_HEIGHT + 10
    }
    assert len(app.target_sheet_result_widgets) == 1
    assert app.target_sheet_result_widgets[0].kwargs["text"] == "No predefined match."

    save_calls = []
    app._save_settings = lambda: save_calls.append(True)
    app._select_target_sheet_option("CP_ACCESSORY-07")
    assert app.target_sheet_var.get() == "CP_ACCESSORY-07"
    assert app.target_sheet_dropdown_visible is False
    assert save_calls == [True]


def main() -> None:
    check_playwright_path_boundary()
    check_shell_structure()
    check_settings_round_trip()
    check_browse_callbacks()
    check_target_sheet_matching()
    check_target_sheet_dropdown()

    for _ in range(1000):
        check_shell_structure()

    print("ui app shell ok")


if __name__ == "__main__":
    main()
