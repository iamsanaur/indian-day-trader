// Indian number formatting (1,23,456.78), rupees, percentages and IST times.

const grouped = (dp: number) =>
  new Intl.NumberFormat("en-IN", { minimumFractionDigits: dp, maximumFractionDigits: dp });

export function num(v: number | null | undefined, dp = 2): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return grouped(dp).format(v);
}

export function rupees(v: number | null | undefined, dp = 0): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v < 0 ? "−" : ""}₹${grouped(dp).format(Math.abs(v))}`;
}

export function signedRupees(v: number | null | undefined, dp = 0): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}₹${grouped(dp).format(Math.abs(v))}`;
}

export function pct(v: number | null | undefined, dp = 2, signed = true): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${signed && v > 0 ? "+" : ""}${v.toFixed(dp)}%`;
}

/** Lakh / crore shorthand: 1.25 L, 3.4 Cr. */
export function compact(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "−" : "";
  if (a >= 1e7) return `${sign}${(a / 1e7).toFixed(2)} Cr`;
  if (a >= 1e5) return `${sign}${(a / 1e5).toFixed(2)} L`;
  if (a >= 1e3) return `${sign}${(a / 1e3).toFixed(1)} K`;
  return `${sign}${a.toFixed(0)}`;
}

const istTime = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false });
const istDate = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short" });

export function time(iso: string | null | undefined): string {
  if (!iso) return "—";
  return istTime.format(new Date(iso));
}

export function dateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  return istDate.format(new Date(iso));
}

export function tone(v: number | null | undefined): "up" | "down" | "" {
  if (v == null || v === 0) return "";
  return v > 0 ? "up" : "down";
}
