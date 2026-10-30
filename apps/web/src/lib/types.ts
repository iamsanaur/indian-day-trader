// Response shapes from the idt API (subset the UI reads).

export interface Orb {
  state: "waiting" | "triggered" | "expired";
  side?: "long" | "short";
  trigger_time?: string;
  entry?: number;
  detail?: string;
}

export interface BoardEntry {
  last: number;
  change_pct: number | null;
  orb: Orb;
  ema: { ema9: number; ema21: number; trend: "up" | "down" | "mixed" };
  cpr_read: string | null;
  day: { open: number; high: number; low: number };
  error?: string;
}

export interface Board {
  as_of: string;
  indices: Record<string, BoardEntry>;
}

export interface Candle { t: number; o: number; h: number; l: number; c: number; v: number }

export interface IndexView {
  symbol: string;
  as_of: string;
  last: number;
  change_pct: number | null;
  day: { open: number; high: number; low: number };
  opening_range: { high: number; low: number; mid: number; width: number } | null;
  orb: Orb;
  prev_day: { date: string; high: number; low: number; close: number } | null;
  cpr: Record<string, number>;
  cpr_read: string | null;
  ema: { ema9: number; ema21: number; trend: string };
  vwap: number | null;
  vwap_note?: string;
  candles: Candle[];
  series: { ema9: (number | null)[]; ema21: (number | null)[]; vwap: (number | null)[] };
}

export interface OptionSide {
  ltp: number;
  iv: number;
  oi: number;
  oi_change: number;
  volume: number;
  delta: number;
  buildup: string;
}

export interface ChainRow { strike: number; ce?: OptionSide; pe?: OptionSide }

export interface Chain {
  underlying: string;
  expiry: string;
  spot: number;
  days_to_expiry: number;
  atm: number;
  atm_iv: number | null;
  atm_straddle: number;
  expected_move: { points: number; range: [number, number] };
  pcr: { oi: number | null; volume: number | null; oi_change: number | null; ce_oi: number; pe_oi: number };
  max_pain: number;
  max_pain_distance_pct: number;
  walls: {
    resistance: { strike: number; oi: number; oi_change: number }[];
    support: { strike: number; oi: number; oi_change: number }[];
  };
  skew: { put_3pct_iv: number | null; call_3pct_iv: number | null };
  bias: string;
  lot_size: number;
  table: ChainRow[];
}

export interface Leg {
  kind: "CE" | "PE" | "FUT";
  strike: number;
  side: 1 | -1;
  lots: number;
  premium: number;
  expiry: string;
  iv: number;
  symbol: string;
}

export interface StrategyResult {
  name: string;
  underlying: string;
  expiry: string;
  spot: number;
  lot_size: number;
  view: string;
  legs: Leg[];
  analysis: {
    net_premium: number;
    premium_type: "debit" | "credit";
    max_profit: number | null;
    max_loss: number | null;
    unlimited_profit: boolean;
    unlimited_loss: boolean;
    breakevens: number[];
    naked: string[];
  };
  greeks: { delta: number; gamma: number; theta: number; vega: number };
  margin: { total?: number; source?: string; error?: string };
  warning?: string;
  curve: { x: number[]; expiry: number[]; today: number[] };
}

export interface Plan {
  symbol: string;
  kind: "equity" | "future" | "option" | "strategy";
  side: string;
  setup: string;
  basis: "underlying" | "premium" | "pnl";
  contract: string | null;
  unit: string;
  lot_size: number;
  entry: number;
  stop?: number;
  target?: number;
  stop_pnl?: number;
  target_pnl?: number;
  underlying_entry: number;
  underlying_stop?: number;
  underlying_target?: number;
  risk_per_unit: number;
  reward_per_unit: number;
  rr: number;
  stop_rule: string;
  target_rule: string;
  squareoff: string;
  trigger_time?: string | null;
  strategy?: string;
}

export interface Orders {
  units: number;
  unit: string;
  lot_size: number;
  legs: { symbol: string; side: "BUY" | "SELL"; quantity: number; lots: number | null; price: number; product: string }[];
  loss_at_stop: number;
  profit_at_target: number;
  charges: { if_stopped: number; if_target: number };
  margin: { total: number; source?: string };
  notes: string[];
  hash: string;
}

export interface RiskVerdict {
  verdict: "PASS" | "BLOCK";
  reasons: string[];
  checks: { rule: string; ok: boolean; detail: string }[];
  order_hash: string;
  ts: string;
}

export interface Ticket {
  mode: string;
  order_hash: string;
  symbol: string;
  entries: { action: string; symbol: string; product: string; order_type: string; price: number; quantity: number; lots: number | null }[];
  exits: Record<string, string | number | null>[];
  oco: string;
  square_off: string;
  loss_at_stop: number;
  profit_at_target: number;
  margin: { total: number };
  charges: { if_stopped: number; if_target: number };
}

export interface TimeMachine {
  monte_carlo: {
    paths: number;
    p_target: number;
    p_stop: number;
    p_flat: number;
    pnl_per_unit: { mean: number; median: number; p5: number; p95: number };
    expected_r: number | null;
    sessions_sampled: number;
    from: string;
    to: string;
  };
  replay: { fired?: number; win_rate?: number | null; avg_r?: number | null; sessions?: number; skipped?: string };
  sized?: { units: number; expected_pnl: number };
  caveat: string;
}

export interface Alert {
  id: string;
  kind: "price" | "pnl" | "time";
  symbol: string | null;
  op: string;
  value: number | string;
  label: string;
  fired: boolean;
  fired_at?: string;
  observed?: number | string;
}

export interface DhanStatus {
  connected: boolean;
  source: "env" | "totp" | null;
  client_id_set: boolean;
  pin_set: boolean;
  totp_login_available: boolean;
  client_name?: string | null;
  expires_at: string | null;
  expires_in_seconds: number | null;
  message: string;
}

export interface Status {
  now: string;
  phase: string;
  mode: string;
  data_provider: string;
  trades_today: number;
  realised_today: number;
  limits: Record<string, number | boolean>;
  demo?: boolean;
  dhan?: DhanStatus | null;
}

export interface JournalEntry {
  type: "confirm" | "close";
  ts: string;
  symbol?: string;
  pnl?: number;
  hash?: string;
  kind?: string;
  loss_at_stop?: number;
  note?: string;
  mode?: string;
}
