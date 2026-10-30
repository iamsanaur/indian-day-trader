import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getConnection, saveConnection } from "../lib/api";
import { Badge, Card, ErrorBox, PageHead, Seg } from "../ui";
import { DhanCardBody } from "../DhanSession";
import type { Status } from "../lib/types";

type Theme = "system" | "light" | "dark";

export function applyTheme(t: Theme) {
  if (t === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem("idt.theme", t); } catch { /* ignore */ }
}

export function storedTheme(): Theme {
  try { return (localStorage.getItem("idt.theme") as Theme) || "system"; } catch { return "system"; }
}

interface Config { config: Record<string, string | number | boolean>; editable: string[]; data_provider: string }

const LABELS: Record<string, string> = {
  capital: "Paper capital (₹)", max_loss_per_trade: "Max loss per trade (₹)", daily_loss_cap: "Daily loss cap (₹)",
  max_trades_per_day: "Max trades per day", leverage_cap: "Leverage cap (×)", or_minutes: "Opening range (minutes)",
  entry_expiry: "ORB expires at", entry_cutoff: "No new entries after", squareoff: "Square off by",
  min_premium: "Minimum option premium (₹)", stale_quote_seconds: "Stale price limit (s)",
  allow_short: "Allow shorting", allow_naked: "Allow naked short options", block_expiry_day_selling: "Block expiry-day selling",
  require_ban_check: "Require F&O ban check",
};

export function Settings() {
  const qc = useQueryClient();
  const [conn, setConn] = useState(getConnection());
  const [theme, setTheme] = useState<Theme>(storedTheme());
  const [draft, setDraft] = useState<Record<string, string | number | boolean>>({});
  const health = useQuery({ queryKey: ["health", conn.url], queryFn: () => api<{ ok: boolean; version: string; demo: boolean; now: string }>("/health"), retry: false });
  const cfg = useQuery({ queryKey: ["config"], queryFn: () => api<Config>("/config"), retry: false });
  const status = useQuery({ queryKey: ["status"], queryFn: () => api<Status>("/status"), retry: false });
  useEffect(() => { if (cfg.data) setDraft(cfg.data.config); }, [cfg.data]);
  const save = useMutation({
    mutationFn: (changes: object) => api<Config>("/config", { method: "PATCH", json: changes }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const changed = cfg.data ? Object.fromEntries(Object.entries(draft).filter(([k, v]) => cfg.data!.config[k] !== v)) : {};

  return (
    <>
      <PageHead title="Settings" />
      <div className="grid grid-2">
        <Card title="Server" right={health.data ? <Badge tone="up">connected · v{health.data.version}{health.data.demo ? " · demo" : ""}</Badge> : <Badge tone="down">not connected</Badge>}>
          <div className="stack">
            <div className="field"><label>Server URL (blank = this site)</label><input className="input" value={conn.url} onChange={(e) => setConn({ ...conn, url: e.target.value })} placeholder="http://192.168.1.10:8742" /></div>
            <div className="field"><label>Access token (printed by <code>idt serve</code>)</label><input className="input" type="password" value={conn.token} onChange={(e) => setConn({ ...conn, token: e.target.value })} /></div>
            <button className="btn btn-primary" onClick={() => { saveConnection(conn); qc.invalidateQueries(); }}>Save & connect</button>
            <ErrorBox error={cfg.error} />
          </div>
        </Card>
        {status.data?.dhan && <Card title="Dhan session"><DhanCardBody status={status.data.dhan} /></Card>}
        <Card title="Appearance">
          <Seg value={theme} onChange={(t) => { setTheme(t); applyTheme(t); }} options={[{ value: "system", label: "System" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }]} />
        </Card>
        {cfg.data && (
          <Card title="Mode" className="">
            <div className="stack">
              <Seg value={String(draft.mode)} onChange={(m) => setDraft({ ...draft, mode: m })} options={[{ value: "paper", label: "Paper" }, { value: "live", label: "Live" }]} />
              <span className="small text-2">Live mode reads available funds from your broker for the margin check. Orders are never placed either way.</span>
            </div>
          </Card>
        )}
        {cfg.data && (
          <Card title="Risk limits" right={<button className="btn btn-sm btn-primary" disabled={!Object.keys(changed).length || save.isPending} onClick={() => save.mutate(changed)}>Save {Object.keys(changed).length || ""}</button>}>
            <div className="stack">
              {Object.keys(LABELS).filter((k) => k in draft).map((k) => (
                typeof draft[k] === "boolean" ? (
                  <label key={k} className="row between" style={{ cursor: "pointer" }}>
                    <span>{LABELS[k]}</span>
                    <input type="checkbox" checked={draft[k] as boolean} onChange={(e) => setDraft({ ...draft, [k]: e.target.checked })} style={{ width: 18, height: 18, accentColor: "var(--accent)" }} />
                  </label>
                ) : (
                  <div key={k} className="row between">
                    <label className="text-2" htmlFor={k}>{LABELS[k]}</label>
                    <input id={k} className="input num" style={{ width: 130, textAlign: "right" }} value={String(draft[k])}
                      onChange={(e) => setDraft({ ...draft, [k]: typeof cfg.data!.config[k] === "number" ? Number(e.target.value) || 0 : e.target.value })} />
                  </div>
                )
              ))}
              {draft.allow_naked === true && <div className="banner warn small">Naked short options can lose far more than the premium collected.</div>}
              <ErrorBox error={save.error} />
            </div>
          </Card>
        )}
      </div>
    </>
  );
}
