import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, eventsUrl } from "../lib/api";
import type { Alert } from "../lib/types";
import { num, time } from "../lib/format";
import { Badge, Card, ErrorBox, Loading, PageHead } from "../ui";

/** Subscribes to server-sent alert events; calls onAlert for each fired alert. */
export function useAlertStream(onAlert: (a: Alert) => void) {
  const [live, setLive] = useState(false);
  useEffect(() => {
    let es: EventSource | null = null;
    try {
      es = new EventSource(eventsUrl(15));
      es.addEventListener("tick", () => setLive(true));
      es.addEventListener("alert", (e) => onAlert(JSON.parse((e as MessageEvent).data)));
      es.onerror = () => setLive(false);
    } catch {
      setLive(false);
    }
    return () => es?.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return live;
}

function describe(a: Alert) {
  if (a.kind === "time") return `at ${a.value} IST`;
  if (a.kind === "pnl") return `combined P/L ${a.op} ₹${num(Number(a.value), 0)}`;
  return `${a.symbol} ${a.op} ${num(Number(a.value))}`;
}

export function Alerts() {
  const qc = useQueryClient();
  const [symbol, setSymbol] = useState("NIFTY");
  const [dir, setDir] = useState<"above" | "below">("above");
  const [price, setPrice] = useState("");
  const list = useQuery({ queryKey: ["alerts"], queryFn: () => api<Alert[]>("/alerts"), refetchInterval: 20_000 });
  const refresh = () => qc.invalidateQueries({ queryKey: ["alerts"] });
  const add = useMutation({ mutationFn: (body: object) => api("/alerts", { json: body }), onSuccess: () => { setPrice(""); refresh(); } });
  const check = useMutation({ mutationFn: () => api("/alerts/check", { method: "POST" }), onSuccess: refresh });
  const clear = useMutation({ mutationFn: () => api("/alerts", { method: "DELETE" }), onSuccess: refresh });
  const items = list.data ?? [];
  const pending = items.filter((a) => !a.fired);
  const fired = items.filter((a) => a.fired);

  return (
    <>
      <PageHead title="Alerts" sub="Stop, target, P/L and square-off — checked against live quotes"
        right={<><button className="btn" onClick={() => check.mutate()} disabled={check.isPending}>Check now</button><button className="btn btn-ghost" onClick={() => clear.mutate()}>Clear all</button></>} />
      <ErrorBox error={list.error ?? add.error ?? check.error} />
      <div className="split">
        <div className="stack">
          <Card title={`Pending (${pending.length})`}>
            {list.isLoading && <Loading h={80} />}
            {!list.isLoading && pending.length === 0 && <div className="empty">No pending alerts.</div>}
            {pending.map((a) => (
              <div key={a.id} className="row between" style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
                <div><b>{a.label}</b><div className="small text-2 num">{describe(a)}</div></div>
                <Badge tone="warn">watching</Badge>
              </div>
            ))}
          </Card>
          <Card title={`Fired (${fired.length})`}>
            {fired.length === 0 && <div className="empty">Nothing has fired yet.</div>}
            {fired.map((a) => (
              <div key={a.id} className="row between" style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
                <div><b>{a.label}</b><div className="small text-2 num">{describe(a)} · observed {String(a.observed ?? "—")}</div></div>
                <Badge tone={a.label.startsWith("STOP") ? "down" : a.label.startsWith("TARGET") ? "up" : ""}>{time(a.fired_at)}</Badge>
              </div>
            ))}
          </Card>
        </div>
        <div className="stack">
          <Card title="From your plan">
            <p className="small text-2" style={{ marginTop: 0 }}>Adds the stop, target and square-off for the current plan.</p>
            <button className="btn btn-primary" style={{ width: "100%" }} onClick={() => add.mutate({ from_plan: true })}>Add plan alerts</button>
          </Card>
          <Card title="Price alert">
            <div className="stack">
              <div className="field"><label>Symbol or contract</label><input className="input" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} placeholder="NIFTY or NIFTY 2026-11-03 26000 CE" /></div>
              <div className="row">
                <select className="select" value={dir} onChange={(e) => setDir(e.target.value as "above" | "below")}><option value="above">Crosses above</option><option value="below">Crosses below</option></select>
                <input className="input" value={price} onChange={(e) => setPrice(e.target.value.replace(/[^\d.]/g, ""))} placeholder="Price" style={{ flex: 1 }} />
              </div>
              <button className="btn" disabled={!price || !symbol} onClick={() => add.mutate({ symbol, [dir]: Number(price) })}>Add alert</button>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
