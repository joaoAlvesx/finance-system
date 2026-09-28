import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import AssistantPage from "./AssistantPage";

afterEach(() => vi.unstubAllGlobals());

describe("AssistantPage", () => {
  it("distingue cálculo, previsão e sugestão e consulta o backend", async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: string) => {
      if (input === "/api/v1/assistant/insights") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            generated_at: "2026-09-16T12:00:00Z",
            cards: [
              { key: "a", title: "Saldo", text: "R$ 10,00", value_kind: "calculated", severity: "neutral" },
              { key: "b", title: "Projeção", text: "R$ 5,00", value_kind: "prediction", severity: "neutral" },
            ],
            suggested_questions: ["Qual é meu saldo?"],
          }),
        };
      }
      if (input === "/api/v1/assistant/suggestions") {
        return { ok: true, status: 200, json: async () => [] };
      }
      if (input === "/api/v1/assistant/query") {
        return {
          ok: true,
          status: 200,
          json: async () => ({ intent: "balance", value_kind: "calculated", answer: "Saldo R$ 10,00", data: {} }),
        };
      }
      throw new Error(`Requisição inesperada: ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<MemoryRouter><AssistantPage /></MemoryRouter>);

    expect(await screen.findByText("Saldo")).toBeInTheDocument();
    expect(screen.getByText("Previsão")).toBeInTheDocument();
    expect(screen.getAllByText("Sugestão").length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Pergunta"), { target: { value: "Qual é meu saldo?" } });
    fireEvent.click(screen.getByRole("button", { name: "Perguntar" }));
    expect(await screen.findByText("Saldo R$ 10,00")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/assistant/query",
      expect.objectContaining({ method: "POST" }),
    ));
  });
});
