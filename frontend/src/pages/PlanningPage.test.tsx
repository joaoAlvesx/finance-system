import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PlanningPage from "./PlanningPage";

afterEach(() => vi.unstubAllGlobals());

describe("PlanningPage", () => {
  it("habilita alertas do Telegram sem manipular o token no frontend", async () => {
    const settings = {
      id: "settings-id",
      minimum_reserve: "100.00",
      currency_code: "BRL",
      safe_spending_mode: "until_next_income",
      include_pending_transactions: true,
      telegram_notifications_enabled: false,
      timezone: "America/Campo_Grande",
      created_at: "2026-09-15T12:00:00Z",
      updated_at: "2026-09-15T12:00:00Z",
    };
    const fetchMock = vi.fn().mockImplementation(async (input: string, options?: RequestInit) => {
      if (input === "/api/v1/planning/settings" && options?.method === "PUT") {
        return {
          ok: true,
          status: 200,
          json: async () => ({ ...settings, telegram_notifications_enabled: true }),
        };
      }
      if (input === "/api/v1/planning/settings") {
        return { ok: true, status: 200, json: async () => settings };
      }
      if (
        input === "/api/v1/planning/incomes" ||
        input === "/api/v1/planning/expenses" ||
        input === "/api/v1/categories"
      ) {
        return { ok: true, status: 200, json: async () => [] };
      }
      throw new Error(`Requisição inesperada: ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<PlanningPage />);

    const toggle = await screen.findByRole("checkbox", {
      name: /Habilitar alertas após configurar o bot/,
    });
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);

    await waitFor(() => expect(toggle).toBeChecked());
    const putCall = fetchMock.mock.calls.find(
      ([input, options]) =>
        input === "/api/v1/planning/settings" && options?.method === "PUT",
    );
    expect(JSON.parse(putCall?.[1]?.body as string)).toEqual(
      expect.objectContaining({ telegram_notifications_enabled: true }),
    );
  });
});
