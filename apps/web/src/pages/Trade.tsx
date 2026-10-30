import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Orders, Plan, RiskVerdict, Ticket, TimeMachine } from "../lib/types";
import { num, rupees, signedRupees, time } from "../lib/format";
import { Badge, Card, ErrorBox, Icons, Loading, PageHead, Spinner, Stat } from "../ui";

const STEPS = ["Setup", "Plan", "Odds", "Size", "Risk", "Ticket"] as const;

interface PlanState {
  plan: Plan | null;
  setup: { symbol: string; state: string; side?: string; entry?: number; trigger_time?: string; range?: { high: number; low: number; mid: number } } | null;
  strategy: { name: string; underlying: string; expiry: string; legs: unknown[] } | null;
}

function Stepper({ step, done, onPick }: { step: number; done: boolean[]; onPick: (i: number) => void }) {
  return (
    <ol className="row" style={{ listStyle: "none", padding: 0, margin: "0 0 18px", gap: 6 }}>
      {STEPS.map((s, i) => (
        <li key={s}>
          <button className={`btn btn-sm ${i === step ? "btn-primary" : ""}`} onClick={() => onPick(i)} aria-current={i === step ? "step" : undefined}>
            <span className="num" style={{ opacity: 0.7 }}>{done[i] && i !== step ? "✓" : i + 1}</span> {s}
          </button>
        </li>
      ))}
    </ol>
  );
}

function SetupStep({ state, next }: { state?: PlanState; next: () => void }) {
  const qc = useQueryClient();
  const [symbol, setSymbol] = useState(state?.setup?.symbol ?? "NIFTY");
  const [setup, setSetup] = useState("orb");
  const check = useMutation({
    mutationFn: () => api<PlanState["setup"]>(`/entry/${symbol}`, { json: { setup, write: true } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["plan"] }),
  });
  const s = check.data ?? state?.setup;
  return (
    <div className="grid grid-2">
      <Card title="Check the entry trigger">
        <div className="stack">
          <div className="row">
            <input className="input" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} aria-label="Symbol" style={{ flex: 1 }} />
            <select className="select" value={setup} onChange={(e) => setSetup(e.target.value)} aria-label="Setup">
              <option value="orb">Opening-range breakout</option>
              <option value="pdh">Previous-day high/low</option>
            </select>
            <button className="btn btn-primary" onClick={() => check.mutate()} disabled={check.isPending}>{check.isPending ? <Spinner /> : "Check"}</button>
          </div>
          <ErrorBox error={check.error} />
          {s && (
            <div className={`banner ${s.state === "triggered" ? "pass" : "warn"}`}>
              <div>
                <div className="banner-title">{s.symbol}: {s.state}{s.side ? ` ${s.side}` : ""}</div>
                <div className="small text-2">
                  {s.state === "triggered" ? <>Entry {num(s.entry)} on the {time(s.trigger_time)} bar{s.range && <> · range {num(s.range.low)}–{num(s.range.high)}</>}</> : "Only completed 5-minute bars count."}
                </div>
              </div>
            </div>
          )}
        </div>
      </Card>
      <Card title="Or trade a strategy">
        {state?.strategy ? (
          <div className="stack">
            <div><b>{state.strategy.name.replace(/-/g, " ")}</b> · {state.strategy.underlying} {state.strategy.expiry}</div>
            <span className="small text-2">{state.strategy.legs.length} legs saved from the Strategy builder. Choose “Strategy” in the next step.</span>
          </div>
        ) : <p className="muted small">Build one in Strategy and press “Use for trade”.</p>}
      </Card>
      <div><button className="btn btn-primary" onClick={next} disabled={!s && !state?.strategy}>Next: plan the exit →</button></div>
    </div>
  );
}

