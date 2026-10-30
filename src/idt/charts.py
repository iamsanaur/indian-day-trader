"""Charts: index/stock candles with levels (PNG + interactive HTML), OI profile and strategy payoff."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

UP, DOWN = "#1a9c5b", "#d64545"
LEVEL_STYLE = {"or_high": ("#7a5cff", "--"), "or_low": ("#7a5cff", "--"), "pdh": ("#2b6cb0", ":"),
               "pdl": ("#2b6cb0", ":"), "pivot": ("#555", "-."), "tc": ("#999", ":"), "bc": ("#999", ":"),
               "r1": (DOWN, ":"), "s1": (UP, ":"), "max_pain": ("#b7791f", "--")}


def _candles_png(ax, df: pd.DataFrame) -> None:
    x = np.arange(len(df))
    up = df["close"] >= df["open"]
    colors = np.where(up, UP, DOWN)
    ax.vlines(x, df["low"], df["high"], color=colors, linewidth=0.8)
    body_lo = np.minimum(df["open"], df["close"])
    body_h = np.maximum((df["close"] - df["open"]).abs(), (df["high"] - df["low"]).max() * 0.002)
    ax.bar(x, body_h, bottom=body_lo, color=colors, width=0.7, linewidth=0)


def price_chart(df: pd.DataFrame, title: str, levels: dict[str, float], overlays: dict[str, pd.Series],
                out: Path, html: bool = False) -> list[Path]:
    """df: intraday bars to draw. levels: horizontal lines. overlays: series aligned to df (EMA, VWAP)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    paths = []
    fig, ax = plt.subplots(figsize=(13, 6.5), dpi=110)
    _candles_png(ax, df)
    x = np.arange(len(df))
    for name, series in overlays.items():
        if series.notna().any():
            ax.plot(x, series.values, linewidth=1.2, label=name)
    for name, value in levels.items():
        if value is None:
            continue
        color, style = LEVEL_STYLE.get(name, ("#888", ":"))
        ax.axhline(value, color=color, linestyle=style, linewidth=1)
        ax.text(len(df) - 0.5, value, f" {name.upper()} {value:,.2f}", va="center", fontsize=8, color=color)
    step = max(1, len(df) // 12)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([t.strftime("%d %b %H:%M") for t in df.index[::step]], rotation=30, ha="right", fontsize=8)
    ax.set_title(title)
    ax.grid(alpha=0.2)
    if overlays:
        ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    png = out.with_suffix(".png")
    fig.savefig(png)
    plt.close(fig)
    paths.append(png)

    if html:
        import plotly.graph_objects as go
        fig2 = go.Figure(go.Candlestick(x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
                                        name=title, increasing_line_color=UP, decreasing_line_color=DOWN))
        for name, series in overlays.items():
            if series.notna().any():
                fig2.add_scatter(x=df.index, y=series, mode="lines", name=name)
        for name, value in levels.items():
            if value is not None:
                fig2.add_hline(y=value, line_dash="dot", annotation_text=f"{name.upper()} {value:,.2f}",
                               line_color=LEVEL_STYLE.get(name, ("#888",))[0])
        fig2.update_layout(title=title, xaxis_rangeslider_visible=False, template="plotly_white", height=650,
                           xaxis={"rangebreaks": [{"bounds": ["sat", "mon"]}, {"bounds": [15.5, 9.25], "pattern": "hour"}]})
        page = out.with_suffix(".html")
        fig2.write_html(page, include_plotlyjs="cdn")
        paths.append(page)
    return paths


def oi_chart(analysis: dict, out: Path) -> Path:
    rows = analysis["table"]
    strikes = [r["strike"] for r in rows]
    ce = [r.get("ce", {}).get("oi", 0) for r in rows]
    pe = [r.get("pe", {}).get("oi", 0) for r in rows]
    ce_chg = [r.get("ce", {}).get("oi_change", 0) for r in rows]
    pe_chg = [r.get("pe", {}).get("oi_change", 0) for r in rows]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 8), dpi=110, sharex=True)
    w = (strikes[1] - strikes[0]) * 0.4 if len(strikes) > 1 else 20
    a1.bar([s - w / 2 for s in strikes], ce, width=w, color=DOWN, label="Call OI")
    a1.bar([s + w / 2 for s in strikes], pe, width=w, color=UP, label="Put OI")
    a2.bar([s - w / 2 for s in strikes], ce_chg, width=w, color=DOWN, label="Call OI change")
    a2.bar([s + w / 2 for s in strikes], pe_chg, width=w, color=UP, label="Put OI change")
    for ax in (a1, a2):
        ax.axvline(analysis["spot"], color="#222", linestyle="--", linewidth=1, label=f"Spot {analysis['spot']:,.2f}")
        ax.axvline(analysis["max_pain"], color="#b7791f", linestyle=":", linewidth=1.2, label=f"Max pain {analysis['max_pain']:,.0f}")
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8, loc="upper left")
    a1.set_title(f"{analysis['underlying']} {analysis['expiry']}  PCR {analysis['pcr']['oi']}  ATM IV {analysis['atm_iv']}")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    png = out.with_suffix(".png")
    fig.savefig(png)
    plt.close(fig)
    return png


def payoff_chart(grid: np.ndarray, expiry_pnl: np.ndarray, today_pnl: np.ndarray | None, spot: float,
                 breakevens: list[float], title: str, out: Path) -> Path:
    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=110)
    ax.plot(grid, expiry_pnl, color="#222", linewidth=1.6, label="At expiry")
    if today_pnl is not None:
        ax.plot(grid, today_pnl, color="#2b6cb0", linewidth=1.2, linestyle="--", label="Today (model)")
    ax.fill_between(grid, expiry_pnl, 0, where=expiry_pnl >= 0, color=UP, alpha=0.15)
    ax.fill_between(grid, expiry_pnl, 0, where=expiry_pnl < 0, color=DOWN, alpha=0.15)
    ax.axhline(0, color="#888", linewidth=0.8)
    ax.axvline(spot, color="#222", linestyle=":", label=f"Spot {spot:,.2f}")
    for b in breakevens:
        ax.axvline(b, color="#b7791f", linestyle=":", linewidth=1)
        ax.text(b, ax.get_ylim()[1] * 0.9, f" BE {b:,.0f}", fontsize=8, color="#b7791f")
    ax.set_title(title)
    ax.set_ylabel("P/L (Rs)")
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    png = out.with_suffix(".png")
    fig.savefig(png)
    plt.close(fig)
    return png
