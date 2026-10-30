import { describe, expect, it } from "vitest";
import { compact, num, pct, rupees, signedRupees, time } from "./format";
import { ticks } from "../charts/svg";

describe("Indian formatting", () => {
  it("groups by lakh and crore", () => {
    expect(num(12345678.9)).toBe("1,23,45,678.90");
    expect(rupees(5404.1)).toBe("₹5,404");
    expect(rupees(-2702.05, 2)).toBe("−₹2,702.05");
  });
  it("signs P/L and percentages", () => {
    expect(signedRupees(4053)).toBe("+₹4,053");
    expect(signedRupees(-1)).toBe("−₹1");
    expect(pct(0.314)).toBe("+0.31%");
    expect(pct(null)).toBe("—");
  });
  it("abbreviates lakh / crore", () => {
    expect(compact(4003220)).toBe("40.03 L");
    expect(compact(123456789)).toBe("12.35 Cr");
  });
  it("shows IST regardless of the viewer's zone", () => {
    expect(time("2026-10-29T04:15:00Z")).toBe("09:45");
  });
  it("makes round ticks", () => {
    expect(ticks(0, 100)).toEqual([0, 20, 40, 60, 80, 100]);
  });
});
