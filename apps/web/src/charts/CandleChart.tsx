import { useEffect, useRef } from "react";
import { createChart, CrosshairMode, LineStyle, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import type { IndexView } from "../lib/types";

const IST_OFFSET = 19800; // lightweight-charts renders UTC; shift so axes read IST

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function CandleChart({ view, height = 420 }: { view: IndexView; height?: number }) {
  const el = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!el.current) return;
    const build = () => {
      chartRef.current?.remove();
      const chart = createChart(el.current!, {
        height,
        autoSize: true,
        layout: { background: { color: "transparent" }, textColor: token("--text-2"), fontFamily: "Inter, system-ui", fontSize: 11 },
        grid: { vertLines: { color: token("--grid") }, horzLines: { color: token("--grid") } },
        rightPriceScale: { borderColor: token("--border") },
        timeScale: { borderColor: token("--border"), timeVisible: true, secondsVisible: false },
        crosshair: { mode: CrosshairMode.Normal },
        localization: { priceFormatter: (p: number) => p.toLocaleString("en-IN", { maximumFractionDigits: 2 }) },
      });
      chartRef.current = chart;
      const candles = chart.addCandlestickSeries({
        upColor: token("--up-mark"), downColor: token("--down-mark"), borderVisible: false,
        wickUpColor: token("--up-mark"), wickDownColor: token("--down-mark"),
      });
      const t = (s: number) => (s + IST_OFFSET) as UTCTimestamp;
      candles.setData(view.candles.map((c) => ({ time: t(c.t), open: c.o, high: c.h, low: c.l, close: c.c })));

      const line = (key: "ema9" | "ema21" | "vwap", color: string) => {
        const pts = view.series[key]
          .map((v, i) => (v == null ? null : { time: t(view.candles[i].t), value: v }))
          .filter((p): p is { time: UTCTimestamp; value: number } => p !== null);
        if (!pts.length) return;
        chart.addLineSeries({ color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }).setData(pts);
      };
      line("ema9", token("--series-1"));
      line("ema21", token("--series-2"));
      line("vwap", token("--series-3"));

      const level = (price: number | undefined, title: string, color: string, style = LineStyle.Dashed) => {
        if (price == null) return;
        candles.createPriceLine({ price, color, lineWidth: 1, lineStyle: style, axisLabelVisible: true, title });
      };
      const muted = token("--muted");
      level(view.opening_range?.high, "OR H", token("--accent"));
      level(view.opening_range?.low, "OR L", token("--accent"));
      level(view.prev_day?.high, "PDH", muted, LineStyle.Dotted);
      level(view.prev_day?.low, "PDL", muted, LineStyle.Dotted);
      level(view.cpr?.pivot, "P", muted, LineStyle.SparseDotted);
      chart.timeScale().fitContent();
    };
    build();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const obs = new MutationObserver(build); // theme toggle flips data-theme on <html>
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    mq.addEventListener("change", build);
    return () => {
      obs.disconnect();
      mq.removeEventListener("change", build);
      chartRef.current?.remove();
      chartRef.current = null;
    };
  }, [view, height]);

  return (
    <div>
      <div ref={el} style={{ height }} />
      <div className="legend" style={{ marginTop: 10 }}>
        <span><i className="line" style={{ background: "var(--series-1)" }} />EMA 9</span>
        <span><i className="line" style={{ background: "var(--series-2)" }} />EMA 21</span>
        {view.vwap != null && <span><i className="line" style={{ background: "var(--series-3)" }} />VWAP</span>}
        <span><i className="line" style={{ background: "var(--accent)" }} />Opening range</span>
        <span><i className="line" style={{ background: "var(--muted)" }} />PDH / PDL / Pivot</span>
      </div>
    </div>
  );
}
