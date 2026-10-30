import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Chain, OptionSide } from "../lib/types";
import { compact, num, pct } from "../lib/format";
import { Badge, Card, ErrorBox, Loading, PageHead, Seg, Stat } from "../ui";
import { OIChart } from "../charts/OIChart";

export const UNDERLYINGS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"];

const BUILDUP_TONE: Record<string, "up" | "down" | "warn" | ""> = {
  "long buildup": "up", "short covering": "up", "short buildup": "down", "long unwinding": "warn",
};

function OIBar({ value, max, color, align }: { value: number; max: number; color: string; align: "left" | "right" }) {
  const w = max ? Math.max(2, (value / max) * 100) : 0;
  return (
    <div style={{ display: "flex", justifyContent: align === "right" ? "flex-end" : "flex-start", minWidth: 80 }}>
      <div style={{ width: `${w}%`, height: 6, borderRadius: 4, background: color, opacity: 0.85 }} />
    </div>
  );
}

function Side({ s, max, color, align }: { s?: OptionSide; max: number; color: string; align: "left" | "right" }) {
  if (!s) return <td colSpan={4} className="muted">—</td>;
  const cells = [
    <td key="bar"><OIBar value={s.oi} max={max} color={color} align={align === "left" ? "right" : "left"} /><div className="small muted">{compact(s.oi)}</div></td>,
    <td key="chg" className={s.oi_change >= 0 ? "up" : "down"}>{s.oi_change >= 0 ? "+" : ""}{compact(s.oi_change)}</td>,
    <td key="iv" className="text-2">{num(s.iv, 1)}</td>,
    <td key="ltp"><b>{num(s.ltp)}</b><div><Badge tone={BUILDUP_TONE[s.buildup] ?? ""}>{s.buildup}</Badge></div></td>,
  ];
  return <>{align === "right" ? cells : cells.reverse()}</>;
}

export function Options() {
  const [underlying, setUnderlying] = useState("NIFTY");
  const [expiry, setExpiry] = useState<string>("");
  const [mode, setMode] = useState<"oi" | "change">("oi");
  const exp = useQuery({ queryKey: ["expiries", underlying], queryFn: () => api<{ expiries: string[] }>(`/expiries/${underlying}`) });
  const chain = useQuery({
    queryKey: ["chain", underlying, expiry],
    queryFn: () => api<Chain>(`/chain/${underlying}?strikes=12${expiry ? `&expiry=${expiry}` : ""}`),
  });
  const c = chain.data;
  const maxOI = c ? Math.max(...c.table.flatMap((r) => [r.ce?.oi ?? 0, r.pe?.oi ?? 0])) : 0;

  return (
    <>
      <PageHead
        title="Option chain"
        sub={c ? `${c.underlying} · expiry ${c.expiry} · ${num(c.days_to_expiry, 1)} days · lot ${c.lot_size}` : "OI, PCR, max pain, IV"}
        right={
          <>
            <Seg value={underlying} onChange={(u) => { setUnderlying(u); setExpiry(""); }} options={UNDERLYINGS.map((u) => ({ value: u, label: u }))} />
            <select className="select" value={expiry} onChange={(e) => setExpiry(e.target.value)} aria-label="Expiry">
              <option value="">Nearest expiry</option>
              {exp.data?.expiries.map((e) => <option key={e} value={e}>{e}</option>)}
            </select>
          </>
        }
      />
      <ErrorBox error={chain.error ?? exp.error} />
      {!c && chain.isLoading && <Loading h={360} />}
      {c && (
        <div className="stack">
          <Card>
            <div className="stats">
              <Stat k="Spot" v={num(c.spot)} />
              <Stat k="ATM IV" v={c.atm_iv != null ? `${num(c.atm_iv, 1)}%` : "—"} />
              <Stat k="PCR (OI)" v={num(c.pcr.oi, 2)} hint={`Δ OI PCR ${num(c.pcr.oi_change, 2)}`} />
              <Stat k="Max pain" v={num(c.max_pain, 0)} hint={pct(c.max_pain_distance_pct)} />
              <Stat k="Expected move" v={`± ${num(c.expected_move.points, 0)}`} hint={`${num(c.expected_move.range[0], 0)} – ${num(c.expected_move.range[1], 0)}`} />
              <Stat k="ATM straddle" v={num(c.atm_straddle)} />
            </div>
            <p className="small text-2" style={{ margin: "14px 0 0" }}>Positioning: {c.bias}. A description of where open interest sits, not a prediction.</p>
          </Card>
          <div className="grid grid-2">
            <Card title="Resistance — call writers">
              {c.walls.resistance.map((w) => (
                <div key={w.strike} className="row between num" style={{ padding: "6px 0" }}><b>{num(w.strike, 0)}</b><span className="text-2">{compact(w.oi)} OI · +{compact(w.oi_change)}</span></div>
              ))}
            </Card>
            <Card title="Support — put writers">
              {c.walls.support.map((w) => (
                <div key={w.strike} className="row between num" style={{ padding: "6px 0" }}><b>{num(w.strike, 0)}</b><span className="text-2">{compact(w.oi)} OI · +{compact(w.oi_change)}</span></div>
              ))}
            </Card>
          </div>
          <Card title="Open interest by strike" right={<Seg value={mode} onChange={setMode} options={[{ value: "oi", label: "OI" }, { value: "change", label: "Change" }]} />}>
            <OIChart chain={c} mode={mode} />
          </Card>
          <Card title="Chain">
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>Call LTP</th><th>IV</th><th>Δ OI</th><th>Call OI</th>
                    <th style={{ textAlign: "center" }}>Strike</th>
                    <th style={{ textAlign: "left" }}>Put OI</th><th>Δ OI</th><th>IV</th><th>Put LTP</th>
                  </tr>
                </thead>
                <tbody>
                  {c.table.map((r) => {
                    const atm = r.strike === c.atm;
                    return (
                      <tr key={r.strike} style={atm ? { background: "var(--accent-soft)" } : undefined}>
                        <Side s={r.ce} max={maxOI} color="var(--series-1)" align="left" />
                        <td style={{ textAlign: "center", fontWeight: 700, background: r.strike < c.spot ? "var(--surface-2)" : undefined }}>
                          {num(r.strike, 0)}{atm && <div><Badge tone="accent">ATM</Badge></div>}
                        </td>
                        <Side s={r.pe} max={maxOI} color="var(--series-2)" align="right" />
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="small muted" style={{ marginBottom: 0 }}>Shaded strikes are below spot (ITM calls, OTM puts).</p>
          </Card>
        </div>
      )}
    </>
  );
}
