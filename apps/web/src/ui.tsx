import type { ReactNode } from "react";
import { ApiError } from "./lib/api";

export function PageHead({ title, sub, right }: { title: string; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {right && <div className="row">{right}</div>}
    </div>
  );
}

export function Card({ title, right, children, className = "" }: { title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || right) && (
        <h2 className="card-title">
          <span>{title}</span>
          {right}
        </h2>
      )}
      {children}
    </section>
  );
}

export function Stat({ k, v, tone = "", hint }: { k: ReactNode; v: ReactNode; tone?: string; hint?: ReactNode }) {
  return (
    <div className="stat">
      <span className="k">{k}</span>
      <span className={`v ${tone}`}>{v}</span>
      {hint && <span className="small muted">{hint}</span>}
    </div>
  );
}

export function Badge({ children, tone = "" }: { children: ReactNode; tone?: "up" | "down" | "warn" | "accent" | "" }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function Seg<T extends string | number>({ value, options, onChange }: { value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void }) {
  return (
    <div className="seg" role="tablist">
      {options.map((o) => (
        <button key={String(o.value)} role="tab" aria-selected={o.value === value} className={o.value === value ? "on" : ""} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Loading({ h = 120 }: { h?: number }) {
  return <div className="skeleton" style={{ height: h }} aria-label="Loading" />;
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof ApiError || error instanceof Error ? error.message : String(error);
  return <div className="error" role="alert">{msg}</div>;
}

export function Spinner() {
  return <span className="spinner" aria-label="Working" />;
}

export function OrbBadge({ state, side }: { state?: string; side?: string }) {
  if (state === "triggered") return <Badge tone={side === "short" ? "down" : "up"}>{side === "short" ? "▼" : "▲"} ORB {side}</Badge>;
  if (state === "expired") return <Badge>ORB expired</Badge>;
  return <Badge tone="warn">ORB waiting</Badge>;
}

export function TrendBadge({ trend }: { trend?: string }) {
  if (trend === "up") return <Badge tone="up">Trend up</Badge>;
  if (trend === "down") return <Badge tone="down">Trend down</Badge>;
  return <Badge>Trend mixed</Badge>;
}

/* --- icons (24px stroke) --- */
const P = (d: ReactNode) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
);
export const Icons = {
  markets: P(<><path d="M4 19V5" /><path d="M4 19h16" /><path d="M7 15l4-4 3 3 5-6" /></>),
  options: P(<><rect x="4" y="4" width="16" height="16" rx="3" /><path d="M4 10h16M10 4v16" /></>),
  strategy: P(<><path d="M3 17c3 0 4-10 9-10s6 10 9 10" /><path d="M3 12h18" strokeDasharray="2 3" /></>),
  trade: P(<><path d="M5 12h14" /><path d="M13 6l6 6-6 6" /></>),
  alerts: P(<><path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15z" /><path d="M10 20a2 2 0 0 0 4 0" /></>),
  journal: P(<><path d="M6 4h11a1 1 0 0 1 1 1v15H7a1 1 0 0 1-1-1z" /><path d="M9 8h6M9 12h6" /></>),
  research: P(<><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.5-4.5" /></>),
  settings: P(<><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z" /></>),
  more: P(<><circle cx="5" cy="12" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="19" cy="12" r="1.5" /></>),
  check: P(<path d="M5 12l5 5 9-10" />),
  cross: P(<><path d="M6 6l12 12M18 6L6 18" /></>),
  logo: (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="white" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 16l5-5 3 3 7-7" />
    </svg>
  ),
};
