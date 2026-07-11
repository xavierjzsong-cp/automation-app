"""Main orchestration service for template generation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

import yaml

from src.adapters.vam_adapter import VamAdapter
from src.mappers.tsh_mapper import TshMapper
from src.mappers.vam_mapper import VamMapper
from src.parsers.pots_doc_parser import ParsedPotsDocument, PotsDocParser
from src.routers.partner_router import PartnerRouter
from src.utils.app_paths import get_logs_dir, resource_path
from src.writers.template_writer import TemplateWriter


StatusCallback = Callable[[str], None]
AdapterFactory = Callable[..., Any]


@dataclass
class GenerationRequest:
    input_path: Path
    template_path: Path
    output_dir: Path
    user_name: str | None = None
    show_browser: bool = False
    run_partner_adapters: bool = False
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
        router: PartnerRouter | None = None,
        writer: TemplateWriter | None = None,
        mapper_registry: dict[str, Any] | None = None,
        adapter_factories: dict[str, AdapterFactory] | None = None,
        partners_config_path: str | Path | None = None,
        logs_dir: str | Path | None = None,
    ) -> None:
        self.parser = parser or PotsDocParser()
        self.router = router or PartnerRouter()
        self.writer = writer or TemplateWriter()
        self.mapper_registry = mapper_registry or {
            "VAM": VamMapper(),
            "TSH": TshMapper(),
        }
        self.adapter_factories = adapter_factories or {
            "VAM": VamAdapter,
        }
        self.partners_config_path = Path(partners_config_path) if partners_config_path else resource_path("config/partners.yml")
        self.logs_dir = Path(logs_dir) if logs_dir else get_logs_dir(create=False)
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

        self._status(status_callback, "Identifying connection details...")
        routing_result = self.router.route(parsed_data)
        mapped_results = self.router.map_targets(
            routing_result=routing_result,
            mapper_registry=self.mapper_registry,
        )

        top_adapter: dict[str, Any] | None = None
        bottom_adapter: dict[str, Any] | None = None

        if request.run_partner_adapters:
            top_adapter, bottom_adapter = self._run_partner_adapters(
                mapped_results=mapped_results,
                show_browser=request.show_browser,
                status_callback=status_callback,
            )

        self._status(status_callback, "Filling Excel template...")
        writer_result = self.writer.write(
            parsed=parsed,
            top_adapter=top_adapter,
            bottom_adapter=bottom_adapter,
            template_path=request.template_path,
            output_dir=request.output_dir,
            user_name=request.user_name,
            coating_data={},
            target_sheet_name=request.target_sheet_name,
        )

        self._status(status_callback, "Saving output file...")
        return GenerationResult(
            parsed=parsed_data,
            writer_result=writer_result,
            routing_result=routing_result,
            mapped_results=mapped_results,
            coating_data={},
            top_adapter=top_adapter,
            bottom_adapter=bottom_adapter,
            target_sheet_name=request.target_sheet_name,
        )

    def _run_partner_adapters(
        self,
        mapped_results: list[dict[str, Any]],
        show_browser: bool,
        status_callback: StatusCallback | None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        partners_config = self._load_partners_config(self.partners_config_path)
        top_adapter: dict[str, Any] | None = None
        bottom_adapter: dict[str, Any] | None = None

        for mapped_result in mapped_results:
            partner = (mapped_result.get("partner") or "").upper()
            side = mapped_result.get("side")

            if partner not in self.adapter_factories:
                continue

            if side == "upper":
                self._status(status_callback, "Retrieving top thread data...")
            elif side == "lower":
                self._status(status_callback, "Retrieving bottom thread data...")
            else:
                self._status(status_callback, "Retrieving thread data...")

            adapter_result = self._run_adapter_for_mapped_result(
                mapped_result=mapped_result,
                partners_config=partners_config,
                show_browser=show_browser,
            )

            if side == "upper":
                top_adapter = adapter_result
            elif side == "lower":
                bottom_adapter = adapter_result

        return top_adapter, bottom_adapter

    def _run_adapter_for_mapped_result(
        self,
        mapped_result: dict[str, Any],
        partners_config: dict[str, Any],
        show_browser: bool,
    ) -> dict[str, Any]:
        partner = (mapped_result.get("partner") or "").upper()
        side = mapped_result.get("side")
        partner_config = self._get_partner_config(partners_config, partner)
        urls = partner_config.get("urls") or {}

        if partner != "VAM":
            raise ValueError(f"Unsupported partner adapter: {partner}")

        base_url = urls.get("homepage")
        configurator_url = urls.get("connection_datasheet")
        if not base_url:
            raise ValueError("VAM config missing urls.homepage")
        if not configurator_url:
            raise ValueError("VAM config missing urls.connection_datasheet")

        adapter_factory = self.adapter_factories[partner]
        adapter = adapter_factory(
            base_url=base_url,
            configurator_url=configurator_url,
            logs_dir=self.logs_dir,
            headless=not show_browser,
            slow_mo=300,
            timeout_ms=10000,
        )

        try:
            adapter_result = adapter.run(mapped_result)
        finally:
            adapter.close()

        self._validate_adapter_result(partner, side, adapter_result)
        return adapter_result

    def _validate_adapter_result(
        self,
        partner: str,
        side: str | None,
        adapter_result: dict[str, Any],
    ) -> None:
        required_fields = [
            "tensile",
            "compression",
            "burst",
            "collapse",
            "drift",
            "od",
            "id",
            "external_length",
            "internal_length",
        ]

        missing = [
            field
            for field in required_fields
            if field not in adapter_result
        ]
        if missing:
            raise RuntimeError(
                f"{partner} adapter result for {side} thread missing fields: "
                f"{missing}. adapter_result={adapter_result}"
            )

    def _load_partners_config(self, config_path: Path) -> dict[str, Any]:
        if not config_path.exists():
            raise FileNotFoundError(f"partners.yml not found: {config_path}")

        with config_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)

        if not isinstance(data, dict):
            raise ValueError(f"Invalid partners.yml structure: {config_path}")

        return data

    def _get_partner_config(
        self,
        partners_config: dict[str, Any],
        partner: str,
    ) -> dict[str, Any]:
        partner = partner.upper()

        if "partners" in partners_config and isinstance(partners_config["partners"], dict):
            config = partners_config["partners"].get(partner)
            if config:
                return config

        config = partners_config.get(partner)
        if config:
            return config

        raise KeyError(f"Partner config not found for partner: {partner}")

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
