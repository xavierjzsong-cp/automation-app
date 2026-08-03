"""Import-safety, parity, and repeatability checks for UI styles."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

assert "customtkinter" not in sys.modules

from src.ui import AppStyle  # noqa: E402


EXPECTED_STYLE = {
    "COLOR_BACKGROUND": "#F4F7FA",
    "COLOR_CARD": "#FFFFFF",
    "COLOR_PRIMARY": "#1F5F8B",
    "COLOR_PRIMARY_HOVER": "#174D73",
    "COLOR_SECONDARY": "#EAF4FA",
    "COLOR_TEXT": "#1F2933",
    "COLOR_MUTED": "#64748B",
    "COLOR_BORDER": "#D7E0E7",
    "COLOR_SUCCESS": "#2E7D32",
    "COLOR_ERROR": "#B42318",
    "FIELD_WIDTH": 360,
    "TARGET_SHEET_WIDTH": 360,
    "FIELD_HEIGHT": 34,
    "BROWSE_BUTTON_WIDTH": 90,
    "BROWSE_BUTTON_HEIGHT": 28,
    "PRIMARY_BUTTON_HEIGHT": 42,
    "TARGET_SHEET_DROPDOWN_HEIGHT": 160,
    "TARGET_SHEET_OPTION_HEIGHT": 30,
    "TARGET_SHEET_NO_MATCH_HEIGHT": 34,
    "PROGRESS_BAR_HEIGHT": 14,
    "STATUS_MESSAGE_HEIGHT": 20,
}


def current_style() -> dict[str, str | int]:
    return {
        name: value
        for name, value in vars(AppStyle).items()
        if name.isupper()
    }


def main() -> None:
    assert "customtkinter" not in sys.modules
    assert current_style() == EXPECTED_STYLE

    for _ in range(1000):
        assert current_style() == EXPECTED_STYLE

    print("ui styles ok")


if __name__ == "__main__":
    main()
