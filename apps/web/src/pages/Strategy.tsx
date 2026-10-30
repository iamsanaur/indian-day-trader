import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { StrategyResult } from "../lib/types";
import { num, rupees, signedRupees } from "../lib/format";
import { Badge, Card, ErrorBox, Loading, PageHead, Seg, Stat } from "../ui";
import { PayoffChart } from "../charts/PayoffChart";
import { UNDERLYINGS } from "./Options";

interface Params {
  name: string;
  underlying: string;
  expiry: string;
  lots: number;
  offset: number;
  width: number;
  delta: string;
  legs: string[];
}

const DELTA_STRATS = new Set(["short-strangle", "long-strangle", "iron-condor", "short-call", "short-put"]);

function LegEditor({ legs, onChange }: { legs: string[]; onChange: (l: string[]) => void }) {
  const [side, setSide] = useState("+");
  const [lots, setLots] = useState(1);
  const [strike, setStrike] = useState("");
  const [kind, setKind] = useState("CE");
  return (
    <div className="stack">
      {legs.map((l, i) => (
        <div key={i} className="row between">
          <Badge tone={l.startsWith("-") ? "down" : "up"}>{l.startsWith("-") ? "SELL" : "BUY"}</Badge>
          <span className="num">{l.replace(/^[+-]/, "")}</span>
          <button className="btn btn-sm btn-ghost" onClick={() => onChange(legs.filter((_, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <div className="row">
        <select className="select" value={side} onChange={(e) => setSide(e.target.value)} aria-label="Side"><option value="+">Buy</option><option value="-">Sell</option></select>
        <input className="input" type="number" min={1} value={lots} onChange={(e) => setLots(+e.target.value)} style={{ width: 64 }} aria-label="Lots" />
        <input className="input" placeholder="Strike" value={strike} onChange={(e) => setStrike(e.target.value)} style={{ width: 100 }} aria-label="Strike" />
        <select className="select" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Type"><option>CE</option><option>PE</option></select>
        <button className="btn btn-sm" disabled={!strike} onClick={() => { onChange([...legs, `${side}${lots}x${strike}${kind}`]); setStrike(""); }}>Add leg</button>
      </div>
    </div>
  );
}

export function Strategy() {
  const nav = useNavigate();
  const [p, setP] = useState<Params>({ name: "bull-call-spread", underlying: "NIFTY", expiry: "", lots: 1, offset: 0, width: 4, delta: "", legs: [] });
  const set = <K extends keyof Params>(k: K, v: Params[K]) => setP((x) => ({ ...x, [k]: v }));
  const templates = useQuery({ queryKey: ["strategies"], queryFn: () => api<Record<string, string>>("/strategies") });
  const exp = useQuery({ queryKey: ["expiries", p.underlying], queryFn: () => api<{ expiries: string[] }>(`/expiries/${p.underlying}`) });
  const body = (write: boolean) => ({
    name: p.name, underlying: p.underlying, expiry: p.expiry || null, lots: p.lots, offset: p.offset, width: p.width,
    delta: p.delta ? Number(p.delta) : null, legs: p.legs, write,
  });
  const ready = p.name !== "custom" || p.legs.length > 0;
  const preview = useQuery({
    queryKey: ["strategy", p],
    queryFn: () => api<StrategyResult>("/strategy", { json: body(false) }),
    enabled: ready,
  });
  const use = useMutation({ mutationFn: () => api("/strategy", { json: body(true) }), onSuccess: () => nav("/trade?from=strategy") });
  const r = preview.data;
  const a = r?.analysis;

  return (
    <>
      <PageHead title="Strategy builder" sub="Payoff, breakevens, Greeks and margin before you commit" />
      <div className="split" style={{ gridTemplateColumns: "320px minmax(0,1fr)" }}>
        <Card title="Setup">
          <div className="stack">
            <div className="field"><label>Underlying</label>
              <select className="select" value={p.underlying} onChange={(e) => setP({ ...p, underlying: e.target.value, expiry: "" })}>
                {UNDERLYINGS.map((u) => <option key={u}>{u}</option>)}
              </select>
            </div>
            <div className="field"><label>Expiry</label>
              <select className="select" value={p.expiry} onChange={(e) => set("expiry", e.target.value)}>
                <option value="">Nearest</option>
                {exp.data?.expiries.map((e) => <option key={e}>{e}</option>)}
              </select>
            </div>
            <div className="field"><label>Strategy</label>
              <select className="select" value={p.name} onChange={(e) => set("name", e.target.value)}>
                {templates.data && Object.keys(templates.data).map((k) => <option key={k} value={k}>{k.replace(/-/g, " ")}</option>)}
                <option value="custom">custom legs</option>
              </select>
              {templates.data?.[p.name] && <span className="small muted">{templates.data[p.name]}</span>}
            </div>
            {p.name === "custom" ? (
              <LegEditor legs={p.legs} onChange={(l) => set("legs", l)} />
            ) : (
              <div className="grid grid-3" style={{ gap: 10 }}>
                <div className="field"><label>Lots</label><input className="input" type="number" min={1} value={p.lots} onChange={(e) => set("lots", Math.max(1, +e.target.value))} /></div>
                <div className="field"><label>Offset</label><input className="input" type="number" value={p.offset} onChange={(e) => set("offset", +e.target.value)} /></div>
                <div className="field"><label>Width</label><input className="input" type="number" min={1} value={p.width} onChange={(e) => set("width", Math.max(1, +e.target.value))} /></div>
              </div>
            )}
            {DELTA_STRATS.has(p.name) && (
              <div className="field"><label>Short strikes by |delta| (optional)</label>
                <Seg value={p.delta} onChange={(d) => set("delta", d)} options={[{ value: "", label: "Steps" }, { value: "0.1", label: "0.10" }, { value: "0.15", label: "0.15" }, { value: "0.2", label: "0.20" }, { value: "0.3", label: "0.30" }]} />
              </div>
            )}
            <p className="small muted" style={{ margin: 0 }}>Offset and width are in strike steps. Buys price at the ask, sells at the bid.</p>
            <button className="btn btn-primary" disabled={!r || use.isPending} onClick={() => use.mutate()}>Use for trade →</button>
            <ErrorBox error={use.error} />
          </div>
        </Card>

        <div className="stack">
          <ErrorBox error={preview.error} />
          {r?.warning && (
            <div className="banner warn"><div><div className="banner-title">Naked short options</div><div className="small">{a?.naked.join(" · ")}. {r.warning}</div></div></div>
          )}
          <Card title={r ? `${r.name.replace(/-/g, " ")} · ${r.underlying} ${r.expiry}` : "Payoff"} right={r && <Badge tone="accent">lot {r.lot_size}</Badge>}>
            {r ? <PayoffChart {...r.curve} spot={r.spot} breakevens={a!.breakevens} /> : <Loading h={320} />}
          </Card>
          {r && a && (
            <>
              <Card>
                <div className="stats">
                  <Stat k={a.premium_type === "debit" ? "Net debit" : "Net credit"} v={rupees(Math.abs(a.net_premium))} />
                  <Stat k="Max profit" v={a.unlimited_profit ? "Unlimited" : signedRupees(a.max_profit)} tone="up" />
                  <Stat k="Max loss" v={a.unlimited_loss ? "Unlimited" : signedRupees(a.max_loss)} tone="down" />
                  <Stat k="Breakevens" v={a.breakevens.map((b) => num(b, 0)).join(" · ") || "—"} />
                  <Stat k="Margin" v={r.margin.total != null ? rupees(r.margin.total) : "—"} hint={r.margin.source ?? r.margin.error} />
                </div>
              </Card>
              <div className="grid grid-2">
                <Card title="Greeks (position)">
                  <div className="stats">
                    <Stat k="Delta" v={num(r.greeks.delta, 1)} hint="units of underlying" />
                    <Stat k="Theta / day" v={signedRupees(r.greeks.theta)} tone={r.greeks.theta >= 0 ? "up" : "down"} />
                    <Stat k="Vega / IV pt" v={signedRupees(r.greeks.vega)} />
                    <Stat k="Gamma" v={num(r.greeks.gamma, 3)} />
                  </div>
                </Card>
                <Card title="Legs">
                  <table className="table">
                    <thead><tr><th>Leg</th><th>Lots</th><th>Price</th><th>IV</th></tr></thead>
                    <tbody>
                      {r.legs.map((l) => (
                        <tr key={l.symbol + l.side}>
                          <td><Badge tone={l.side > 0 ? "up" : "down"}>{l.side > 0 ? "BUY" : "SELL"}</Badge> {num(l.strike, 0)} {l.kind}</td>
                          <td>{l.lots}</td><td>{num(l.premium)}</td><td className="text-2">{num(l.iv * 100, 1)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Card>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
