import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "./DashboardPage";

afterEach(() => vi.unstubAllGlobals());

describe("DashboardPage", () => {
  it("explica como habilitar o limite quando não há próxima entrada", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          generated_at: "2026-09-15T12:00:00Z",
          current_balance: "1250.00",
          available_until_next_income: null,
          daily_safe_limit: null,
          committed_expenses: "0.00",
          deficit: "0.00",
          minimum_reserve: "0.00",
          month_income: "0.00",
          month_expense: "0.00",
          review_count: 2,
          uncategorized_count: 1,
          next_income: null,
          spending_by_category: [],
          recent_transactions: [],
        }),
      }),
    );

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Cadastre a próxima entrada")).toBeInTheDocument();
    expect(screen.getByText(/1.250,00/)).toBeInTheDocument();
  });
});
