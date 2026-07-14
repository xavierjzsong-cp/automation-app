"""Smoke checks for the JFE mapper."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mappers.jfe_mapper import JfeMapper  # noqa: E402


def main() -> None:
    mapper = JfeMapper()
    shared_data = {
        "product_material_grade": "13CR(80)",
        "drift_extraction": True,
    }
    target = {
        "partner": "JFE",
        "side": "upper",
        "connection": {
            "name": "Bear",
            "od": "5 1/2",
            "weight": "17.00",
            "type": "BOX",
        },
    }

    mapped = mapper.build_mapped_data(target=target, shared_data=shared_data)
    connection = mapped["connection"]
    assert mapped["partner"] == "JFE"
    assert mapped["side"] == "upper"
    assert mapped["drift_extraction"] is True
    assert connection["name"] == "JFEBEAR"
    assert connection["od"] == "5.500"
    assert connection["weight"] == "17"
    assert connection["material_family"] == "13CR"
    assert connection["yield_strength"] == "80"
    assert connection["grade_source"] == "standard"
    assert connection["friction"] == "API Modified"
    assert connection["coupling"] == "STD"
    assert connection["type"] == "BOX"

    fox_target = {
        "partner": "JFE",
        "side": "lower",
        "connection": {
            "name": "FOX",
            "od": "7.000 IN",
            "weight": "29#",
            "type": "PIN",
        },
    }
    fox_mapped = mapper.build_mapped_data(target=fox_target, shared_data=shared_data)
    assert fox_mapped["connection"]["name"] == "FOX"
    assert fox_mapped["connection"]["od"] == "7.000"
    assert fox_mapped["connection"]["weight"] == "29"

    jfe_grade_mapped = mapper.build_mapped_data(
        target=target,
        shared_data={
            "product_material_grade": "JFE-13CR-95",
            "drift_extraction": False,
        },
    )
    assert jfe_grade_mapped["drift_extraction"] is False
    assert jfe_grade_mapped["connection"]["material_family"] == "13CR"
    assert jfe_grade_mapped["connection"]["yield_strength"] == "95"
    assert jfe_grade_mapped["connection"]["grade_source"] == "jfe"

    try:
        mapper.build_mapped_data(target={"partner": "TSH"}, shared_data={})
        raise AssertionError("Expected ValueError for non-JFE target.")
    except ValueError:
        pass

    print("jfe mapper ok")


if __name__ == "__main__":
    main()