const STOPS: Record<string, { value: string; label: string }[]> = {
  option: [{ value: "or-mid", label: "Underlying at OR mid" }, { value: "or-low", label: "Underlying at far side of OR" }, { value: "premium-pct:30", label: "Premium −30%" }, { value: "premium-pct:50", label: "Premium −50%" }],
  equity: [{ value: "or-mid", label: "OR mid" }, { value: "or-low", label: "Far side of OR" }, { value: "atr:1", label: "1 × ATR" }, { value: "pct:0.5", label: "0.5%" }],
  future: [{ value: "or-mid", label: "OR mid" }, { value: "or-low", label: "Far side of OR" }, { value: "atr:1", label: "1 × ATR" }],
  strategy: [{ value: "maxloss-pct:50", label: "50% of max loss" }, { value: "credit-x:1", label: "Loss = 1 × credit" }, { value: "pnl:-2000", label: "−₹2,000 per set" }],
};
const TARGETS: Record<string, { value: string; label: string }[]> = {
  option: [{ value: "1.5R", label: "1.5 R" }, { value: "2R", label: "2 R" }, { value: "1R", label: "1 R" }],
  equity: [{ value: "1.5R", label: "1.5 R" }, { value: "2R", label: "2 R" }, { value: "1R", label: "1 R" }],
  future: [{ value: "1.5R", label: "1.5 R" }, { value: "2R", label: "2 R" }],
  strategy: [{ value: "1.5R", label: "1.5 R" }, { value: "maxprofit-pct:60", label: "60% of max profit" }, { value: "credit-pct:50", label: "Keep 50% of credit" }],
};

function PlanCard({ p }: { p: Plan }) {
  const isStrat = p.basis === "pnl";
  return (
    <Card title={`${p.kind === "strategy" ? p.strategy?.replace(/-/g, " ") : p.contract} · ${p.side}`} right={<Badge tone="accent">R:R {num(p.rr, 2)}</Badge>}>
      <div className="stats">
        {isStrat ? (
          <>
            <Stat k={p.entry > 0 ? "Debit / set" : "Credit / set"} v={rupees(Math.abs(p.entry))} />
            <Stat k="Stop (P/L)" v={signedRupees(p.stop_pnl)} tone="down" />
            <Stat k="Target (P/L)" v={signedRupees(p.target_pnl)} tone="up" />
          </>
        ) : (
          <>
            <Stat k="Entry" v={num(p.entry)} />
            <Stat k="Stop" v={num(p.stop)} tone="down" hint={p.underlying_stop != null && p.kind === "option" ? `underlying ${num(p.underlying_stop)}` : undefined} />
            <Stat k="Target" v={num(p.target)} tone="up" hint={p.underlying_target != null && p.kind === "option" ? `underlying ${num(p.underlying_target)}` : undefined} />
          </>
        )}
        <Stat k={`Risk / ${p.unit}`} v={rupees(p.risk_per_unit)} />
        <Stat k={`Reward / ${p.unit}`} v={rupees(p.reward_per_unit)} />
      </div>
      <p className="small muted" style={{ marginBottom: 0 }}>Square off by {p.squareoff} IST · {p.stop_rule} / {p.target_rule}</p>
    </Card>
  );
}

