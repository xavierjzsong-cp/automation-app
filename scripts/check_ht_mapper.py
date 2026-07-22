"""Smoke and repeatability checks for the HT mapper."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mappers.ht_mapper import HtMapper  # noqa: E402


def main() -> None:
    mapper = HtMapper()
    shared_data = {
        "product_material_grade": "13CR(80)",
        "drift_extraction": True,
    }
    target = {
        "partner": "HT",
        "side": "upper",
        "connection": {
            "name": "slht",
            "od": "5 1/2",
            "weight": "17#",
            "type": "BOX",
        },
    }

    expected = {
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
    }
    assert mapper.build_mapped_data(target=target, shared_data=shared_data) == expected

    slht_s_mapped = mapper.build_mapped_data(
        target={
            "partner": "ht",
            "side": "lower",
            "connection": {
                "name": " slht-s ",
                "od": "7.000 IN",
                "weight": "29.5 LB/FT",
                "type": "PIN",
            },
        },
        shared_data={
            "product_material_grade": " 13cr (80.0) ",
            "drift_extraction": False,
        },
    )
    assert slht_s_mapped == {
        "partner": "HT",
        "side": "lower",
        "drift_extraction": False,
        "connection": {
            "name": "SLHT-S",
            "od": "7.000",
            "weight": "29.500",
            "material_family": "13CR",
            "yield_strength": "80",
            "type": "PIN",
        },
    }

    unmapped_grade = mapper.build_mapped_data(
        target=target,
        shared_data={"product_material_grade": "UNKNOWN"},
    )
    assert unmapped_grade["connection"]["material_family"] is None
    assert unmapped_grade["connection"]["yield_strength"] is None

    invalid_fraction = mapper.build_mapped_data(
        target={
            "partner": "HT",
            "connection": {"od": "5 1/0", "weight": "bad"},
        },
        shared_data={},
    )
    assert invalid_fraction["connection"]["od"] == "5 1/0"
    assert invalid_fraction["connection"]["weight"] == "bad"

    for _ in range(250):
        assert mapper.build_mapped_data(target=target, shared_data=shared_data) == expected

    try:
        mapper.build_mapped_data(target={"partner": "JFE"}, shared_data={})
        raise AssertionError("Expected ValueError for non-HT target.")
    except ValueError:
        pass

    print("ht mapper ok")


if __name__ == "__main__":
    main()
