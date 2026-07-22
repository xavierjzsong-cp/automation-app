"""Partner website adapters."""

from src.adapters.base_adapter import BaseAdapter
from src.adapters.ht_adapter import HtAdapter
from src.adapters.jfe_adapter import JfeAdapter
from src.adapters.tsh_adapter import TshAdapter
from src.adapters.vam_adapter import VamAdapter

__all__ = [
    "BaseAdapter",
    "HtAdapter",
    "JfeAdapter",
    "TshAdapter",
    "VamAdapter",
]
