"""`idt serve`: start the API, print the pairing URL and a QR code for the mobile apps."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from urllib.parse import quote

DEMO_NOW = "2026-10-29T09:45"


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def pairing_uri(url: str, token: str) -> str:
    return f"idt://pair?u={quote(url, safe='')}&t={quote(token, safe='')}"


def serve(host: str, port: int, demo: bool, now: str | None) -> None:
    try:
        import uvicorn
    except ImportError:
        sys.exit('The API server needs extras: pip install -e ".[server]"')

    if demo:
        fixtures = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "data"
        if not os.environ.get("IDT_FIXTURES"):
            if not fixtures.exists():
                sys.exit("--demo needs the repo checkout (tests/fixtures/data) or IDT_FIXTURES")
            os.environ["IDT_FIXTURES"] = str(fixtures)
        now = now or DEMO_NOW

    from .. import service as svc
    from .app import create_app, fixed_clock, server_token

    svc.init()
    token = server_token()
    url = f"http://{lan_ip() if host == '0.0.0.0' else host}:{port}"
    uri = pairing_uri(url, token)
    print(f"\n  Indian Day Trader API {'(DEMO: fixtures, clock pinned to ' + now + ' IST)' if demo else ''}")
    print(f"  Web app:   {url}/?token={token}")
    print(f"  API token: {token}   (stored in idt/server.json; delete it to rotate)")
    print("  Pair a phone: scan the QR below in the app, or enter the URL and token.\n")
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(uri)
        qr.print_ascii(invert=True)
    except ImportError:
        print(f"  {uri}")
    print()
    app = create_app(fixed_clock(now) if now else None, demo=demo)
    uvicorn.run(app, host=host, port=port, log_level="info")
