import io
import json
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

import pytest

from idt.data.fixture import FixtureData
from idt.market import IST

FIXTURES = Path(__file__).parent / "fixtures" / "data"
NOW = datetime(2026, 10, 29, 9, 45, tzinfo=IST)


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("IDT_HOME", str(tmp_path / "idt"))
    monkeypatch.setenv("IDT_FIXTURES", str(FIXTURES))
    return tmp_path / "idt"


@pytest.fixture
def data():
    return FixtureData(FIXTURES)


@pytest.fixture
def cfg():
    from idt.config import DEFAULTS
    return dict(DEFAULTS, max_loss_per_trade=3000)


def run(*argv, now="2026-10-29T09:45"):
    from idt.cli import main
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(["--now", now, *argv] if now else list(argv))
    return code, json.loads(buf.getvalue())


@pytest.fixture
def cli(ws):
    return run
