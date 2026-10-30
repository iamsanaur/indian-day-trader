"""Data providers. `get_data(cfg)` returns the configured MarketData implementation."""

from __future__ import annotations

from pathlib import Path

from ..config import workspace
from .base import DataError, MarketData


def get_data(cfg: dict) -> MarketData:
    overrides = cfg.get("index_ids") or {}
    if cfg.get("data_provider") == "fixture":
        from .fixture import FixtureData
        if not cfg.get("fixtures_dir"):
            raise DataError("data_provider is 'fixture' but fixtures_dir is not set")
        return FixtureData(cfg["fixtures_dir"], overrides)
    if cfg.get("data_provider") == "dhan":
        from .dhan import DhanData
        from .instruments import Instruments
        return DhanData(Instruments.load(workspace() / "cache", index_overrides=overrides))
    raise DataError(f"Unknown data_provider {cfg.get('data_provider')!r}")


def get_nse(cfg: dict):
    from .nse import NSE
    fixtures = Path(cfg["fixtures_dir"]) / "nse" if cfg.get("data_provider") == "fixture" else None
    return NSE(workspace() / "cache", cfg["nse_user_agent"], fixture_dir=fixtures)
