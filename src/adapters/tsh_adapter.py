"""TSH adapter interface."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.adapters.base_adapter import BaseAdapter


logger = logging.getLogger(__name__)


class TshAdapter(BaseAdapter):
    """Validate TSH mapped data before Playwright automation is implemented."""

    REQUIRED_CONNECTION_FIELDS = {
        "name",
        "od",
        "weight",
        "material_family",
        "yield_strength",
        "type",
    }

    SUPPORTED_CONNECTION_TYPES = {"BOX", "PIN"}

    def __init__(
        self,
        base_url: str,
        datasheet_url: str,
        blanking_url: str,
        logs_dir: str | Path,
        headless: bool = False,
        slow_mo: int = 300,
        timeout_ms: int = 10000,
        navigation_timeout_ms: int = 60000,
    ) -> None:
        self.base_url = base_url
        self.datasheet_url = datasheet_url
        self.blanking_url = blanking_url
        self.logs_dir = Path(logs_dir)
        self.headless = headless
        self.slow_mo = slow_mo
        self.timeout_ms = timeout_ms
        self.navigation_timeout_ms = navigation_timeout_ms
        self._closed = False

    def run(self, mapped_data: dict[str, Any]) -> dict[str, Any]:
        """Validate mapped data and fail explicitly until automation exists."""
        self._validate_mapped_data(mapped_data)
        raise NotImplementedError(
            "TSH Playwright automation is not implemented yet."
        )

    def close(self) -> None:
        """Release adapter resources idempotently."""
        self._closed = True

    def _validate_mapped_data(self, mapped_data: dict[str, Any]) -> None:
        partner = (mapped_data.get("partner") or "").upper()
        if partner != "TSH":
            raise ValueError(f"TshAdapter received non-TSH data: {mapped_data.get('partner')}")

        side = mapped_data.get("side")
        if side not in {"upper", "lower"}:
            raise ValueError(f"TSH mapped data has invalid side: {side}")

        connection = mapped_data.get("connection")
        if not isinstance(connection, dict):
            raise ValueError("TSH mapped data is missing connection data.")

        missing = [
            field
            for field in sorted(self.REQUIRED_CONNECTION_FIELDS)
            if not connection.get(field)
        ]
        if missing:
            raise ValueError(f"TSH mapped connection missing fields: {missing}")

        connection_type = str(connection.get("type") or "").upper()
        if connection_type not in self.SUPPORTED_CONNECTION_TYPES:
            raise ValueError(
                f"TSH mapped data has unsupported connection.type: {connection_type}"
            )

        logger.debug("Validated TSH mapped data for %s side.", side)
