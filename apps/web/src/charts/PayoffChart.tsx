import { useState } from "react";
import { num, signedRupees } from "../lib/format";
import { linear, ticks } from "./svg";

interface Props {
  x: number[];
  expiry: number[];
  today: number[];
  spot: number;
  breakevens: number[];
}

/** Strategy P/L vs underlying at expiry (solid) and today (dashed), with crosshair tooltip. */
export function PayoffChart({ x, expiry, today, spot, breakevens }: Props) {
  const [hi, setHi] = useState<number | null>(null);
  const W = 900, H = 320, L = 64, R = 14, T = 14, B = 30;
  const all = [...expiry, ...today, 0];
  const lo = Math.min(...all), top = Math.max(...all);
  const pad = (top - lo) * 0.08 || 1;
  const sx = linear(x[0], x[x.length - 1], L, W - R);
  const sy = linear(lo - pad, top + pad, H - B, T);
  const path = (ys: number[]) => ys.map((v, i) => `${i ? "L" : "M"}${sx(x[i]).toFixed(1)},${sy(v).toFixed(1)}`).join("");
  const area = (sign: 1 | -1) => {
    const clip = expiry.map((v) => (sign > 0 ? Math.max(v, 0) : Math.min(v, 0)));
    return `${path(clip)}L${sx(x[x.length - 1])},${sy(0)}L${sx(x[0])},${sy(0)}Z`;
  };
  const move = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const v = sx.invert(px);
    let best = 0;
    x.forEach((xi, i) => { if (Math.abs(xi - v) < Math.abs(x[best] - v)) best = i; });
    setHi(px < L || px > W - R ? null : best);
  };

  return (
    <div style={{ position: "relative" }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Strategy payoff" onMouseMove={move} onMouseLeave={() => setHi(null)}>
        {ticks(lo - pad, top + pad).map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} stroke="var(--grid)" />
            <text x={L - 8} y={sy(t) + 4} textAnchor="end" fontSize="12" fill="var(--muted)">{signedRupees(t)}</text>
          </g>
        ))}
        {ticks(x[0], x[x.length - 1], 6).map((t) => (
          <text key={t} x={sx(t)} y={H - 10} textAnchor="middle" fontSize="12" fill="var(--muted)">{num(t, 0)}</text>
        ))}
        <path d={area(1)} fill="var(--up-soft)" />
        <path d={area(-1)} fill="var(--down-soft)" />
        <line x1={L} x2={W - R} y1={sy(0)} y2={sy(0)} stroke="var(--border)" strokeWidth="1.5" />
        <path d={path(today)} fill="none" stroke="var(--series-1)" strokeWidth="2" strokeDasharray="6 4" />
        <path d={path(expiry)} fill="none" stroke="var(--text)" strokeWidth="2" />
        <line x1={sx(spot)} x2={sx(spot)} y1={T} y2={H - B} stroke="var(--text-2)" strokeDasharray="2 3" />
        <text x={sx(spot) + 4} y={T + 10} fontSize="12" fill="var(--text-2)">Spot {num(spot, 0)}</text>
        {breakevens.filter((b) => b >= x[0] && b <= x[x.length - 1]).map((b) => (
          <g key={b}>
            <circle cx={sx(b)} cy={sy(0)} r="4.5" fill="var(--surface)" stroke="var(--warn)" strokeWidth="2" />
            <text x={sx(b)} y={sy(0) + 18} textAnchor="middle" fontSize="12" fill="var(--warn)">BE {num(b, 0)}</text>
          </g>
        ))}
        {hi != null && (
          <g>
            <line x1={sx(x[hi])} x2={sx(x[hi])} y1={T} y2={H - B} stroke="var(--muted)" />
            <circle cx={sx(x[hi])} cy={sy(expiry[hi])} r="4.5" fill="var(--text)" stroke="var(--surface)" strokeWidth="2" />
            <circle cx={sx(x[hi])} cy={sy(today[hi])} r="4.5" fill="var(--series-1)" stroke="var(--surface)" strokeWidth="2" />
          </g>
        )}
      </svg>
      {hi != null && (
        <div className="chart-tip" style={{ left: `${(sx(x[hi]) / W) * 100}%`, top: 8, transform: `translateX(${sx(x[hi]) > W * 0.7 ? "-105%" : "8px"})` }}>
          <b>Underlying {num(x[hi], 0)}</b>
          <div>At expiry <b className={expiry[hi] >= 0 ? "up" : "down"}>{signedRupees(expiry[hi])}</b></div>
          <div>Today <b className={today[hi] >= 0 ? "up" : "down"}>{signedRupees(today[hi])}</b></div>
        </div>
      )}
      <div className="legend" style={{ marginTop: 6 }}>
        <span><i className="line" style={{ background: "var(--text)" }} />At expiry</span>
        <span><i className="line" style={{ background: "var(--series-1)" }} />Today (model)</span>
        <span><i style={{ background: "var(--surface)", border: "2px solid var(--warn)", borderRadius: 99 }} />Breakeven</span>
      </div>
    </div>
  );
}
