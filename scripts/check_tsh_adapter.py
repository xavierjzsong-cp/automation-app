"""Smoke checks for the TSH adapter interface."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.adapters.tsh_adapter import TshAdapter  # noqa: E402


def build_mapped_data() -> dict[str, Any]:
    return {
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
    }


def main() -> None:
    tmp = TemporaryDirectory()
    adapter = TshAdapter(
        base_url="https://dcp.tenaris.com/en",
        datasheet_url="https://dcp.tenaris.com/Product_Datasheet",
        blanking_url="https://dcp.tenaris.com/BlankingDimensions",
        logs_dir=Path(tmp.name),
        headless=True,
        slow_mo=25,
        timeout_ms=1234,
        navigation_timeout_ms=5678,
    )

    try:
        assert adapter.base_url == "https://dcp.tenaris.com/en"
        assert adapter.datasheet_url == "https://dcp.tenaris.com/Product_Datasheet"
        assert adapter.blanking_url == "https://dcp.tenaris.com/BlankingDimensions"
        assert adapter.logs_dir == Path(tmp.name)
        assert adapter.headless is True
        assert adapter.slow_mo == 25
        assert adapter.timeout_ms == 1234
        assert adapter.navigation_timeout_ms == 5678

        try:
            adapter.run({"partner": "TSH", "side": "lower", "connection": {}})
            raise AssertionError("Expected ValueError for incomplete TSH data.")
        except ValueError:
            pass

        invalid_type = build_mapped_data()
        invalid_type["connection"]["type"] = "COUPLING"
        try:
            adapter.run(invalid_type)
            raise AssertionError("Expected ValueError for unsupported TSH type.")
        except ValueError:
            pass

        try:
            adapter.run(build_mapped_data())
            raise AssertionError("Expected NotImplementedError for TSH automation.")
        except NotImplementedError as exc:
            assert str(exc) == "TSH Playwright automation is not implemented yet."
    finally:
        adapter.close()
        assert adapter._closed is True
        adapter.close()
        tmp.cleanup()

    print("tsh adapter ok")


if __name__ == "__main__":
    main()
