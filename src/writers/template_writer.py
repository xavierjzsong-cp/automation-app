"""Excel template writer for parsed POTS data."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any
import logging
import re

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell


logger = logging.getLogger(__name__)


class TemplateWriter:
    """Write parsed POTS fields into a selected Excel template sheet."""

    NA_VALUES = {"NA", "N/A"}

    def write(
        self,
        parsed: Any,
        top_adapter: dict[str, Any] | None = None,
        bottom_adapter: dict[str, Any] | None = None,
        template_path: str | Path | None = None,
        output_dir: str | Path | None = None,
        user_name: str | None = None,
        coating_data: dict[str, Any] | None = None,
        target_sheet_name: str | None = None,
    ) -> dict[str, Any]:
        """Write available parsed fields to the requested target sheet."""
        if template_path is None:
            raise ValueError("template_path is required.")
        if output_dir is None:
            raise ValueError("output_dir is required.")

        parsed_data = self._to_mapping(parsed)
        formatted = self._build_template_fields(
            parsed=parsed_data,
            top_adapter=top_adapter,
            bottom_adapter=bottom_adapter,
            user_name=user_name,
            coating_data=coating_data,
        )

        output_file = self._write_to_template(
            template_path=template_path,
            formatted=formatted,
            output_dir=output_dir,
            target_sheet_name=target_sheet_name,
        )

        return {
            "parsed": parsed_data,
            "formatted": formatted,
            "output_file": str(output_file),
            "target_sheet_name": target_sheet_name,
        }

    def _build_template_fields(
        self,
        parsed: dict[str, Any],
        top_adapter: dict[str, Any] | None,
        bottom_adapter: dict[str, Any] | None,
        user_name: str | None,
        coating_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        connections = parsed.get("connections") or {}
        upper = connections.get("upper") or {}
        lower = connections.get("lower") or {}

        top_thread_text = self._format_thread(
            od=self._get_value(upper, "od"),
            weight=self._get_value(upper, "weight"),
            family=self._get_value(upper, "family"),
            connection_name=self._get_value(upper, "name"),
            connection_type=self._get_value(upper, "type"),
        )
        bottom_thread_text = self._format_thread(
            od=self._get_value(lower, "od"),
            weight=self._get_value(lower, "weight"),
            family=self._get_value(lower, "family"),
            connection_name=self._get_value(lower, "name"),
            connection_type=self._get_value(lower, "type"),
        )

        material = self._format_material(
            mds=parsed.get("ansi_nace"),
            grade=parsed.get("product_material_grade"),
        )

        return {
            "user_name": self._format_user_name(user_name),
            "part_number": parsed.get("part_number"),
            "rev": parsed.get("rev"),
            "qcp": self._format_qcp(parsed.get("qcp")),
            "product_type": parsed.get("product_type"),
            "description": self._format_description(
                top_thread=top_thread_text,
                bottom_thread=bottom_thread_text,
                material=material,
            ),
            "material": material,
            "overall_length": self._format_overall_length(parsed.get("overall_length")),
            "coating": coating_data or {},
            "top_thread": {
                "thread": top_thread_text,
                **(top_adapter or {}),
            },
            "bottom_thread": {
                "thread": bottom_thread_text,
                **(bottom_adapter or {}),
            },
        }

    def _write_to_template(
        self,
        template_path: str | Path,
        formatted: dict[str, Any],
        output_dir: str | Path,
        target_sheet_name: str | None,
    ) -> Path:
        template_path = Path(template_path)
        output_dir = Path(output_dir)

        if not template_path.exists():
            raise FileNotFoundError(f"Template file not found: {template_path}")

        output_dir.mkdir(parents=True, exist_ok=True)
        workbook = load_workbook(template_path)
        sheet = self._get_target_sheet(workbook, target_sheet_name)

        self._write_if_editable(sheet, "G1", formatted.get("user_name"))
        self._write_if_editable(sheet, "B6", formatted.get("part_number"))
        self._write_if_editable(sheet, "D6", formatted.get("rev"))
        self._write_if_editable(sheet, "B8", formatted.get("product_type"))
        self._write_if_editable(sheet, "B18", formatted.get("material"))
        self._write_if_editable(sheet, "B28", (formatted.get("top_thread") or {}).get("thread"))
        self._write_if_editable(sheet, "B30", (formatted.get("bottom_thread") or {}).get("thread"))
        self._write_if_editable(sheet, "B34", formatted.get("qcp"))
        self._write_if_editable(sheet, "H9", formatted.get("overall_length"))

        part_number = formatted.get("part_number")
        if not part_number:
            raise ValueError("part_number is missing, cannot name output file.")

        output_file = output_dir / f"{part_number}.xlsx"
        workbook.save(output_file)
        logger.info("Saved template output: %s", output_file)
        return output_file

    def _get_target_sheet(self, workbook: Any, target_sheet_name: str | None) -> Any:
        target_sheet_name = str(target_sheet_name or "").strip()
        if not target_sheet_name:
            raise ValueError("Target sheet name is required.")

        if target_sheet_name not in workbook.sheetnames:
            available_sheets = ", ".join(workbook.sheetnames)
            raise ValueError(
                f"Target sheet not found in template: {target_sheet_name}. "
                f"Available sheets: {available_sheets}"
            )

        return workbook[target_sheet_name]

    def _write_if_editable(self, sheet: Any, cell_ref: str, value: Any) -> None:
        if value is None:
            return
        if not self._is_cell_editable(sheet, cell_ref):
            return
        sheet[cell_ref] = value

    def _is_cell_editable(self, sheet: Any, cell_ref: str) -> bool:
        cell = sheet[cell_ref]
        if isinstance(cell, MergedCell):
            return False

        current_value = cell.value
        if isinstance(current_value, str):
            normalized = current_value.strip().upper()
            if normalized in self.NA_VALUES:
                return False

        return True

    def _format_thread(
        self,
        od: str | None,
        weight: str | None,
        family: str | None,
        connection_name: str | None,
        connection_type: str | None,
    ) -> str | None:
        if not od or not weight or not connection_name or not connection_type:
            return None

        connection_label = self._format_connection_label(
            family=family,
            connection_name=connection_name,
            connection_type=connection_type,
        )
        if not connection_label:
            return None

        return f"{od} - {weight}# {connection_label}"

    def _format_connection_label(
        self,
        family: str | None,
        connection_name: str | None,
        connection_type: str | None,
    ) -> str | None:
        normalized_name = self._normalize_connection_name(connection_name)
        normalized_type = str(connection_type or "").strip().upper()
        normalized_family = str(family or "").strip().upper()

        if not normalized_name or not normalized_type:
            return None

        parts: list[str] = []
        if normalized_family and normalized_family != "HT":
            parts.append(normalized_family)
        parts.append(normalized_name)
        parts.append(normalized_type)
        return " ".join(parts)

    def _normalize_connection_name(self, connection_name: str | None) -> str | None:
        if not connection_name:
            return None

        text = str(connection_name).strip()
        text = re.sub(r"\bWEDGE\b", "W", text, flags=re.IGNORECASE)
        text = re.sub(r"\bW\s+(\d+)\b", r"W\1", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()
        return text or None

    def _format_user_name(self, user_name: str | None) -> str | None:
        if not user_name:
            return None

        name = re.sub(r"\s+", " ", str(user_name).strip())
        if not name:
            return None

        today_text = date.today().strftime("%d-%m-%Y")
        return f"{name.upper()} ({today_text})"

    def _format_material(self, mds: str | None, grade: str | None) -> str | None:
        if not mds and not grade:
            return None

        normalized_grade = self._normalize_grade(grade) if grade else None
        if mds and normalized_grade:
            return f"{mds} ({normalized_grade})"
        if mds:
            return mds
        return normalized_grade

    def _normalize_grade(self, grade: str) -> str:
        text = grade.strip()
        match = re.match(r"^([A-Za-z0-9]+)\(([\d.]+)\)$", text)
        if match:
            material_family = match.group(1)
            strength = match.group(2)
            return f"{material_family}-{strength}KSI"
        return text

    def _format_qcp(self, qcp: str | None) -> str | None:
        if not qcp:
            return None

        text = qcp.strip()
        text = re.sub(r"\bSTANDARD\b", "STD", text, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", text).strip() or None

    def _format_description(
        self,
        top_thread: str | None,
        bottom_thread: str | None,
        material: str | None,
    ) -> str | None:
        thread_part = None
        if top_thread and bottom_thread:
            thread_part = f"{top_thread} x {bottom_thread}"
        elif top_thread:
            thread_part = top_thread
        elif bottom_thread:
            thread_part = bottom_thread

        if thread_part and material:
            return f"{thread_part}, {material}"
        return thread_part or material

    def _format_overall_length(self, overall_length: str | None) -> str | None:
        if not overall_length:
            return None

        match = re.search(r"(\d+(?:\.\d+)?)", str(overall_length))
        if not match:
            return None

        value = float(match.group(1))
        return f"{value:.3f} +/-.125"

    def _to_mapping(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if is_dataclass(value):
            return asdict(value)
        raise TypeError(f"Unsupported parsed data type: {type(value)!r}")

    def _get_value(self, source: Any, key: str) -> Any:
        if isinstance(source, dict):
            return source.get(key)
        return getattr(source, key, None)
