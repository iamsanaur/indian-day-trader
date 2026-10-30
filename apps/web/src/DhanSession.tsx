import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./lib/api";
import type { DhanStatus } from "./lib/types";
import { Badge, ErrorBox, Spinner } from "./ui";

export function hoursLeft(s: DhanStatus): string {
  if (!s.expires_in_seconds) return "";
  const h = Math.floor(s.expires_in_seconds / 3600);
  const m = Math.floor((s.expires_in_seconds % 3600) / 60);
  return `${h}h ${m}m left`;
}

/** 6-digit TOTP entry that exchanges the code for today's Dhan token. */
export function TotpForm({ compact = false }: { compact?: boolean }) {
  const qc = useQueryClient();
  const [totp, setTotp] = useState("");
  const login = useMutation({
    mutationFn: () => api<DhanStatus>("/dhan/login", { json: { totp } }),
    onSuccess: () => { setTotp(""); qc.invalidateQueries(); },
  });
  return (
    <form className="stack" style={{ gap: 8 }} onSubmit={(e) => { e.preventDefault(); if (totp.length === 6) login.mutate(); }}>
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <input
          className="input num" inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="6-digit TOTP"
          value={totp} onChange={(e) => setTotp(e.target.value.replace(/\D/g, "").slice(0, 6))}
          style={{ width: compact ? 150 : 200, letterSpacing: "0.2em", fontWeight: 600 }} aria-label="Dhan TOTP"
        />
        <button className="btn btn-primary" disabled={totp.length !== 6 || login.isPending}>
          {login.isPending ? <Spinner /> : "Connect"}
        </button>
      </div>
      <ErrorBox error={login.error} />
    </form>
  );
}

export function DhanCardBody({ status }: { status: DhanStatus }) {
  const qc = useQueryClient();
  const logout = useMutation({ mutationFn: () => api("/dhan", { method: "DELETE" }), onSuccess: () => qc.invalidateQueries() });
  return (
    <div className="stack">
      <div className="row">
        {status.connected ? <Badge tone="up">Connected{status.client_name ? ` · ${status.client_name}` : ""}</Badge> : <Badge tone="down">Not connected</Badge>}
        {status.connected && status.source === "totp" && <Badge>{hoursLeft(status)}</Badge>}
        {status.source === "env" && <Badge>manual token</Badge>}
      </div>
      <p className="small text-2" style={{ margin: 0 }}>{status.message}</p>
      {status.totp_login_available && status.source !== "env" && <TotpForm />}
      {!status.client_id_set || !status.pin_set ? (
        <p className="small muted" style={{ margin: 0 }}>Add <code>DHAN_CLIENT_ID</code> and <code>DHAN_PIN</code> to the server's <code>.env</code> and restart it.</p>
      ) : (
        <p className="small muted" style={{ margin: 0 }}>Your TOTP is used once to get a 24-hour token and is never stored. Enable TOTP at web.dhan.co › DhanHQ Trading APIs.</p>
      )}
      {status.connected && status.source === "totp" && (
        <div><button className="btn btn-sm btn-ghost" onClick={() => logout.mutate()}>Disconnect</button></div>
      )}
    </div>
  );
}

/** Shown on every page while the Dhan session is missing or expired. */
export function DhanBanner({ status }: { status: DhanStatus }) {
  if (status.connected) return null;
  return (
    <div className="banner warn" style={{ marginBottom: 18, alignItems: "center", flexWrap: "wrap" }}>
      <div style={{ flex: 1, minWidth: 220 }}>
        <div className="banner-title" style={{ fontSize: 15 }}>Connect Dhan for today</div>
        <div className="small text-2">{status.message}</div>
      </div>
      {status.totp_login_available && <TotpForm compact />}
    </div>
  );
}
