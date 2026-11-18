import { describe, expect, it } from "vitest";

import { bytes, normalizeWeights, timeAgo, titleCase } from "./format";

describe("format helpers", () => {
  it("formats relative times", () => {
    const now = new Date("2026-11-13T12:00:00Z");
    expect(timeAgo("2026-11-13T11:00:00Z", now)).toBe("1 hour ago");
    expect(timeAgo("2026-11-10T12:00:00Z", now)).toBe("3 days ago");
    expect(timeAgo("2026-11-13T11:59:50Z", now)).toBe("just now");
    expect(timeAgo(null, now)).toBe("—");
  });

  it("formats bytes and titles", () => {
    expect(bytes(512)).toBe("512 B");
    expect(bytes(37_334)).toBe("36 KB");
    expect(bytes(5 * 1024 * 1024)).toBe("5.0 MB");
    expect(titleCase("full_time")).toBe("Full Time");
  });

  it("normalizes weights like the backend", () => {
    const w = normalizeWeights({ title: 2, skills: 2, freshness: 0 });
    expect(w.title).toBeCloseTo(0.5);
    expect(w.freshness).toBe(0);
    expect(normalizeWeights({ a: 0 }).a).toBe(0);
  });
});
