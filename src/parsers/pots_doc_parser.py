"""Parser for POTS PDF content."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import logging
import re
from typing import Any

import fitz


logger = logging.getLogger(__name__)


@dataclass
class ParsedConnection:
    """Connection data extracted from a product description."""

    name: str | None = None
    od: str | None = None
    weight: str | None = None
    family: str | None = None
    type: str | None = None


@dataclass
class ParsedPotsDocument:
    """Structured POTS data used by downstream generation steps."""

    source_file: str | None = None
    part_number: str | None = None
    rev: str | None = None
    product_type: str | None = None
    product_material_grade: str | None = None
    product_description: str | None = None
    ansi_nace: str | None = None
    qcp: str | None = None
    overall_length: str | None = None
    connections: dict[str, ParsedConnection | None] = field(
        default_factory=lambda: {"upper": None, "lower": None}
    )
    parse_warnings: list[str] = field(default_factory=list)
    raw_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a dict compatible with service and writer code."""
        return asdict(self)


class PotsDocParser:
    """Extract basic structured fields from POTS document text or PDF."""

    PARTNER_ALIASES = {
        "VAM": ["VAM"],
        "TSH": ["TSH", "TENARIS", "TENARIS HYDRIL", "TENARISHYDRIL"],
        "JFE": ["JFE"],
        "HT": ["SLHT-S", "SLHT", "HUNTING"],
    }

    MATERIAL_FAMILY_PATTERN = r"(?:SUPER\s*)?S?13CR|13CR|41\d{2}|INCOLLOY|INCOL"
    MATERIAL_GRADE_PATTERNS = [
        rf"\b(?P<family>{MATERIAL_FAMILY_PATTERN})\s*[\(\[]\s*(?P<grade>\d+(?:\.\d+)?)\s*(?:KSI)?\s*[\)\]]",
        rf"\b(?P<family>{MATERIAL_FAMILY_PATTERN})\s*[- ]+\s*(?P<grade>\d+(?:\.\d+)?)\s*KSI\b",
        rf"\b(?P<family>{MATERIAL_FAMILY_PATTERN})\s*[- ]+\s*(?P<grade>\d{{2,4}}(?:\.\d+)?)\b",
        r"\b(?P<family>(?:SUPER\s*)?S?13CR|13CR)\s*(?P<grade>\d{2,3}(?:\.\d+)?)\b",
    ]

    def parse_pdf(self, pdf_path: str | Path, max_pages: int = 2) -> ParsedPotsDocument:
        """Read the first pages of a PDF and parse its text."""
        pdf_path = Path(pdf_path)
        text = self._extract_text_from_pdf(pdf_path, max_pages=max_pages)
        parsed = self.parse_text(text)
        parsed.source_file = str(pdf_path)
        return parsed

    def parse(self, input_path: str | Path) -> ParsedPotsDocument:
        """Compatibility wrapper for parsing a POTS PDF path."""
        return self.parse_pdf(input_path)

    def parse_text(self, text: str) -> ParsedPotsDocument:
        """Parse POTS fields from extracted or fixture text."""
        cleaned_text = self._normalize_text(text)
        warnings: list[str] = []

        product_description = self._extract_product_description(cleaned_text)
        normalized_description = (
            self._normalize_description_text(product_description)
            if product_description
            else None
        )

        product_material_grade = (
            self._extract_material_grade(normalized_description)
            or self._normalize_material_grade(
                self._extract_field_value(
                    cleaned_text,
                    ["Product Material Grade", "Material Grade"],
                )
            )
        )

        overall_length = (
            self._extract_overall_length(normalized_description)
            or self._extract_field_value(cleaned_text, ["Overall Length"])
        )

        product_type = self._extract_field_value(cleaned_text, ["Product Type"])
        if not product_type and normalized_description:
            product_type = self._extract_product_type_guess(normalized_description)

        connections = self._parse_connections(
            normalized_description,
            product_type,
            warnings,
        )

        result = ParsedPotsDocument(
            part_number=self._extract_field_value(
                cleaned_text,
                ["CP Part Number", "Part Number"],
            ),
            rev=self._extract_rev(cleaned_text),
            product_type=product_type,
            product_material_grade=product_material_grade,
            product_description=product_description,
            ansi_nace=self._extract_field_value(
                cleaned_text,
                ["ANSI/NACE MR0175/ISO 15156 (Yes/No)", "ANSI/NACE"],
            ),
            qcp=self._extract_field_value(
                cleaned_text,
                ["QCP (Standard/Client Specific)", "QCP"],
            ),
            overall_length=overall_length,
            connections=connections,
            raw_text=cleaned_text,
        )

        self._add_missing_field_warnings(result, warnings)
        result.parse_warnings = warnings
        return result

    def _extract_text_from_pdf(self, pdf_path: Path, max_pages: int) -> str:
        if not pdf_path.exists():
            raise FileNotFoundError(f"POTS PDF not found: {pdf_path}")

        if pdf_path.suffix.lower() != ".pdf":
            raise ValueError(f"POTS input must be a PDF file: {pdf_path}")

        logger.info("Reading POTS PDF: %s", pdf_path)
        document = fitz.open(pdf_path)
        try:
            page_texts = [
                document[page_index].get_text("text")
                for page_index in range(min(max_pages, len(document)))
            ]
        finally:
            document.close()

        return "\n".join(page_texts)

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\u00a0", " ")
        text = text.replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{2,}", "\n", text)
        return text.strip()

    def _normalize_description_text(self, text: str | None) -> str | None:
        if not text:
            return None

        replacements = {
            "“": '"',
            "”": '"',
            "″": '"',
            "＂": '"',
            "’": "'",
            "‘": "'",
            "–": "-",
            "—": "-",
            "×": " X ",
        }

        normalized = text.strip()
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)

        normalized = normalized.upper()
        normalized = re.sub(r"\s+[X]\s+", " X ", normalized)
        normalized = re.sub(r"\b(BOX|PIN)\s*X(?=\s*\d)", r"\1 X ", normalized)
        normalized = re.sub(r"(\d)(IN\b)", r"\1 \2", normalized)
        normalized = normalized.replace(",", " , ")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _extract_field_value(self, text: str, field_names: list[str]) -> str | None:
        for field_name in field_names:
            escaped = re.escape(field_name)
            patterns = [
                rf"{escaped}\s*[:\-]?\s*(.+?)(?:\n|$)",
                rf"{escaped}\s+(.+?)(?:\n|$)",
            ]
            for pattern in patterns:
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if match:
                    return self._clean_value(match.group(1))
        return None

    def _extract_rev(self, text: str) -> str | None:
        patterns = [
            r"POTS Document number:\s*\d+\s+Rev:\s*([A-Za-z0-9\-]+)",
            r"\bRev(?:ision)?\s*[:\-]?\s*([A-Za-z0-9\-]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _extract_product_description(self, text: str) -> str | None:
        block_pattern = (
            r"Product Description\s*[:\-]?\s*(.+?)\s+"
            r"ANSI/NACE MR0175/ISO 15156 \(Yes/No\)"
        )
        match = re.search(block_pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return self._clean_value(match.group(1))

        return self._extract_field_value(text, ["Product Description"])

    def _extract_product_type_guess(self, description: str) -> str | None:
        marker_patterns = [
            *self.MATERIAL_GRADE_PATTERNS,
            r"\b\d+(?:\.\d+)?(?:\s+\d+/\d+)?\s*(?:\"|IN|INCH)?\s+\d+(?:\.\d+)?\s*#?\b",
        ]

        first_marker_index: int | None = None
        for pattern in marker_patterns:
            match = re.search(pattern, description, flags=re.IGNORECASE)
            if match and (first_marker_index is None or match.start() < first_marker_index):
                first_marker_index = match.start()

        if first_marker_index is None or first_marker_index <= 0:
            return None

        candidate = description[:first_marker_index].strip(" ,;-")
        return candidate or None

    def _extract_material_grade(self, text: str | None) -> str | None:
        if not text:
            return None

        for pattern in self.MATERIAL_GRADE_PATTERNS:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                family = self._normalize_material_family(match.group("family"))
                grade = self._clean_number(match.group("grade"))
                return f"{family}({grade})"

        return None

    def _normalize_material_grade(self, value: str | None) -> str | None:
        if not value:
            return None

        text = self._normalize_description_text(value)
        return self._extract_material_grade(text) or self._clean_value(value)

    def _extract_overall_length(self, text: str | None) -> str | None:
        if not text:
            return None

        patterns = [
            r"\bOAL\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:\"|IN|INCH)?\b",
            r"\bOVERALL\s+LENGTH\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:\"|IN|INCH)?\b",
            r"\bBASED\s+ON\s+(\d+(?:\.\d+)?)\s*(?:\"|IN|INCH)?\s+LONG\b",
            r"\b(\d+(?:\.\d+)?)\s*(?:\"|IN|INCH)\s+LONG\b",
            r"\b(\d+(?:\.\d+)?)\s+LONG\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return self._clean_number(match.group(1))

        return None

    def _parse_connections(
        self,
        description: str | None,
        product_type: str | None,
        warnings: list[str],
    ) -> dict[str, ParsedConnection | None]:
        connections: dict[str, ParsedConnection | None] = {
            "upper": None,
            "lower": None,
        }

        if not description:
            warnings.append("Product description was not found.")
            return connections

        connection_text = self._remove_global_description_fields(
            text=description,
            product_type=product_type,
        )
        segments = self._split_connection_segments(connection_text)

        if len(segments) < 2:
            warnings.append(
                f"Expected 2 connection segments, but found {len(segments)}."
            )

        if len(segments) >= 1:
            connections["upper"] = self._build_connection(segments[0], warnings)
        if len(segments) >= 2:
            connections["lower"] = self._build_connection(segments[1], warnings)

        return connections

    def _remove_global_description_fields(
        self,
        text: str,
        product_type: str | None,
    ) -> str:
        cleaned = text

        if product_type:
            cleaned = re.sub(
                rf"^\s*{re.escape(product_type)}\b",
                " ",
                cleaned,
                count=1,
                flags=re.IGNORECASE,
            )

        for pattern in self.MATERIAL_GRADE_PATTERNS:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

        overall_length_patterns = [
            r"\bOAL\s*[:\-]?\s*\d+(?:\.\d+)?\s*(?:\"|IN|INCH)?\b",
            r"\bOVERALL\s+LENGTH\s*[:\-]?\s*\d+(?:\.\d+)?\s*(?:\"|IN|INCH)?\b",
            r"\bBASED\s+ON\s+\d+(?:\.\d+)?\s*(?:\"|IN|INCH)?\s+LONG\b",
            r"\b\d+(?:\.\d+)?\s*(?:\"|IN|INCH)\s+LONG\b",
            r"\b\d+(?:\.\d+)?\s+LONG\b",
        ]
        for pattern in overall_length_patterns:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

        cleaned = cleaned.replace(",", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _split_connection_segments(self, text: str) -> list[str]:
        if not text:
            return []

        return [
            segment.strip(" ,;-")
            for segment in re.split(r"\s+\bX\b\s+", text, maxsplit=1)
            if segment.strip(" ,;-")
        ]

    def _build_connection(
        self,
        segment: str,
        warnings: list[str],
    ) -> ParsedConnection:
        od, weight, od_weight_span = self._extract_od_and_weight(segment)
        connection_type = self._extract_connection_type(segment)
        family = self._extract_connection_family(segment)
        name = self._extract_connection_name(
            segment=segment,
            od_weight_span=od_weight_span,
            connection_type=connection_type,
            family=family,
        )

        if od is None:
            warnings.append(f"Could not extract OD from connection segment: {segment}")
        if weight is None:
            warnings.append(f"Could not extract weight from connection segment: {segment}")
        if connection_type is None:
            warnings.append(f"Could not extract BOX/PIN from connection segment: {segment}")
        if family is None:
            warnings.append(f"Could not extract partner family from connection segment: {segment}")
        if name is None:
            warnings.append(f"Could not extract connection name from connection segment: {segment}")

        return ParsedConnection(
            name=name,
            od=od,
            weight=weight,
            family=family,
            type=connection_type,
        )

    def _extract_od_and_weight(
        self,
        segment: str,
    ) -> tuple[str | None, str | None, tuple[int, int] | None]:
        pattern = re.compile(
            r"""
            (?P<od>
                \d+(?:\.\d+)?
                (?:\s+\d+/\d+)?
            )
            \s*
            (?:"|IN|INCH)?
            \s+
            (?P<weight>\d+(?:\.\d+)?)
            \s*
            \#?
            """,
            flags=re.IGNORECASE | re.VERBOSE,
        )

        match = pattern.search(segment)
        if not match:
            return None, None, None

        od = self._clean_value(match.group("od"))
        weight = self._clean_number(match.group("weight"))
        return od, weight, match.span()

    def _extract_connection_type(self, segment: str) -> str | None:
        matches = re.findall(r"\b(BOX|PIN)\b", segment, flags=re.IGNORECASE)
        if not matches:
            return None
        return matches[-1].upper()

    def _extract_connection_family(self, segment: str) -> str | None:
        text = segment.upper()
        for family, aliases in self.PARTNER_ALIASES.items():
            for alias in aliases:
                if re.search(rf"\b{re.escape(alias.upper())}\b", text):
                    return family
        return None

    def _extract_connection_name(
        self,
        segment: str,
        od_weight_span: tuple[int, int] | None,
        connection_type: str | None,
        family: str | None,
    ) -> str | None:
        name = segment

        if od_weight_span is not None:
            start, end = od_weight_span
            name = segment[:start] + " " + segment[end:]

        name = name.replace('"', " ")
        name = name.replace("#", " ")

        if connection_type:
            name = re.sub(
                rf"\b{re.escape(connection_type)}\b",
                " ",
                name,
                flags=re.IGNORECASE,
            )

        if family:
            for alias in self.PARTNER_ALIASES.get(family, []):
                if family == "HT" and alias.upper() in {"SLHT", "SLHT-S"}:
                    continue
                name = re.sub(
                    rf"\b{re.escape(alias.upper())}\b",
                    " ",
                    name,
                    flags=re.IGNORECASE,
                )

        name = re.sub(r"\bX\b", " ", name, flags=re.IGNORECASE)
        name = re.sub(r"\s+", " ", name).strip(" ,;-")
        return name or None

    def _add_missing_field_warnings(
        self,
        result: ParsedPotsDocument,
        warnings: list[str],
    ) -> None:
        field_labels = {
            "part_number": "Part number",
            "rev": "Revision",
            "product_description": "Product description",
            "product_material_grade": "Product material grade",
            "qcp": "QCP",
            "overall_length": "Overall length",
        }

        for field_name, label in field_labels.items():
            if getattr(result, field_name) is None:
                warnings.append(f"{label} was not found.")

        if result.connections.get("upper") is None:
            warnings.append("Upper connection was not found.")
        if result.connections.get("lower") is None:
            warnings.append("Lower connection was not found.")

    def _normalize_material_family(self, family: str) -> str:
        return re.sub(r"\s+", "", family.upper())

    def _clean_number(self, value: str) -> str:
        value = value.strip()
        try:
            number = float(value)
        except ValueError:
            return value

        if number.is_integer():
            return str(int(number))
        return f"{number:.6f}".rstrip("0").rstrip(".")

    def _clean_value(self, value: str | None) -> str | None:
        if value is None:
            return None

        value = re.sub(r"\s+", " ", value.strip())
        return value if value else None


POTSDocParser = PotsDocParser
