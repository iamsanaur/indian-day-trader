import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Board, BoardEntry, IndexView, Orb } from "../lib/types";
import { num, pct, time, tone } from "../lib/format";
import { Badge, Card, ErrorBox, Loading, OrbBadge, PageHead, Seg, Stat, TrendBadge } from "../ui";
import { CandleChart } from "../charts/CandleChart";

const NAMES: Record<string, string> = {
  NIFTY: "Nifty 50", BANKNIFTY: "Nifty Bank", FINNIFTY: "Nifty Financial", MIDCPNIFTY: "Nifty Midcap Select",
  SENSEX: "BSE Sensex", INDIAVIX: "India VIX",
};

function DayRange({ e }: { e: BoardEntry }) {
  const span = e.day.high - e.day.low || 1;
  const at = ((e.last - e.day.low) / span) * 100;
  return (
    <div>
      <div style={{ position: "relative", height: 6, borderRadius: 99, background: "var(--surface-2)", margin: "10px 0 6px" }}>
        <div style={{ position: "absolute", left: `calc(${Math.min(100, Math.max(0, at))}% - 5px)`, top: -3, width: 12, height: 12, borderRadius: 99, background: "var(--text)", border: "2px solid var(--surface)" }} />
      </div>
      <div className="row between small muted num">
        <span>L {num(e.day.low)}</span>
        <span>H {num(e.day.high)}</span>
      </div>
    </div>
  );
}

function IndexCard({ sym, e }: { sym: string; e: BoardEntry }) {
  if (e.error) return <Card title={sym}><ErrorBox error={e.error} /></Card>;
  const vix = sym === "INDIAVIX";
  return (
    <Link to={`/markets/${sym}`} className="card" style={{ display: "block" }}>
      <div className="row between">
        <div>
          <div style={{ fontWeight: 700 }}>{sym}</div>
          <div className="small muted">{NAMES[sym]}</div>
        </div>
        <Badge tone={tone(e.change_pct)}>{pct(e.change_pct)}</Badge>
      </div>
      <div className="num" style={{ fontSize: 28, fontWeight: 700, letterSpacing: "-0.02em", margin: "12px 0 2px" }}>{num(e.last)}</div>
      <DayRange e={e} />
      {!vix && (
        <div className="row" style={{ marginTop: 12 }}>
          <OrbBadge state={e.orb.state} side={e.orb.side} />
          <TrendBadge trend={e.ema.trend} />
        </div>
      )}
      {vix && <div className="small text-2" style={{ marginTop: 12 }}>Implied volatility gauge — higher means richer option premiums.</div>}
    </Link>
  );
}

export function Markets() {
  const q = useQuery({ queryKey: ["indices"], queryFn: () => api<Board>("/indices"), refetchInterval: 30_000 });
  return (
    <>
      <PageHead title="Markets" sub={q.data ? `Indices as of ${time(q.data.as_of)} IST` : "NSE & BSE indices"} />
      <ErrorBox error={q.error} />
      <div className="grid grid-auto">
        {q.isLoading && Array.from({ length: 6 }, (_, i) => <Loading key={i} h={190} />)}
        {q.data && Object.entries(q.data.indices).map(([sym, e]) => <IndexCard key={sym} sym={sym} e={e} />)}
      </div>
    </>
  );
}

function orbLine(o: Orb) {
  if (o.state === "triggered") return `Triggered ${o.side} at ${num(o.entry)} (${time(o.trigger_time)} bar)`;
  return o.detail ?? o.state;
}

export function IndexDetail() {
  const { symbol = "NIFTY" } = useParams();
  const nav = useNavigate();
  const [interval, setInterval] = useState(5);
  const [days, setDays] = useState(2);
  const [future, setFuture] = useState(false);
  const q = useQuery({
    queryKey: ["index", symbol, interval, days, future],
    queryFn: () => api<IndexView>(`/index/${symbol}?interval=${interval}&days=${days}&future=${future}`),
  });
  const entry = useMutation({
    mutationFn: () => api(`/entry/${symbol}`, { json: { setup: "orb", write: true } }),
    onSuccess: () => nav("/trade"),
  });
  const v = q.data;

  return (
    <>
      <PageHead
        title={future ? `${symbol} FUT` : symbol}
        sub={v ? <>Last <b className="num">{num(v.last)}</b> <span className={tone(v.change_pct)}>{pct(v.change_pct)}</span> · {time(v.as_of)} IST</> : NAMES[symbol]}
        right={
          <>
            <Seg value={interval} onChange={setInterval} options={[1, 5, 15].map((m) => ({ value: m, label: `${m}m` }))} />
            <Seg value={days} onChange={setDays} options={[1, 2, 5].map((d) => ({ value: d, label: `${d}D` }))} />
            {symbol !== "INDIAVIX" && <Seg value={future ? "fut" : "spot"} onChange={(x) => setFuture(x === "fut")} options={[{ value: "spot", label: "Spot" }, { value: "fut", label: "Future" }]} />}
          </>
        }
      />
      <ErrorBox error={q.error ?? entry.error} />
      <div className="split">
        <Card>{v ? <CandleChart view={v} /> : <Loading h={420} />}</Card>
        <div className="stack">
          <Card title="Opening range" right={v && <OrbBadge state={v.orb.state} side={v.orb.side} />}>
            {v?.opening_range ? (
              <>
                <div className="stats">
                  <Stat k="High" v={num(v.opening_range.high)} />
                  <Stat k="Low" v={num(v.opening_range.low)} />
                  <Stat k="Mid" v={num(v.opening_range.mid)} />
                </div>
                <p className="small text-2" style={{ marginBottom: 12 }}>{orbLine(v.orb)}</p>
                <button className="btn btn-primary" style={{ width: "100%" }} disabled={entry.isPending} onClick={() => entry.mutate()}>
                  Plan a trade from this setup
                </button>
              </>
            ) : <Loading h={80} />}
          </Card>
          <Card title="Levels">
            {v ? (
              <table className="table">
                <tbody>
                  {[
                    ["Prev high (PDH)", v.prev_day?.high], ["Prev low (PDL)", v.prev_day?.low], ["Prev close", v.prev_day?.close],
                    ["R1", v.cpr.r1], ["CPR top (TC)", v.cpr.tc], ["Pivot", v.cpr.pivot], ["CPR bottom (BC)", v.cpr.bc], ["S1", v.cpr.s1],
                    ["EMA 9", v.ema.ema9], ["EMA 21", v.ema.ema21], ["VWAP", v.vwap],
                  ].map(([k, val]) => (
                    <tr key={k as string}><td className="text-2">{k}</td><td>{num(val as number | null)}</td></tr>
                  ))}
                </tbody>
              </table>
            ) : <Loading h={200} />}
          </Card>
          {v && (
            <Card title="Read">
              <div className="stack small">
                <div className="row"><TrendBadge trend={v.ema.trend} /></div>
                <span className="text-2">{v.cpr_read}</span>
                {v.vwap_note && <span className="muted">Spot indices have no volume, so VWAP is blank. Switch to Future for VWAP.</span>}
              </div>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
