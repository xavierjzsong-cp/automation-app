"""Cross-partner regression checks for parser, router, and mapper parity."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mappers.ht_mapper import HtMapper  # noqa: E402
from src.mappers.jfe_mapper import JfeMapper  # noqa: E402
from src.mappers.tsh_mapper import TshMapper  # noqa: E402
from src.mappers.vam_mapper import VamMapper  # noqa: E402
from src.parsers.pots_doc_parser import PotsDocParser  # noqa: E402
from src.routers.partner_router import PartnerRouter  # noqa: E402


MAPPER_REGISTRY = {
    "VAM": VamMapper(),
    "TSH": TshMapper(),
    "JFE": JfeMapper(),
    "HT": HtMapper(),
}

CASES = (
    (
        "5.5 17# VAM TOP BOX X 5.5 17# TSH WEDGE PIN",
        [
            {
                "partner": "VAM",
                "side": "upper",
                "drift_extraction": True,
                "connection": {
                    "name": "TOP",
                    "od": "5-1/2",
                    "weight": "17.00",
                    "material_family": "13CR",
                    "yield_strength": "80",
                    "type": "BOX",
                },
            },
            {
                "partner": "TSH",
                "side": "lower",
                "drift_extraction": True,
                "connection": {
                    "name": "WEDGE",
                    "od": "5.500",
                    "weight": "17.00",
                    "material_family": "13CR",
                    "yield_strength": "80",
                    "type": "PIN",
                },
            },
        ],
    ),
    (
        "5.5 17# TSH WEDGE BOX X 5.5 17# JFE BEAR PIN",
        [
            {
                "partner": "TSH",
                "side": "upper",
                "drift_extraction": True,
                "connection": {
                    "name": "WEDGE",
                    "od": "5.500",
                    "weight": "17.00",
                    "material_family": "13CR",
                    "yield_strength": "80",
                    "type": "BOX",
                },
            },
            {
                "partner": "JFE",
                "side": "lower",
                "drift_extraction": True,
                "connection": {
                    "name": "JFEBEAR",
                    "od": "5.500",
                    "weight": "17",
                    "material_family": "13CR",
                    "yield_strength": "80",
                    "grade_source": "standard",
                    "friction": "API Modified",
                    "coupling": "STD",
                    "type": "PIN",
                },
            },
        ],
    ),
    (
        "5.5 17# JFE BEAR BOX X 5.5 17# SLHT PIN",
        [
            {
                "partner": "JFE",
                "side": "upper",
                "drift_extraction": True,
                "connection": {
                    "name": "JFEBEAR",
                    "od": "5.500",
                    "weight": "17",
                    "material_family": "13CR",
                    "yield_strength": "80",
                    "grade_source": "standard",
                    "friction": "API Modified",
                    "coupling": "STD",
                    "type": "BOX",
                },
            },
            {
                "partner": "HT",
                "side": "lower",
                "drift_extraction": True,
                "connection": {
                    "name": "SLHT",
                    "od": "5.500",
                    "weight": "17.000",
                    "material_family": "13CR",
                    "yield_strength": "80",
                    "type": "PIN",
                },
            },
        ],
    ),
    (
        "5.5 17# SLHT BOX X 5.5 17# VAM TOP PIN",
        [
            {
                "partner": "HT",
                "side": "upper",
                "drift_extraction": True,
                "connection": {
                    "name": "SLHT",
                    "od": "5.500",
                    "weight": "17.000",
                    "material_family": "13CR",
                    "yield_strength": "80",
                    "type": "BOX",
                },
            },
            {
                "partner": "VAM",
                "side": "lower",
                "drift_extraction": True,
                "connection": {
                    "name": "TOP",
                    "od": "5-1/2",
                    "weight": "17.00",
                    "material_family": "13CR",
                    "yield_strength": "80",
                    "type": "PIN",
                },
            },
        ],
    ),
)


def build_document_text(connections: str) -> str:
    return (
        "POTS Document number: 123 Rev: A\n"
        "CP Part Number ABC-001\n"
        f"Product Description Pup Joint 13CR(80) {connections} OAL 120\n"
        "ANSI/NACE MR0175/ISO 15156 (Yes/No) Yes\n"
        "QCP (Standard/Client Specific) Standard\n"
    )


def check_field_mapping_contract() -> None:
    config_path = ROOT_DIR / "config" / "field_mapping.yml"
    fields = yaml.safe_load(config_path.read_text(encoding="utf-8"))["fields"]
    expected_aliases = {
        "od": {"OD", "OD (in)", "Outside Diameter"},
        "wt": {"Weight / WT", "Weight / WT (lb/ft)", "WT", "Weight"},
        "grade": {"Grade"},
        "drift_option": {"Drift Option", "Drift Type"},
        "material_family": {"Material Family"},
        "yield_strength": {"Yield Strength", "Yield Strength (ksi)"},
    }

    assert set(fields) == set(expected_aliases)
    for field_name, aliases in expected_aliases.items():
        assert set(fields[field_name]["aliases"]) == aliases


def check_case(
    parser: PotsDocParser,
    router: PartnerRouter,
    connections: str,
    expected_mapped: list[dict[str, Any]],
) -> None:
    parsed = parser.parse_text(build_document_text(connections))
    routing = router.route(parsed)
    mapped = router.map_targets(routing, MAPPER_REGISTRY)

    assert parsed.part_number == "ABC-001"
    assert parsed.rev == "A"
    assert parsed.product_type == "PUP JOINT"
    assert parsed.product_material_grade == "13CR(80)"
    assert parsed.overall_length == "120"
    assert parsed.parse_warnings == []
    assert routing["partners_involved"] == [
        item["partner"] for item in expected_mapped
    ]
    assert routing["routing_warnings"] == []
    assert routing["shared_data"] == {
        "product_type": "PUP JOINT",
        "product_material_grade": "13CR(80)",
        "ansi_nace": "Yes",
        "qcp": "Standard",
        "overall_length": "120",
        "drift_extraction": True,
    }
    assert mapped == expected_mapped

    for _ in range(250):
        repeated_routing = router.route(parsed)
        repeated_mapped = router.map_targets(repeated_routing, MAPPER_REGISTRY)
        assert repeated_routing == routing
        assert repeated_mapped == expected_mapped


def main() -> None:
    check_field_mapping_contract()
    parser = PotsDocParser()
    router = PartnerRouter()

    for connections, expected_mapped in CASES:
        check_case(parser, router, connections, expected_mapped)

    print("partner pipeline parity ok")


if __name__ == "__main__":
    main()
