"""Workspace folder (./idt by default) and config/state helpers."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "mode": "paper",                 # paper | live (live only changes where funds come from)
    "data_provider": "dhan",         # dhan | fixture
    "fixtures_dir": None,
    "capital": 100000,               # paper capital in INR
    "max_loss_per_trade": 1000,
    "daily_loss_cap": 3000,
    "max_trades_per_day": 5,
    "leverage_cap": 5,               # max notional / capital for intraday equity
    "or_minutes": 15,
    "entry_expiry": "11:30",         # ORB setups expire if not triggered by this time
    "entry_cutoff": "15:00",         # no fresh intraday entries after this
    "squareoff": "15:15",            # flat by this time (MIS)
    "allow_short": False,
    "allow_naked": False,            # naked short options
    "block_expiry_day_selling": True,
    "min_premium": 5.0,
    "stale_quote_seconds": 60,
    "require_ban_check": True,
    "risk_free_rate": 0.065,
    "product_intraday": "MIS",
    "product_carry": "NRML",
    "brokerage": {"per_order": 20.0, "equity_pct_cap": 0.0003},
    "charges_override": {},
    "index_ids": {},                 # override Dhan IDX_I security ids, e.g. {"NIFTY": 13}
    "holidays": [],                  # extra YYYY-MM-DD trading holidays
    "nse_user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
}


def workspace() -> Path:
    path = Path(os.environ.get("IDT_HOME", "idt"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config() -> dict[str, Any]:
    path = workspace() / "config.json"
    user = json.loads(path.read_text()) if path.exists() else {}
    cfg = _merge(DEFAULTS, user)
    if os.environ.get("IDT_FIXTURES"):
        cfg["data_provider"] = "fixture"
        cfg["fixtures_dir"] = os.environ["IDT_FIXTURES"]
    return cfg


def load_state(name: str, default: Any = None) -> Any:
    path = workspace() / name
    if not path.exists():
        return default
    return json.loads(path.read_text())


def save_state(name: str, data: Any) -> Path:
    path = workspace() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))
    return path


def append_journal(entry: dict) -> None:
    with open(workspace() / "journal.jsonl", "a") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")


def read_journal() -> list[dict]:
    path = workspace() / "journal.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
