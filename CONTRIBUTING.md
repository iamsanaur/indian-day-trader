# Contributing

Thanks for helping. This project is about **disciplined, transparent** trading tools for Indian
markets. Please keep that spirit.

## Ground rules

1. **No automatic order placement.** PRs that add order endpoints will be closed. The ticket +
   human "yes" flow is the design.
2. **No hardcoded lot sizes, expiries or tick sizes.** Read them from the instrument master.
3. **Rates and rules change.** Put statutory rates in `src/idt/charges.py` with an effective date
   and a source in the PR description.
4. **Tests run offline.** Use `FixtureData` or mocked HTTP; never call live APIs in tests.

## Setup

```bash
uv venv && uv pip install -e ".[dev]" ruff
pytest -q
ruff check src tests --select F,E9
```

## Good first contributions

- A `MarketData` adapter for another broker (`src/idt/data/<broker>.py`) — implement `candles`,
  `quote`, `expiries`, `option_chain`, `funds`, `margin`, `instrument`, plus mocked-HTTP tests like
  `tests/test_data.py`.
- A new scanner setup in `src/idt/scanner.py` with a fixture that triggers it.
- Better margin estimation when the broker margin API is unavailable.

## Style

Match the surrounding code: small focused modules, type hints, JSON-in/JSON-out CLI commands,
comments only where the *why* isn't obvious.
