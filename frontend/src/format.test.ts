import { describe, expect, it } from "vitest";

import { formatDate, formatMoney, normalizeMoneyInput } from "./format";

describe("formatação brasileira", () => {
  it("formata valores monetários e datas civis", () => {
    expect(formatMoney("1234.56")).toContain("1.234,56");
    expect(formatDate("2026-09-15")).toContain("15");
  });

  it("normaliza entrada decimal sem usar float", () => {
    expect(normalizeMoneyInput("R$ 1.600,25")).toBe("1600.25");
    expect(normalizeMoneyInput("700.00")).toBe("700.00");
  });
});
