import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { compact, dateShort, num, pct, time, tone } from "../lib/format";
import { Badge, Card, ErrorBox, Loading, PageHead, Seg } from "../ui";

type Tab = "news" | "ban" | "deals" | "insider" | "results";

interface Announcement { symbol: string; subject: string; detail: string; time: string; attachment?: string }
interface Deal { date: string; symbol: string; clientName: string; buySell: string; qty: string; watp: string }
interface Insider { symbol: string; person: string; category: string; type: string; quantity: string; value: string; mode: string; to: string }
interface Quarter { period_end: string; revenue: number | null; net_profit: number | null; eps: number | null; revenue_yoy_pct?: number; net_profit_yoy_pct?: number; revenue_qoq_pct?: number }

function News() {
  const [symbols, setSymbols] = useState("");
  const q = useQuery({ queryKey: ["news", symbols], queryFn: () => api<{ announcements: Announcement[]; symbols: string[] }>(`/news?hours=72${symbols ? `&symbols=${symbols}` : ""}`) });
  return (
    <Card title="NSE corporate announcements · last 72 h" right={<input className="input" placeholder="Symbols, comma separated (default: watchlist)" value={symbols} onChange={(e) => setSymbols(e.target.value.toUpperCase())} style={{ width: 300 }} />}>
      <ErrorBox error={q.error} />
      {q.isLoading && <Loading />}
      {q.data?.announcements.length === 0 && <div className="empty">No announcements for {q.data.symbols.join(", ")}.</div>}
      {q.data?.announcements.map((a, i) => (
        <article key={i} style={{ padding: "12px 0", borderBottom: "1px solid var(--border)" }}>
          <div className="row between"><div className="row"><Badge tone="accent">{a.symbol}</Badge><b>{a.subject}</b></div><span className="small muted">{dateShort(a.time)} {time(a.time)}</span></div>
          <p className="small text-2" style={{ margin: "6px 0 0" }}>{a.detail}</p>
          {a.attachment && <a className="small" style={{ color: "var(--accent)" }} href={a.attachment} target="_blank" rel="noreferrer">Filing ↗</a>}
        </article>
      ))}
    </Card>
  );
}

function Ban() {
  const q = useQuery({ queryKey: ["ban"], queryFn: () => api<{ ban_list: string[] }>("/ban") });
  return (
    <Card title="F&O ban list — no fresh positions today">
      <ErrorBox error={q.error} />
      {q.data && (q.data.ban_list.length ? <div className="row">{q.data.ban_list.map((s) => <Badge key={s} tone="down">{s}</Badge>)}</div> : <div className="empty">No securities in ban.</div>)}
    </Card>
  );
}

function Deals() {
  const q = useQuery({ queryKey: ["deals"], queryFn: () => api<{ bulk: Deal[]; block: Deal[] }>("/insider/deals") });
  return (
    <div className="stack">
      <ErrorBox error={q.error} />
      {(["bulk", "block"] as const).map((k) => (
        <Card key={k} title={k === "bulk" ? "Bulk deals (> 0.5% of shares)" : "Block deals"}>
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Symbol</th><th>Client</th><th>Side</th><th>Qty</th><th>Avg price</th></tr></thead>
            <tbody>{q.data?.[k].map((d, i) => (
              <tr key={i}><td><b>{d.symbol}</b></td><td style={{ textAlign: "left" }}>{d.clientName}</td><td><Badge tone={d.buySell === "BUY" ? "up" : "down"}>{d.buySell}</Badge></td><td>{compact(Number(d.qty))}</td><td>{num(Number(d.watp))}</td></tr>
            ))}</tbody>
          </table></div>
        </Card>
      ))}
    </div>
  );
}

function InsiderTab() {
  const [symbol, setSymbol] = useState("");
  const q = useQuery({ queryKey: ["pit", symbol], queryFn: () => api<Insider[]>(`/insider/pit?days=90${symbol ? `&symbol=${symbol}` : ""}`) });
  return (
    <Card title="Insider disclosures (SEBI PIT) · 90 days" right={<input className="input" placeholder="Symbol" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} style={{ width: 160 }} />}>
      <ErrorBox error={q.error} />
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Symbol</th><th>Person</th><th>Type</th><th>Qty</th><th>Value</th><th>Mode</th><th>Date</th></tr></thead>
        <tbody>{q.data?.map((d, i) => (
          <tr key={i}><td><b>{d.symbol}</b></td><td style={{ textAlign: "left" }}>{d.person}<div className="small muted">{d.category}</div></td><td><Badge tone={/buy/i.test(d.type) ? "up" : "down"}>{d.type}</Badge></td><td>{compact(Number(d.quantity))}</td><td>₹{compact(Number(d.value))}</td><td className="text-2">{d.mode}</td><td className="muted">{d.to}</td></tr>
        ))}</tbody>
      </table></div>
      <p className="small muted" style={{ marginBottom: 0 }}>Promoter market purchases say more than ESOP allotments or pledges. Disclosures lag the trade by up to 2 trading days.</p>
    </Card>
  );
}

function Results() {
  const [symbol, setSymbol] = useState("RELIANCE");
  const q = useQuery({ queryKey: ["results", symbol], queryFn: () => api<{ quarters: Quarter[]; note: string }>(`/results/${symbol}`), enabled: !!symbol });
  return (
    <Card title="Quarterly results" right={<input className="input" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} style={{ width: 160 }} aria-label="Symbol" />}>
      <ErrorBox error={q.error} />
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Quarter</th><th>Revenue</th><th>YoY</th><th>Net profit</th><th>YoY</th><th>EPS</th></tr></thead>
        <tbody>{q.data?.quarters.map((r) => (
          <tr key={r.period_end}><td>{r.period_end}</td><td>{num(r.revenue, 0)}</td><td className={tone(r.revenue_yoy_pct)}>{pct(r.revenue_yoy_pct, 1)}</td><td>{num(r.net_profit, 0)}</td><td className={tone(r.net_profit_yoy_pct)}>{pct(r.net_profit_yoy_pct, 1)}</td><td>{num(r.eps)}</td></tr>
        ))}</tbody>
      </table></div>
      {q.data && <p className="small muted" style={{ marginBottom: 0 }}>{q.data.note}</p>}
    </Card>
  );
}

export function Research() {
  const [tab, setTab] = useState<Tab>("news");
  return (
    <>
      <PageHead title="Research" sub="Public NSE data — unofficial endpoints, may lag or rate limit"
        right={<Seg value={tab} onChange={setTab} options={[{ value: "news", label: "News" }, { value: "ban", label: "Ban list" }, { value: "deals", label: "Deals" }, { value: "insider", label: "Insider" }, { value: "results", label: "Results" }]} />} />
      {tab === "news" && <News />}
      {tab === "ban" && <Ban />}
      {tab === "deals" && <Deals />}
      {tab === "insider" && <InsiderTab />}
      {tab === "results" && <Results />}
    </>
  );
}
