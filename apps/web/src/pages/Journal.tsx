import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { JournalEntry, Status } from "../lib/types";
import { dateShort, rupees, signedRupees, time, tone } from "../lib/format";
import { Badge, Card, ErrorBox, PageHead, Stat } from "../ui";

export function Journal() {
  const qc = useQueryClient();
  const [pnl, setPnl] = useState("");
  const [symbol, setSymbol] = useState("");
  const [note, setNote] = useState("");
  const status = useQuery({ queryKey: ["status"], queryFn: () => api<Status>("/status") });
  const journal = useQuery({ queryKey: ["journal"], queryFn: () => api<JournalEntry[]>("/journal?tail=100") });
  const close = useMutation({
    mutationFn: () => api("/journal/close", { json: { pnl: Number(pnl), symbol: symbol || null, note: note || null } }),
    onSuccess: () => { setPnl(""); setNote(""); qc.invalidateQueries({ queryKey: ["journal"] }); qc.invalidateQueries({ queryKey: ["status"] }); },
  });
  const s = status.data;
  const cap = Number(s?.limits.daily_loss_cap ?? 0);
  const used = s ? Math.max(0, -s.realised_today) : 0;

  return (
    <>
      <PageHead title="Journal" sub="Confirmed tickets and closed trades. Closed P/L feeds the daily loss cap." />
      <ErrorBox error={status.error ?? journal.error ?? close.error} />
      <div className="split">
        <Card title="History">
          {(journal.data ?? []).length === 0 && <div className="empty">No entries yet.</div>}
          <table className="table">
            <tbody>
              {[...(journal.data ?? [])].reverse().map((e, i) => (
                <tr key={i}>
                  <td><Badge tone={e.type === "close" ? tone(e.pnl) : "accent"}>{e.type === "close" ? "Closed" : "Confirmed"}</Badge></td>
                  <td style={{ textAlign: "left" }}><b>{e.symbol ?? "—"}</b> <span className="small muted">{e.kind ?? e.note ?? ""}</span></td>
                  <td className={e.type === "close" ? tone(e.pnl) : "text-2"}>{e.type === "close" ? signedRupees(e.pnl) : `risk ${rupees(e.loss_at_stop)}`}</td>
                  <td className="muted small">{dateShort(e.ts)} {time(e.ts)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <div className="stack">
          <Card title="Today">
            <div className="stats">
              <Stat k="Trades confirmed" v={s?.trades_today ?? "—"} hint={s ? `limit ${s.limits.max_trades_per_day}` : undefined} />
              <Stat k="Realised P/L" v={signedRupees(s?.realised_today)} tone={tone(s?.realised_today)} />
            </div>
            {cap > 0 && (
              <div style={{ marginTop: 14 }}>
                <div className="row between small text-2"><span>Daily loss cap used</span><span className="num">{rupees(used)} / {rupees(cap)}</span></div>
                <div style={{ height: 8, borderRadius: 99, background: "var(--surface-2)", marginTop: 6, overflow: "hidden" }}>
                  <div style={{ width: `${Math.min(100, (used / cap) * 100)}%`, height: "100%", background: used / cap > 0.75 ? "var(--down-mark)" : "var(--accent)" }} />
                </div>
              </div>
            )}
          </Card>
          <Card title="Record a closed trade">
            <div className="stack">
              <div className="field"><label>Realised P/L (₹, negative for a loss)</label><input className="input" value={pnl} onChange={(e) => setPnl(e.target.value.replace(/[^\d.-]/g, ""))} placeholder="-850" /></div>
              <div className="field"><label>Symbol</label><input className="input" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} placeholder="NIFTY" /></div>
              <div className="field"><label>Note</label><input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Stopped at OR mid" /></div>
              <button className="btn btn-primary" disabled={!pnl || isNaN(Number(pnl))} onClick={() => close.mutate()}>Save</button>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
