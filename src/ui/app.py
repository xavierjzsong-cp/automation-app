"""Desktop application shell and static layout."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from src.services.template_generation_service import (
    GenerationRequest,
    TemplateGenerationService,
)
from src.ui.styles import AppStyle
from src.utils.app_paths import configure_playwright_browsers, get_ui_settings_path


class TemplateAutomationApp(AppStyle, ctk.CTk):
    """Legacy desktop window while interaction callbacks are restored."""

    SETTINGS_PATH = get_ui_settings_path()

    TEMPLATE_SHEET_OPTIONS = [
        f"CP_ACCESSORY-{index:02d}"
        for index in range(1, 21)
    ]

    def __init__(self) -> None:
        configure_playwright_browsers()

        super().__init__()

        self.title("Template Automation Tool")
        self.geometry("860x680")
        self.minsize(780, 640)
        self.configure(fg_color=self.COLOR_BACKGROUND)

        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")

        self.service = TemplateGenerationService()
        self.last_output_file: str | None = None

        self.user_name_var = ctk.StringVar()
        self.input_pdf_var = ctk.StringVar()
        self.template_file_var = ctk.StringVar()
        self.target_sheet_var = ctk.StringVar(value=self.TEMPLATE_SHEET_OPTIONS[0])
        self.output_dir_var = ctk.StringVar()
        self.show_browser_var = ctk.BooleanVar(value=True)

        self.progress_var = ctk.DoubleVar(value=0)
        self.progress_percent_var = ctk.StringVar(value="0%")

        self.generation_started = False
        self.browser_warmup_started = False
        self.browser_warmup_running = False

        self.target_sheet_dropdown_visible = False
        self.target_sheet_result_widgets: list[ctk.CTkBaseClass] = []

        self._load_settings()
        self._build_ui()

        self.after(1000, self._start_browser_warmup_if_idle)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(
            self,
            corner_radius=0,
            fg_color=self.COLOR_BACKGROUND,
        )
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)

        title = ctk.CTkLabel(
            header,
            text="Template Automation Tool",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=self.COLOR_TEXT,
        )
        title.pack(anchor="w", padx=28, pady=(22, 18))

        main = ctk.CTkFrame(
            self,
            fg_color=self.COLOR_CARD,
            corner_radius=12,
            border_width=1,
            border_color=self.COLOR_BORDER,
        )
        main.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 24))
        main.grid_columnconfigure(1, weight=0)
        main.grid_columnconfigure(2, weight=0)
        main.grid_columnconfigure(3, weight=1)

        for row_index in range(10):
            main.grid_rowconfigure(row_index, weight=0)
        main.grid_rowconfigure(9, weight=1)

        section_title = ctk.CTkLabel(
            main,
            text="Input Settings",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.COLOR_TEXT,
        )
        section_title.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="w",
            padx=24,
            pady=(22, 10),
        )

        self._add_label(main, "User Name", row=1)
        user_entry = self._create_entry(main, self.user_name_var)
        user_entry.grid(row=1, column=1, sticky="w", padx=(14, 24), pady=8)

        self._add_label(main, "Input POTS File", row=2)
        input_entry = self._create_entry(main, self.input_pdf_var)
        input_entry.grid(row=2, column=1, sticky="w", padx=(14, 10), pady=8)
        input_button = self._create_primary_button(
            main,
            text="Browse",
            width=self.BROWSE_BUTTON_WIDTH,
            height=self.BROWSE_BUTTON_HEIGHT,
            command=self._browse_input_pdf,
        )
        input_button.grid(row=2, column=2, sticky="e", padx=(0, 24), pady=8)

        self._add_label(main, "Template Excel File", row=3)
        template_entry = self._create_entry(main, self.template_file_var)
        template_entry.grid(row=3, column=1, sticky="w", padx=(14, 10), pady=8)
        template_button = self._create_primary_button(
            main,
            text="Browse",
            width=self.BROWSE_BUTTON_WIDTH,
            height=self.BROWSE_BUTTON_HEIGHT,
            command=self._browse_template_file,
        )
        template_button.grid(row=3, column=2, sticky="e", padx=(0, 24), pady=8)

        self._add_label(main, "Target Sheet", row=4)

        target_sheet_input_frame = ctk.CTkFrame(
            main,
            width=self.TARGET_SHEET_WIDTH,
            height=self.FIELD_HEIGHT,
            fg_color="transparent",
        )
        target_sheet_input_frame.grid(
            row=4,
            column=1,
            sticky="w",
            padx=(14, 24),
            pady=8,
        )
        target_sheet_input_frame.grid_propagate(False)
        target_sheet_input_frame.grid_columnconfigure(0, weight=1)

        self.target_sheet_entry = ctk.CTkEntry(
            target_sheet_input_frame,
            textvariable=self.target_sheet_var,
            height=self.FIELD_HEIGHT,
            border_color=self.COLOR_BORDER,
            fg_color="#FFFFFF",
            text_color=self.COLOR_TEXT,
        )
        self.target_sheet_entry.grid(row=0, column=0, sticky="ew")

        self.target_sheet_entry.bind(
            "<FocusIn>",
            lambda event: self._show_target_sheet_dropdown(show_all=False),
        )
        self.target_sheet_entry.bind(
            "<KeyRelease>",
            lambda event: self._on_target_sheet_input_changed(),
        )
        self.target_sheet_entry.bind(
            "<Escape>",
            lambda event: self._hide_target_sheet_dropdown(),
        )

        self.target_sheet_dropdown_button = ctk.CTkButton(
            target_sheet_input_frame,
            text="▼",
            width=42,
            height=self.FIELD_HEIGHT,
            fg_color=self.COLOR_PRIMARY,
            hover_color=self.COLOR_PRIMARY_HOVER,
            text_color="#FFFFFF",
            command=self._toggle_target_sheet_dropdown,
        )
        self.target_sheet_dropdown_button.grid(
            row=0,
            column=1,
            sticky="e",
            padx=(8, 0),
        )

        self.target_sheet_dropdown = ctk.CTkFrame(
            main,
            width=self.TARGET_SHEET_WIDTH,
            fg_color="#FFFFFF",
            corner_radius=8,
            border_width=1,
            border_color=self.COLOR_BORDER,
        )
        self.target_sheet_dropdown.grid_columnconfigure(0, weight=1)

        self.target_sheet_results_frame = ctk.CTkScrollableFrame(
            self.target_sheet_dropdown,
            width=self.TARGET_SHEET_WIDTH - 20,
            fg_color="#FFFFFF",
            corner_radius=6,
            height=self.TARGET_SHEET_DROPDOWN_HEIGHT,
        )
        self.target_sheet_results_frame.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=8,
            pady=8,
        )
        self.target_sheet_results_frame.grid_columnconfigure(0, weight=1)

        self._add_label(main, "Output Folder", row=6)
        output_entry = self._create_entry(main, self.output_dir_var)
        output_entry.grid(row=6, column=1, sticky="w", padx=(14, 10), pady=8)
        output_button = self._create_primary_button(
            main,
            text="Browse",
            width=self.BROWSE_BUTTON_WIDTH,
            height=self.BROWSE_BUTTON_HEIGHT,
            command=self._browse_output_dir,
        )
        output_button.grid(row=6, column=2, sticky="e", padx=(0, 24), pady=8)

        options_frame = ctk.CTkFrame(main, fg_color="transparent")
        options_frame.grid(
            row=7,
            column=1,
            columnspan=2,
            sticky="w",
            padx=(14, 24),
            pady=(10, 8),
        )

        show_browser_checkbox = ctk.CTkCheckBox(
            options_frame,
            text="Show browser during automation",
            variable=self.show_browser_var,
            fg_color=self.COLOR_PRIMARY,
            hover_color=self.COLOR_PRIMARY_HOVER,
            border_color=self.COLOR_MUTED,
            text_color=self.COLOR_TEXT,
            command=self._save_settings,
        )
        show_browser_checkbox.pack(anchor="w")

        button_frame = ctk.CTkFrame(main, fg_color="transparent")
        button_frame.grid(
            row=8,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=24,
            pady=(20, 16),
        )
        button_frame.grid_columnconfigure(0, weight=1)

        self.generate_button = self._create_primary_button(
            button_frame,
            text="Generate Template",
            height=self.PRIMARY_BUTTON_HEIGHT,
            command=self._start_generation,
        )
        self.generate_button.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.open_output_button = ctk.CTkButton(
            button_frame,
            text="Open Output Folder",
            height=self.PRIMARY_BUTTON_HEIGHT,
            width=170,
            fg_color=self.COLOR_SECONDARY,
            hover_color="#D7EAF5",
            text_color=self.COLOR_PRIMARY,
            state="disabled",
            command=self._open_output_folder,
        )
        self.open_output_button.grid(row=0, column=1, sticky="e")

        self.progress_card = ctk.CTkFrame(
            main,
            fg_color=self.COLOR_BACKGROUND,
            corner_radius=10,
            border_width=1,
            border_color=self.COLOR_BORDER,
        )
        self.progress_card.grid_columnconfigure(0, weight=1)

        progress_header = ctk.CTkFrame(
            self.progress_card,
            fg_color="transparent",
        )
        progress_header.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=18,
            pady=(16, 6),
        )
        progress_header.grid_columnconfigure(0, weight=1)

        progress_title = ctk.CTkLabel(
            progress_header,
            text="Progress",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.COLOR_TEXT,
        )
        progress_title.grid(row=0, column=0, sticky="w")

        self.progress_percent_label = ctk.CTkLabel(
            progress_header,
            textvariable=self.progress_percent_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.COLOR_PRIMARY,
        )
        self.progress_percent_label.grid(row=0, column=1, sticky="e")

        self.progress_bar = ctk.CTkProgressBar(
            self.progress_card,
            height=self.PROGRESS_BAR_HEIGHT,
            progress_color=self.COLOR_PRIMARY,
            fg_color=self.COLOR_BORDER,
        )
        self.progress_bar.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=18,
            pady=(4, 10),
        )
        self.progress_bar.set(0)

        self.status_message_label = ctk.CTkLabel(
            self.progress_card,
            text="Ready.",
            font=ctk.CTkFont(size=13),
            text_color=self.COLOR_MUTED,
            anchor="w",
            justify="left",
            height=self.STATUS_MESSAGE_HEIGHT,
        )
        self.status_message_label.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=18,
            pady=(0, 16),
        )

    def _add_label(self, parent, text: str, row: int) -> None:
        label = ctk.CTkLabel(
            parent,
            text=text,
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.COLOR_TEXT,
        )
        label.grid(row=row, column=0, sticky="w", padx=(24, 0), pady=8)

    def _create_entry(
        self,
        parent,
        variable: ctk.StringVar,
    ) -> ctk.CTkEntry:
        return ctk.CTkEntry(
            parent,
            textvariable=variable,
            width=self.FIELD_WIDTH,
            height=self.FIELD_HEIGHT,
            border_color=self.COLOR_BORDER,
            fg_color="#FFFFFF",
            text_color=self.COLOR_TEXT,
        )

    def _create_primary_button(
        self,
        parent,
        text: str,
        command,
        width: int | None = None,
        height: int | None = None,
    ) -> ctk.CTkButton:
        button_kwargs = {
            "master": parent,
            "text": text,
            "height": height if height is not None else self.FIELD_HEIGHT,
            "fg_color": self.COLOR_PRIMARY,
            "hover_color": self.COLOR_PRIMARY_HOVER,
            "text_color": "#FFFFFF",
            "command": command,
        }

        if width is not None:
            button_kwargs["width"] = width

        return ctk.CTkButton(**button_kwargs)
