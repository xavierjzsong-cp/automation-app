"""Legacy product-type alias and parser parity checks."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mappers.mapper_tables.product_type_map import (  # noqa: E402
    PRODUCT_TYPE_ALIASES,
)
from src.parsers.pots_doc_parser import PotsDocParser  # noqa: E402


EXPECTED_PRODUCT_TYPE_ALIASES = {
    "BLAST JOINT": ["BLAST JOINT"],
    "BULL NOSE/BULL PLUG": [
        "BULL NOSE/BULL PLUG",
        "BULL NOSE / BULL PLUG",
        "BULL NOSE",
        "BULL PLUG",
    ],
    "CROSSOVER": ["CROSSOVER", "CROSS OVER"],
    "DRIFT BAR": ["DRIFT BAR"],
    "FLOW COUPLING": ["FLOW COUPLING"],
    "HALF MULE SHOE/WIRELINE ENTRY GUIDE": [
        "HALF MULE SHOE/WIRELINE ENTRY GUIDE",
        "HALF MULE SHOE / WIRELINE ENTRY GUIDE",
        "HALF MULE SHOE",
        "WIRELINE ENTRY GUIDE",
    ],
    "LANDING NIPPLE": ["LANDING NIPPLE"],
    "LIFTING SUB": ["LIFTING SUB"],
    "LOCK MANDREL": ["LOCK MANDREL"],
    "MILL OUT EXTENSION": ["MILL OUT EXTENSION"],
    "NO-GO CROSSOVER": [
        "NO-GO CROSSOVER",
        "NO GO CROSSOVER",
        "NO-GO CROSS OVER",
        "NO GO CROSS OVER",
    ],
    "O-RING SEAL SUB": [
        "O-RING SEAL SUB",
        "ORING SEAL SUB",
        "O RING SEAL SUB",
    ],
    "POLISHED BORE RECEPTACLE (PBR)": [
        "POLISHED BORE RECEPTACLE (PBR)",
        "POLISHED BORE RECEPTACLE",
        "PBR",
    ],
    "POLISHED SLICK JOINT": ["POLISHED SLICK JOINT"],
    "PUP JOINT": ["PUP JOINT", "PUPJOINT"],
    "SEAL BORE EXTENSION (SBE)": [
        "SEAL BORE EXTENSION (SBE)",
        "SEAL BORE EXTENSION",
        "SBE",
    ],
    "SPACER TUBE": ["SPACER TUBE"],
    "STINGER": ["STINGER"],
    "TEST CAP/TEST PLUG": [
        "TEST CAP/TEST PLUG",
        "TEST CAP / TEST PLUG",
        "TEST CAP",
        "TEST PLUG",
    ],
    "OTHERS": ["OTHERS", "OTHER"],
}


def document(description: str, product_type_block: str = "") -> str:
    block = f"Product Type\n{product_type_block}\n" if product_type_block else ""
    return (
        "POTS Document number: 123 Rev: A\n"
        "CP Part Number ABC-001\n"
        f"{block}"
        f"Product Description {description}\n"
        "ANSI/NACE MR0175/ISO 15156 (Yes/No) Yes\n"
        "QCP (Standard/Client Specific) Standard\n"
    )


def connection_description(product_type: str = "") -> str:
    prefix = f"{product_type} " if product_type else ""
    return (
        f"{prefix}13CR(80) 5.5 17# VAM TOP BOX X "
        "5.5 17# TSH WEDGE PIN OAL 120"
    )


def check_description_aliases(parser: PotsDocParser) -> None:
    for canonical, aliases in EXPECTED_PRODUCT_TYPE_ALIASES.items():
        for alias in aliases:
            parsed = parser.parse_text(document(connection_description(alias)))
            assert parsed.product_type == canonical
            assert parsed.connections["upper"] is not None
            assert parsed.connections["lower"] is not None
            assert parsed.connections["upper"].name == "TOP"
            assert parsed.connections["lower"].name == "WEDGE"
            assert parsed.parse_warnings == []


def check_document_options(parser: PotsDocParser) -> None:
    checked = parser.parse_text(
        document(
            connection_description(),
            "☐ BLAST JOINT\n☒ NO GO CROSS OVER",
        )
    )
    assert checked.product_type == "NO-GO CROSSOVER"

    bracket_checked = parser.parse_text(
        document(connection_description(), "[x] Oring Seal Sub")
    )
    assert bracket_checked.product_type == "O-RING SEAL SUB"

    block_match = parser.parse_text(document(connection_description(), "PBR"))
    assert block_match.product_type == "POLISHED BORE RECEPTACLE (PBR)"

    description_precedence = parser.parse_text(
        document(connection_description("PUPJOINT"), "☒ CROSSOVER")
    )
    assert description_precedence.product_type == "PUP JOINT"

    embedded_alias = parser.parse_text(
        document(connection_description("SPECIAL PUP JOINT"))
    )
    assert embedded_alias.product_type == "PUP JOINT"

    assert parser._extract_product_type_from_description(
        "PUP   JOINT 13CR(80)"
    ) == "PUP JOINT"


def main() -> None:
    assert PRODUCT_TYPE_ALIASES == EXPECTED_PRODUCT_TYPE_ALIASES
    parser = PotsDocParser()

    check_description_aliases(parser)
    check_document_options(parser)

    for _ in range(20):
        check_description_aliases(parser)
        check_document_options(parser)

    print("product type parser ok")


if __name__ == "__main__":
    main()
