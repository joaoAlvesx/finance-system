import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import TransactionsPage from "./TransactionsPage";

afterEach(() => vi.unstubAllGlobals());

describe("TransactionsPage", () => {
  it("cria categoria e mantém o agrupamento por recebedor explícito", async () => {
    const createdCategory = {
      id: "category-id",
      name: "Restaurante universitário",
      parent_id: null,
      color: "#46dea8",
      icon: null,
      kind: "expense",
      is_active: true,
      created_at: "2026-09-15T12:00:00Z",
      updated_at: "2026-09-15T12:00:00Z",
    };
    const fetchMock = vi.fn().mockImplementation(async (input: string, options?: RequestInit) => {
      if (input.startsWith("/api/v1/transactions?")) {
        return { ok: true, status: 200, json: async () => ({ items: [], next_cursor: null }) };
      }
      if (input === "/api/v1/accounts") {
        return { ok: true, status: 200, json: async () => [] };
      }
      if (input === "/api/v1/categories" && options?.method === "POST") {
        return { ok: true, status: 201, json: async () => createdCategory };
      }
      if (input === "/api/v1/categories") {
        return { ok: true, status: 200, json: async () => [] };
      }
      throw new Error(`Requisição inesperada: ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <TransactionsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Nenhuma transação encontrada")).toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: /Agrupar por recebedor/ }),
    ).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: /Nova categoria/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Nome" }), {
      target: { value: "Restaurante universitário" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Criar categoria" }));

    expect(
      await screen.findByText("Categoria “Restaurante universitário” criada."),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/categories",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });
});
