"""Behavior and repeatability checks for the legacy coating mapper."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mappers.coating_mapper import CoatingMapper  # noqa: E402
from src.mappers.mapper_tables.coating_map import COATING_MAP  # noqa: E402


EXPECTED_COATING_MAP = {
    "base_coating": {
        "alloy_steel": "CSP-158, CSP-99",
        "chrome_steel": "CSP-99",
        "nickel_alloy": "CSP-99",
    },
    "internal_seal_surface": {
        "alloy_steel": "CSP-134 AFTER COATING",
        "chrome_steel": "CSP-70",
        "nickel_alloy": "CSP-70",
    },
    "oring_groove_surfaces": {
        "alloy_steel": "CSP-134 AFTER COATING",
        "chrome_steel": "CSP-99",
        "nickel_alloy": "CSP-99",
    },
    "polished_seal_bore_surface": {
        "alloy_steel": "CSP-134 AFTER COATING",
        "chrome_steel": "CSP-99",
        "nickel_alloy": "CSP-99",
    },
    "premium_threads": {
        "alloy_steel": "CSP-83",
        "chrome_steel": "CSP-83",
        "nickel_alloy": "CSP-83",
    },
    "api_threads": {
        "alloy_steel": "CSP-118",
        "chrome_steel": "CSP-118",
        "nickel_alloy": "CSP-118",
    },
    "stub_acme_box_thread": {
        "alloy_steel": "CSP-28 (Mask all seal surface)",
        "chrome_steel": "CSP-70 (Mask the O-ring groove and not seal surface, if applicable)",
        "nickel_alloy": "CSP-70 (Mask the O-ring groove and not seal surface, if applicable)",
    },
    "stub_acme_pin_thread": {
        "alloy_steel": "CSP-28 (Mask all seal surface)",
        "chrome_steel": "CSP-28 (Mask all seal surface)",
        "nickel_alloy": "CSP-28 (Mask all seal surface)",
    },
    "un_box_pin_threads": {
        "alloy_steel": "CSP-16 / CSP-158",
        "chrome_steel": "CSP-70",
        "nickel_alloy": "CSP-70",
    },
    "tools_enter_seal_bore": {
        "alloy_steel": "CSP-70",
        "chrome_steel": "CSP-70",
        "nickel_alloy": "CSP-70",
    },
}


def routing_result(material: str | None) -> dict[str, object]:
    return {
        "shared_data": {"product_material_grade": material},
        "targets": [
            {"side": "upper", "partner": "VAM"},
            {"side": "lower", "partner": "HT"},
        ],
    }


def assert_value_error(
    callback: Callable[[], object],
    expected_message: str,
) -> None:
    try:
        callback()
    except ValueError as exc:
        assert str(exc) == expected_message
    else:
        raise AssertionError(f"Expected ValueError: {expected_message}")


def main() -> None:
    mapper = CoatingMapper()
    assert COATING_MAP == EXPECTED_COATING_MAP
    assert mapper.PREMIUM_THREAD_PARTNERS == {"VAM", "TSH", "JFE", "HT"}

    cases = (
        (
            "13CR(80)",
            {
                "top_thread_coating": "CSP-83",
                "bottom_thread_coating": "CSP-83",
                "body_coating": "CSP-99",
            },
        ),
        (
            "4140(80)",
            {
                "top_thread_coating": "CSP-83",
                "bottom_thread_coating": "CSP-83",
                "body_coating": "CSP-158, CSP-99",
            },
        ),
        (
            "INCOLLOY 925",
            {
                "top_thread_coating": "CSP-83",
                "bottom_thread_coating": "CSP-83",
                "body_coating": "CSP-99",
            },
        ),
        (
            None,
            {
                "top_thread_coating": None,
                "bottom_thread_coating": None,
                "body_coating": None,
            },
        ),
    )

    for material, expected in cases:
        result = mapper.build_mapped_data(routing_result(material))
        assert result == expected
        for _ in range(250):
            assert mapper.build_mapped_data(routing_result(material)) == expected

    assert mapper.map_material_category("S13CR（95）") == "chrome_steel"
    assert mapper.map_material_category("INCOL-925") == "nickel_alloy"
    assert mapper.map_material_category("4145") == "alloy_steel"
    assert mapper.map_material_category("UNKNOWN") is None
    assert mapper.map_thread_feature(" jfe ") == "premium_threads"
    assert mapper.map_thread_feature("API") is None
    assert mapper.map_thread_feature(None) is None

    one_sided = routing_result("13CR(80)")
    one_sided["targets"] = [{"side": "upper", "partner": "TSH"}]
    assert mapper.build_mapped_data(one_sided) == {
        "top_thread_coating": "CSP-83",
        "bottom_thread_coating": None,
        "body_coating": "CSP-99",
    }

    assert_value_error(
        lambda: mapper.map_coating_by_feature("unknown", "chrome_steel"),
        "Unsupported coating feature: unknown",
    )
    assert_value_error(
        lambda: mapper.map_coating_by_feature("base_coating", "unknown"),
        "Coating not found for feature=base_coating, material_category=unknown",
    )

    print("coating mapper ok")


if __name__ == "__main__":
    main()
