"""Main orchestration service for template generation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from src.parsers.pots_doc_parser import ParsedPotsDocument, PotsDocParser
from src.writers.template_writer import TemplateWriter


StatusCallback = Callable[[str], None]


@dataclass
class GenerationRequest:
    input_path: Path
    template_path: Path
    output_dir: Path
    user_name: str | None = None
    show_browser: bool = False
    target_sheet_name: str | None = None


@dataclass
class GenerationResult:
    parsed: dict[str, Any]
    writer_result: dict[str, Any]
    routing_result: dict[str, Any] | None = None
    mapped_results: list[dict[str, Any]] | None = None
    coating_data: dict[str, Any] | None = None
    top_adapter: dict[str, Any] | None = None
    bottom_adapter: dict[str, Any] | None = None
    target_sheet_name: str | None = None

    @property
    def output_file(self) -> str:
        return self.writer_result.get("output_file", "")


class TemplateGenerationService:
    """Coordinates parser and writer for the current generation flow."""

    SUPPORTED_TEMPLATE_SUFFIXES = {
        ".xlsx",
        ".xlsm",
        ".xltx",
        ".xltm",
    }

    def __init__(
        self,
        parser: PotsDocParser | None = None,
        writer: TemplateWriter | None = None,
    ) -> None:
        self.parser = parser or PotsDocParser()
        self.writer = writer or TemplateWriter()
        self.is_ready = True

    def generate(
        self,
        request: GenerationRequest,
        status_callback: StatusCallback | None = None,
    ) -> GenerationResult:
        """Parse a POTS PDF and write available fields to the Excel template."""
        self._status(status_callback, "Checking input information...")
        request = self._validate_request(request)

        self._status(status_callback, "Reading input document...")
        parsed = self.parser.parse_pdf(request.input_path)
        parsed_data = self._parsed_to_dict(parsed)

        self._status(status_callback, "Filling Excel template...")
        writer_result = self.writer.write(
            parsed=parsed,
            template_path=request.template_path,
            output_dir=request.output_dir,
            user_name=request.user_name,
            target_sheet_name=request.target_sheet_name,
        )

        self._status(status_callback, "Saving output file...")
        return GenerationResult(
            parsed=parsed_data,
            writer_result=writer_result,
            routing_result=None,
            mapped_results=[],
            coating_data={},
            top_adapter=None,
            bottom_adapter=None,
            target_sheet_name=request.target_sheet_name,
        )

    def _validate_request(self, request: GenerationRequest) -> GenerationRequest:
        input_path = Path(request.input_path)
        template_path = Path(request.template_path)
        output_dir = Path(request.output_dir)

        if not input_path.exists():
            raise FileNotFoundError(f"Input PDF not found: {input_path}")

        if input_path.suffix.lower() != ".pdf":
            raise ValueError(f"Input file must be PDF: {input_path}")

        if not template_path.exists():
            raise FileNotFoundError(f"Template file not found: {template_path}")

        if template_path.suffix.lower() not in self.SUPPORTED_TEMPLATE_SUFFIXES:
            supported = ", ".join(sorted(self.SUPPORTED_TEMPLATE_SUFFIXES))
            raise ValueError(
                f"Template file must be an Excel file supported by openpyxl: {supported}"
            )

        target_sheet_name = str(request.target_sheet_name or "").strip()
        if not target_sheet_name:
            raise ValueError("Target sheet is required.")

        output_dir.mkdir(parents=True, exist_ok=True)

        return replace(
            request,
            input_path=input_path,
            template_path=template_path,
            output_dir=output_dir,
            target_sheet_name=target_sheet_name,
        )

    def _parsed_to_dict(self, parsed: ParsedPotsDocument | dict[str, Any]) -> dict[str, Any]:
        if isinstance(parsed, dict):
            return parsed
        return parsed.to_dict()

    def _status(
        self,
        status_callback: StatusCallback | None,
        message: str,
    ) -> None:
        if status_callback:
            status_callback(message)
