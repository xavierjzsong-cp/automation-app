"""Route parsed upper and lower connections to partner targets."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
import re


class PartnerRouter:
    """Build partner targets from parsed POTS connection data."""

    DRIFT_EXTRACTION_THRESHOLD = Decimal("18.125")

    def route(self, parsed: dict[str, Any] | Any) -> dict[str, Any]:
        parsed_data = self._to_mapping(parsed)
        connections = parsed_data.get("connections") or {}

        targets: list[dict[str, Any]] = []
        warnings: list[str] = []

        for side in ("upper", "lower"):
            target = self._build_target(side, connections.get(side), warnings)
            if target:
                targets.append(target)

        return {
            "shared_data": self._build_shared_data(parsed_data),
            "partners_involved": self._collect_partners(targets),
            "targets": targets,
            "routing_warnings": warnings,
        }

    def map_targets(
        self,
        routing_result: dict[str, Any],
        mapper_registry: dict[str, Any],
    ) -> list[dict[str, Any]]:
        shared_data = routing_result.get("shared_data") or {}
        targets = routing_result.get("targets") or []

        mapped_results: list[dict[str, Any]] = []
        for target in targets:
            partner = (target.get("partner") or "").upper()
            if not partner:
                continue

            mapper = mapper_registry.get(partner)
            if mapper is None:
                raise ValueError(f"No mapper registered for partner: {partner}")

            mapped_results.append(
                mapper.build_mapped_data(
                    target=target,
                    shared_data=shared_data,
                )
            )

        return mapped_results

    def _build_target(
        self,
        side: str,
        connection: dict[str, Any] | Any | None,
        warnings: list[str],
    ) -> dict[str, Any] | None:
        if connection is None:
            warnings.append(f"No {side} connection found.")
            return None

        connection_data = self._to_mapping(connection)
        partner = self._normalize_partner(connection_data.get("family"))
        if not partner:
            warnings.append(f"No partner family found for {side} connection.")
            return None

        connection_name = self._strip_connection_end(
            connection_data.get("name"),
            connection_data.get("type"),
        )

        return {
            "partner": partner,
            "side": side,
            "connection": {
                "name": connection_name,
                "od": connection_data.get("od"),
                "weight": connection_data.get("weight"),
                "type": connection_data.get("type"),
            },
        }

    def _build_shared_data(self, parsed: dict[str, Any]) -> dict[str, Any]:
        overall_length = parsed.get("overall_length")
        return {
            "product_type": parsed.get("product_type"),
            "product_material_grade": parsed.get("product_material_grade"),
            "ansi_nace": parsed.get("ansi_nace"),
            "qcp": parsed.get("qcp"),
            "overall_length": overall_length,
            "drift_extraction": self._requires_drift_extraction(overall_length),
        }

    def _requires_drift_extraction(self, overall_length: str | None) -> bool:
        if not overall_length:
            return False

        match = re.search(r"(\d+(?:\.\d+)?)", str(overall_length))
        if not match:
            return False

        try:
            value = Decimal(match.group(1))
        except InvalidOperation:
            return False

        return value > self.DRIFT_EXTRACTION_THRESHOLD

    def _normalize_partner(self, family: str | None) -> str | None:
        if not family:
            return None

        partner = str(family).strip().upper()
        return partner or None

    def _strip_connection_end(self, name: str | None, conn_type: str | None) -> str | None:
        if not name:
            return None

        text = str(name).strip()
        if not conn_type:
            return text

        suffix = str(conn_type).strip().upper()
        upper_text = text.upper()
        if upper_text.endswith(f" {suffix}"):
            return text[: -(len(suffix) + 1)].strip()

        return text

    def _collect_partners(self, targets: list[dict[str, Any]]) -> list[str]:
        partners: list[str] = []
        for target in targets:
            partner = target.get("partner")
            if partner and partner not in partners:
                partners.append(partner)
        return partners

    def _to_mapping(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if is_dataclass(value):
            return asdict(value)
        raise TypeError(f"Unsupported routing input type: {type(value)!r}")
