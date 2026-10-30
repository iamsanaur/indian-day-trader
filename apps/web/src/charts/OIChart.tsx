import { useState } from "react";
import type { Chain } from "../lib/types";
import { compact, num } from "../lib/format";
import { linear, ticks } from "./svg";

/** Open interest by strike: calls vs puts side by side, spot and max pain marked. */
export function OIChart({ chain, mode = "oi" }: { chain: Chain; mode?: "oi" | "change" }) {
  const [hover, setHover] = useState<number | null>(null);
  const rows = chain.table;
  const W = 900, H = 260, L = 48, R = 12, T = 12, B = 28;
  const val = (r: (typeof rows)[number], side: "ce" | "pe") => (mode === "oi" ? r[side]?.oi ?? 0 : r[side]?.oi_change ?? 0);
  const vals = rows.flatMap((r) => [val(r, "ce"), val(r, "pe")]);
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  const y = linear(lo, hi || 1, H - B, T);
  const band = (W - L - R) / rows.length;
  const bw = Math.max(2, Math.min(14, band / 2 - 2)); // 2px gap between the pair
  const x = (i: number) => L + band * i + band / 2;
  const sx = linear(rows[0].strike, rows[rows.length - 1].strike, x(0), x(rows.length - 1));
  const bar = (v: number, cx: number) => {
    const y0 = y(0), y1 = y(v);
    return { x: cx, y: Math.min(y0, y1), h: Math.max(1, Math.abs(y1 - y0)) };
  };
  const yt = ticks(lo, hi);
  const labelEvery = Math.ceil(rows.length / 10);
  const h = hover != null ? rows[hover] : null;

  return (
    <div style={{ position: "relative" }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`${mode === "oi" ? "Open interest" : "Change in OI"} by strike`} onMouseLeave={() => setHover(null)}>
        {yt.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--grid)" />
            <text x={L - 8} y={y(t) + 4} textAnchor="end" fontSize="12" fill="var(--muted)">{compact(t)}</text>
          </g>
        ))}
        {rows.map((r, i) => {
          const c = bar(val(r, "ce"), x(i) - bw - 1);
          const p = bar(val(r, "pe"), x(i) + 1);
          return (
            <g key={r.strike} opacity={hover == null || hover === i ? 1 : 0.45}>
              <rect x={c.x} y={c.y} width={bw} height={c.h} rx={Math.min(3, bw / 2)} fill="var(--series-1)" />
              <rect x={p.x} y={p.y} width={bw} height={p.h} rx={Math.min(3, bw / 2)} fill="var(--series-2)" />
              <rect x={L + band * i} y={T} width={band} height={H - T - B} fill="transparent" onMouseEnter={() => setHover(i)} />
              {i % labelEvery === 0 && (
                <text x={x(i)} y={H - 8} textAnchor="middle" fontSize="12" fill="var(--muted)">{num(r.strike, 0)}</text>
              )}
            </g>
          );
        })}
        <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} stroke="var(--border)" />
        {[{ v: chain.spot, label: "Spot", dash: "4 3", dy: 10 }, { v: chain.max_pain, label: "Max pain", dash: "1 3", dy: 26 }].map((m) => (
          <g key={m.label}>
            <line x1={sx(m.v)} x2={sx(m.v)} y1={T} y2={H - B} stroke="var(--text-2)" strokeDasharray={m.dash} />
            <text x={sx(m.v) + 5} y={T + m.dy} fontSize="12" fill="var(--text-2)" paintOrder="stroke" stroke="var(--surface)" strokeWidth="3">{m.label} {num(m.v, 0)}</text>
          </g>
        ))}
      </svg>
      {h && hover != null && (
        <div className="chart-tip" style={{ left: `${(x(hover) / W) * 100}%`, top: 0, transform: "translate(-50%, -100%)" }}>
          <b>{num(h.strike, 0)}</b>
          <div><span style={{ color: "var(--series-1)" }}>●</span> Call {compact(val(h, "ce"))}</div>
          <div><span style={{ color: "var(--series-2)" }}>●</span> Put {compact(val(h, "pe"))}</div>
        </div>
      )}
      <div className="legend" style={{ marginTop: 6 }}>
        <span><i style={{ background: "var(--series-1)" }} />Calls (CE)</span>
        <span><i style={{ background: "var(--series-2)" }} />Puts (PE)</span>
      </div>
    </div>
  );
}
