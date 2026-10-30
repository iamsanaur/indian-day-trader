import { useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "./lib/api";
import type { Alert, Status } from "./lib/types";
import { time } from "./lib/format";
import { Badge, Icons } from "./ui";
import { IndexDetail, Markets } from "./pages/Markets";
import { Options } from "./pages/Options";
import { Strategy } from "./pages/Strategy";
import { Trade } from "./pages/Trade";
import { Alerts, useAlertStream } from "./pages/Alerts";
import { Journal } from "./pages/Journal";
import { Research } from "./pages/Research";
import { Settings } from "./pages/Settings";

const NAV = [
  { to: "/", label: "Markets", icon: Icons.markets, end: true },
  { to: "/options", label: "Options", icon: Icons.options },
  { to: "/strategy", label: "Strategy", icon: Icons.strategy },
  { to: "/trade", label: "Trade", icon: Icons.trade },
  { to: "/alerts", label: "Alerts", icon: Icons.alerts },
  { to: "/journal", label: "Journal", icon: Icons.journal },
  { to: "/research", label: "Research", icon: Icons.research },
  { to: "/settings", label: "Settings", icon: Icons.settings },
];
const TABS = ["/", "/options", "/trade", "/alerts"];

function More() {
  return (
    <div className="stack">
      <h1 style={{ margin: "0 0 6px", fontSize: 26 }}>More</h1>
      {NAV.filter((n) => !TABS.includes(n.to)).map((n) => (
        <NavLink key={n.to} to={n.to} className="card row" style={{ padding: 16 }}>
          <span style={{ width: 22, color: "var(--accent)" }}>{n.icon}</span><b>{n.label}</b>
        </NavLink>
      ))}
    </div>
  );
}

export function App() {
  const [toast, setToast] = useState<string | null>(null);
  const status = useQuery({ queryKey: ["status"], queryFn: () => api<Status>("/status"), refetchInterval: 60_000, retry: false });
  useAlertStream((a: Alert) => {
    setToast(`${a.label} — observed ${a.observed ?? ""}`);
    setTimeout(() => setToast(null), 8000);
  });
  const s = status.data;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">{Icons.logo}</span>Indian Day Trader</div>
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
            {n.icon}{n.label}
          </NavLink>
        ))}
        <div className="sidebar-foot stack" style={{ gap: 6 }}>
          {s ? (
            <>
              <div className="row"><Badge tone={s.mode === "paper" ? "warn" : "accent"}>{s.mode}</Badge>{s.demo && <Badge>demo</Badge>}</div>
              <span>Market {s.phase} · {time(s.now)} IST</span>
            </>
          ) : <span>Not connected — open Settings</span>}
          <span>Never places orders.</span>
        </div>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Markets />} />
          <Route path="/markets/:symbol" element={<IndexDetail />} />
          <Route path="/options" element={<Options />} />
          <Route path="/strategy" element={<Strategy />} />
          <Route path="/trade" element={<Trade />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/journal" element={<Journal />} />
          <Route path="/research" element={<Research />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/more" element={<More />} />
        </Routes>
      </main>
      <nav className="tabbar">
        {NAV.filter((n) => TABS.includes(n.to)).map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? "active" : "")}>
            {n.icon}{n.label}
          </NavLink>
        ))}
        <NavLink to="/more" className={({ isActive }) => (isActive ? "active" : "")}>{Icons.more}More</NavLink>
      </nav>
      {toast && <div className="toast" role="status">🔔 {toast}</div>}
    </div>
  );
}