function PlanStep({ state, next, fromStrategy }: { state?: PlanState; next: () => void; fromStrategy: boolean }) {
  const qc = useQueryClient();
  const isIndex = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"].includes(state?.setup?.symbol ?? "");
  const [kind, setKind] = useState(fromStrategy && state?.strategy ? "strategy" : isIndex || !state?.setup ? "option" : "equity");
  const [stop, setStop] = useState(STOPS[kind][0].value);
  const [target, setTarget] = useState(TARGETS[kind][0].value);
  const [option, setOption] = useState("auto");
  const [offset, setOffset] = useState(0);
  const save = useMutation({
    mutationFn: () => api<Plan>("/plan", { json: { kind, stop, target, option, strike_offset: offset } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["plan"] }),
  });
  const pick = (k: string) => { setKind(k); setStop(STOPS[k][0].value); setTarget(TARGETS[k][0].value); };
  const p = save.data ?? state?.plan;
  return (
    <div className="grid grid-2">
      <Card title="Stop and target — set before entry">
        <div className="stack">
          <div className="field"><label>Instrument</label>
            <select className="select" value={kind} onChange={(e) => pick(e.target.value)}>
              <option value="option">Long option (CE/PE)</option>
              <option value="equity">Cash equity (MIS)</option>
              <option value="future">Future</option>
              <option value="strategy" disabled={!state?.strategy}>Saved strategy</option>
            </select>
          </div>
          {kind === "option" && (
            <div className="grid grid-2" style={{ gap: 10 }}>
              <div className="field"><label>Option</label>
                <select className="select" value={option} onChange={(e) => setOption(e.target.value)}><option value="auto">Auto (CE long / PE short)</option><option>CE</option><option>PE</option></select>
              </div>
              <div className="field"><label>Strikes OTM</label><input className="input" type="number" value={offset} onChange={(e) => setOffset(+e.target.value)} /></div>
            </div>
          )}
          <div className="field"><label>Stop</label>
            <select className="select" value={stop} onChange={(e) => setStop(e.target.value)}>{STOPS[kind].map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
          </div>
          <div className="field"><label>Target</label>
            <select className="select" value={target} onChange={(e) => setTarget(e.target.value)}>{TARGETS[kind].map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
          </div>
          <button className="btn btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? <Spinner /> : "Save plan"}</button>
          <ErrorBox error={save.error} />
        </div>
      </Card>
      <div className="stack">
        {p ? <PlanCard p={p} /> : <Card><p className="muted">No plan yet.</p></Card>}
        <div><button className="btn btn-primary" onClick={next} disabled={!p}>Next: check the odds →</button></div>
      </div>
    </div>
  );
}

function ProbBar({ mc }: { mc: TimeMachine["monte_carlo"] }) {
  const parts = [
    { k: "Target", v: mc.p_target, c: "var(--up-mark)" },
    { k: "Open at square-off", v: mc.p_flat, c: "var(--muted)" },
    { k: "Stop", v: mc.p_stop, c: "var(--down-mark)" },
  ];
  return (
    <div>
      <div style={{ display: "flex", gap: 2, height: 14, borderRadius: 4, overflow: "hidden" }} role="img" aria-label="Outcome probabilities">
        {parts.map((p) => <div key={p.k} style={{ width: `${p.v * 100}%`, background: p.c }} />)}
      </div>
      <div className="stats" style={{ marginTop: 14 }}>
        {parts.map((p) => <Stat key={p.k} k={<><i style={{ display: "inline-block", width: 9, height: 9, borderRadius: 3, background: p.c, marginRight: 6 }} />{p.k}</>} v={`${(p.v * 100).toFixed(1)}%`} />)}
      </div>
    </div>
  );
}

function OddsStep({ next }: { next: () => void }) {
  const run = useMutation({ mutationFn: (paths: number) => api<TimeMachine>("/timemachine", { json: { paths } }) });
  const r = run.data;
  return (
    <div className="stack">
      <Card title="Time Machine" right={<div className="row">{[2000, 10000].map((n) => <button key={n} className="btn btn-sm" onClick={() => run.mutate(n)} disabled={run.isPending}>Run {n.toLocaleString("en-IN")} paths</button>)}</div>}>
        {run.isPending && <Loading h={120} />}
        <ErrorBox error={run.error} />
        {r && (
          <div className="stack">
            <ProbBar mc={r.monte_carlo} />
            <div className="stats">
              <Stat k="Mean P/L / unit" v={signedRupees(r.monte_carlo.pnl_per_unit.mean)} tone={r.monte_carlo.pnl_per_unit.mean >= 0 ? "up" : "down"} />
              <Stat k="Median" v={signedRupees(r.monte_carlo.pnl_per_unit.median)} />
              <Stat k="5th – 95th pct" v={`${signedRupees(r.monte_carlo.pnl_per_unit.p5)} … ${signedRupees(r.monte_carlo.pnl_per_unit.p95)}`} />
              <Stat k="Expected R" v={num(r.monte_carlo.expected_r, 2)} />
            </div>
            {r.replay.fired != null && (
              <p className="small text-2" style={{ margin: 0 }}>Replay: the rule fired on {r.replay.fired} of {r.replay.sessions} prior sessions · win rate {r.replay.win_rate != null ? `${(r.replay.win_rate * 100).toFixed(0)}%` : "—"} · average {num(r.replay.avg_r, 2)} R</p>
            )}
            <p className="small muted" style={{ margin: 0 }}>{r.caveat} Sampled {r.monte_carlo.sessions_sampled} sessions, {time(r.monte_carlo.from)}–{time(r.monte_carlo.to)} IST.</p>
          </div>
        )}
        {!r && !run.isPending && <p className="muted small">Simulate 10,000 sessions from the same time of day before risking money.</p>}
      </Card>
      <div><button className="btn btn-primary" onClick={next}>Next: size the position →</button></div>
    </div>
  );
}

function SizeStep({ next }: { next: () => void }) {
  const qc = useQueryClient();
  const [maxLoss, setMaxLoss] = useState("");
  const size = useMutation({
    mutationFn: () => api<Orders>("/size", { json: { max_loss: maxLoss ? Number(maxLoss) : null } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["orders"] }),
  });
  const o = size.data;
  return (
    <div className="stack">
      <Card title="Budget">
        <div className="row">
          <input className="input" placeholder="Max loss (₹) — blank uses config" value={maxLoss} onChange={(e) => setMaxLoss(e.target.value.replace(/[^\d.]/g, ""))} style={{ width: 280 }} />
          <button className="btn btn-primary" onClick={() => size.mutate()} disabled={size.isPending}>{size.isPending ? <Spinner /> : "Size it"}</button>
        </div>
        <ErrorBox error={size.error} />
        {o && (
          <div className="stack" style={{ marginTop: 16 }}>
            <div className="stats">
              <Stat k={o.unit === "share" ? "Shares" : o.unit === "lot" ? "Lots" : "Sets"} v={o.units} hint={o.unit !== "share" ? `lot size ${o.lot_size}` : undefined} />
              <Stat k="Loss at stop" v={rupees(o.loss_at_stop)} tone="down" hint={`incl. ₹${num(o.charges.if_stopped, 0)} charges`} />
              <Stat k="Profit at target" v={rupees(o.profit_at_target)} tone="up" hint={`net of ₹${num(o.charges.if_target, 0)} charges`} />
              <Stat k="Margin" v={rupees(o.margin.total)} hint={o.margin.source} />
            </div>
            <table className="table">
              <thead><tr><th>Leg</th><th>Side</th><th>Qty</th><th>Price</th></tr></thead>
              <tbody>{o.legs.map((l) => <tr key={l.symbol + l.side}><td>{l.symbol}</td><td><Badge tone={l.side === "BUY" ? "up" : "down"}>{l.side}</Badge></td><td>{l.quantity}{l.lots ? ` (${l.lots} lot)` : ""}</td><td>{num(l.price)}</td></tr>)}</tbody>
            </table>
            {o.notes.map((n) => <span key={n} className="small muted">{n}</span>)}
          </div>
        )}
      </Card>
      <div><button className="btn btn-primary" onClick={next} disabled={!o}>Next: risk check →</button></div>
    </div>
  );
}

function RiskStep({ next }: { next: () => void }) {
  const qc = useQueryClient();
  const check = useMutation({ mutationFn: () => api<RiskVerdict>("/risk", { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["orders"] }) });
  const r = check.data;
  return (
    <div className="stack">
      <div><button className="btn btn-primary" onClick={() => check.mutate()} disabled={check.isPending}>{check.isPending ? <Spinner /> : "Run risk check"}</button></div>
      <ErrorBox error={check.error} />
      {r && (
        <>
          <div className={`banner ${r.verdict === "PASS" ? "pass" : "block"}`}>
            <div style={{ width: 28, color: r.verdict === "PASS" ? "var(--up)" : "var(--down)" }}>{r.verdict === "PASS" ? Icons.check : Icons.cross}</div>
            <div>
              <div className="banner-title">{r.verdict}</div>
              <div className="small text-2">{r.verdict === "PASS" ? "Every rule passed. The verdict is bound to this exact order for 10 minutes." : `${r.reasons.length} rule(s) failed. Fix them, then re-size and re-check.`}</div>
            </div>
          </div>
          <Card title="Checks">
            <table className="table"><tbody>
              {r.checks.map((c) => (
                <tr key={c.rule}>
                  <td style={{ width: 28, color: c.ok ? "var(--up)" : "var(--down)" }}><span style={{ display: "inline-block", width: 16 }}>{c.ok ? Icons.check : Icons.cross}</span></td>
                  <td style={{ textAlign: "left" }}><b>{c.rule}</b></td>
                  <td style={{ textAlign: "left", whiteSpace: "normal" }} className="text-2 small">{c.detail}</td>
                </tr>
              ))}
            </tbody></table>
          </Card>
          <div><button className="btn btn-primary" onClick={next} disabled={r.verdict !== "PASS"}>Next: ticket →</button></div>
        </>
      )}
    </div>
  );
}

function TicketStep() {
  const qc = useQueryClient();
  const [typed, setTyped] = useState("");
  const t = useQuery({ queryKey: ["ticket"], queryFn: () => api<Ticket>("/ticket"), retry: false });
  const confirm = useMutation({
    mutationFn: () => api<{ confirmed: string; next: string }>("/ticket/confirm", { json: { hash: t.data!.order_hash, typed } }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const alerts = useMutation({ mutationFn: () => api("/alerts", { json: { from_plan: true } }) });
  if (t.isLoading) return <Loading h={200} />;
  if (t.error) return <ErrorBox error={t.error} />;
  const k = t.data!;
  return (
    <div className="stack">
      <Card title={`Order ticket · ${k.order_hash}`} right={<Badge tone={k.mode === "paper" ? "warn" : "accent"}>{k.mode} mode</Badge>}>
        <table className="table">
          <thead><tr><th>Action</th><th>Contract</th><th>Type</th><th>Qty</th><th>Price</th><th>Product</th></tr></thead>
          <tbody>{k.entries.map((e) => (
            <tr key={e.symbol + e.action}><td><Badge tone={e.action === "BUY" ? "up" : "down"}>{e.action}</Badge></td><td>{e.symbol}</td><td>{e.order_type}</td><td>{e.quantity}{e.lots ? ` (${e.lots} lot)` : ""}</td><td>{num(e.price)}</td><td>{e.product}</td></tr>
          ))}</tbody>
        </table>
        <h3 className="card-title" style={{ marginTop: 18 }}>Exits</h3>
        <ul className="small text-2" style={{ margin: 0, paddingLeft: 18 }}>
          {k.exits.map((x, i) => <li key={i}><b>{String(x.note ?? x.action)}</b>: {[x.action, x.order_type, x.trigger_price != null && `trigger ${x.trigger_price}`, x.price != null && `price ${x.price}`, x.condition].filter(Boolean).join(" · ")}</li>)}
        </ul>
        <p className="small muted">{k.oco} Square off by {k.square_off} IST.</p>
        <div className="stats">
          <Stat k="Loss at stop" v={rupees(k.loss_at_stop)} tone="down" />
          <Stat k="Profit at target" v={rupees(k.profit_at_target)} tone="up" />
          <Stat k="Margin" v={rupees(k.margin.total)} />
        </div>
      </Card>
      {confirm.data ? (
        <div className="banner pass">
          <div>
            <div className="banner-title">Confirmed {confirm.data.confirmed}</div>
            <div className="small text-2">{confirm.data.next}</div>
            <button className="btn btn-sm" style={{ marginTop: 10 }} onClick={() => alerts.mutate()} disabled={alerts.isSuccess}>{alerts.isSuccess ? "Alerts added ✓" : "Add stop / target / square-off alerts"}</button>
          </div>
        </div>
      ) : (
        <Card title="Confirm">
          <p className="small text-2" style={{ marginTop: 0 }}>This records your decision. Nothing is sent to a broker — you place the order yourself.</p>
          <div className="row">
            <input className="input" placeholder='Type "yes" to confirm' value={typed} onChange={(e) => setTyped(e.target.value)} aria-label="Type yes to confirm" style={{ width: 220 }} />
            <button className="btn btn-primary" disabled={typed.trim().toLowerCase() !== "yes" || confirm.isPending} onClick={() => confirm.mutate()}>Confirm order</button>
          </div>
          <ErrorBox error={confirm.error} />
        </Card>
      )}
    </div>
  );
}

export function Trade() {
  const [params] = useSearchParams();
  const fromStrategy = params.get("from") === "strategy";
  const [step, setStep] = useState(fromStrategy ? 1 : 0);
  const state = useQuery({ queryKey: ["plan"], queryFn: () => api<PlanState>("/plan") });
  const orders = useQuery({ queryKey: ["orders"], queryFn: () => api<{ orders: Orders | null; risk: RiskVerdict | null }>("/orders") });
  const s = state.data;
  const pass = orders.data?.risk?.verdict === "PASS" && orders.data.risk.order_hash === orders.data.orders?.hash;
  const done = [!!(s?.setup || s?.strategy), !!s?.plan, false, !!orders.data?.orders, pass, false];
  const next = () => setStep((i) => Math.min(STEPS.length - 1, i + 1));

  return (
    <>
      <PageHead title="Trade" sub="Stop first, size from the loss, pass risk, then you decide" />
      <Stepper step={step} done={done} onPick={setStep} />
      <ErrorBox error={state.error} />
      {step === 0 && <SetupStep state={s} next={next} />}
      {step === 1 && <PlanStep key={String(!!s)} state={s} next={next} fromStrategy={fromStrategy} />}
      {step === 2 && <OddsStep next={next} />}
      {step === 3 && <SizeStep next={next} />}
      {step === 4 && <RiskStep next={next} />}
      {step === 5 && <TicketStep />}
    </>
  );
}
