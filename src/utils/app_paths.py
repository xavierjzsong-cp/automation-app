"""Path helpers for source, bundled resources, and user data."""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "TemplateAutomationTool"


def get_project_root() -> Path:
    """Return the repository root when running from source."""
    return Path(__file__).resolve().parents[2]


def resource_path(relative_path: str | Path) -> Path:
    """Return a path to a source or PyInstaller-bundled resource."""
    base_path = Path(getattr(sys, "_MEIPASS", get_project_root()))
    return base_path / Path(relative_path)


def get_app_data_dir(create: bool = False) -> Path:
    """Return the per-user AppData directory for runtime files."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        path = Path(local_app_data) / APP_NAME
    else:
        path = Path.home() / "AppData" / "Local" / APP_NAME

    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def get_config_dir(create: bool = False) -> Path:
    """Return the per-user config directory."""
    path = get_app_data_dir(create=create) / "config"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def get_logs_dir(create: bool = False) -> Path:
    """Return the per-user log directory."""
    path = get_app_data_dir(create=create) / "logs"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def get_ui_settings_path(create_parent: bool = False) -> Path:
    """Return the per-user UI settings file path."""
    return get_config_dir(create=create_parent) / "ui_settings.json"
