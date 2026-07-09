"""VAM adapter interface."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import logging

from src.adapters.base_adapter import BaseAdapter


logger = logging.getLogger(__name__)


class VamAdapter(BaseAdapter):
    """Validate VAM mapped data before Playwright automation is implemented."""

    REQUIRED_CONNECTION_FIELDS = {
        "name",
        "od",
        "weight",
        "material_family",
        "yield_strength",
        "type",
    }

    def __init__(
        self,
        base_url: str,
        configurator_url: str,
        logs_dir: str | Path,
        headless: bool = False,
        slow_mo: int = 300,
        timeout_ms: int = 10000,
    ) -> None:
        self.base_url = base_url
        self.configurator_url = configurator_url
        self.logs_dir = Path(logs_dir)
        self.headless = headless
        self.slow_mo = slow_mo
        self.timeout_ms = timeout_ms
        self._closed = False

    def run(self, mapped_data: dict[str, Any]) -> dict[str, Any]:
        """Validate mapped data and fail explicitly until automation exists."""
        self._validate_mapped_data(mapped_data)
        raise NotImplementedError(
            "VAM Playwright automation is not implemented yet."
        )

    def close(self) -> None:
        """Release adapter resources.

        The initial interface does not start browser resources yet, so close is
        intentionally idempotent.
        """
        self._closed = True

    def _validate_mapped_data(self, mapped_data: dict[str, Any]) -> None:
        partner = (mapped_data.get("partner") or "").upper()
        if partner != "VAM":
            raise ValueError(f"VamAdapter received non-VAM data: {mapped_data.get('partner')}")

        side = mapped_data.get("side")
        if side not in {"upper", "lower"}:
            raise ValueError(f"VAM mapped data has invalid side: {side}")

        connection = mapped_data.get("connection")
        if not isinstance(connection, dict):
            raise ValueError("VAM mapped data is missing connection data.")

        missing = [
            field
            for field in sorted(self.REQUIRED_CONNECTION_FIELDS)
            if not connection.get(field)
        ]
        if missing:
            raise ValueError(f"VAM mapped connection missing fields: {missing}")

        logger.debug("Validated VAM mapped data for %s side.", side)
