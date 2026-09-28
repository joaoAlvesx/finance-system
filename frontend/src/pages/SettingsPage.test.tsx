import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("react-pluggy-connect", () => ({
  PluggyConnect: ({
    onEvent,
  }: {
    onEvent?: (payload: { event: string; item: { id: string } }) => void;
  }) => (
    <button
      data-testid="pluggy-widget"
      type="button"
      onClick={() =>
        onEvent?.({ event: "LOGIN_SUCCESS", item: { id: "sandbox-item-id" } })
      }
    >
      Simular login Pluggy
    </button>
  ),
}));

import SettingsPage from "./SettingsPage";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SettingsPage", () => {
  it("mantém a conexão desativada enquanto o servidor não tem credenciais", async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: string) => {
      if (input === "/api/v1/integrations/pluggy/status") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            enabled: false,
            configured: false,
            connector_id: 200,
            include_sandbox: true,
            polling_seconds: 900,
            provider_refresh_note: "A origem gratuita pode atualizar uma vez ao dia.",
            items: [],
            latest_run: null,
          }),
        };
      }
      if (input === "/api/v1/accounts") {
        return { ok: true, status: 200, json: async () => [] };
      }
      throw new Error(`Requisição inesperada: ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Aguardando configuração")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Conectar Meu Pluggy" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Testar sandbox" })).toBeDisabled();
    expect(screen.queryByTestId("pluggy-widget")).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("connect_token");
  });

  it("registra o item assim que o widget informa o login", async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: string, options?: RequestInit) => {
      if (input === "/api/v1/integrations/pluggy/status") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            enabled: true,
            configured: true,
            connector_id: 200,
            include_sandbox: true,
            polling_seconds: 900,
            provider_refresh_note: "Dados disponibilizados pelo provedor.",
            items: [],
            latest_run: null,
          }),
        };
      }
      if (input === "/api/v1/accounts") {
        return { ok: true, status: 200, json: async () => [] };
      }
      if (input === "/api/v1/integrations/pluggy/connect-token") {
        return {
          ok: true,
          status: 200,
          json: async () => ({ connect_token: "temporary-token" }),
        };
      }
      if (input === "/api/v1/integrations/pluggy/items" && options?.method === "POST") {
        return { ok: true, status: 201, json: async () => ({}) };
      }
      throw new Error(`Requisição inesperada: ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Testar sandbox" }));
    fireEvent.click(await screen.findByTestId("pluggy-widget"));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/integrations/pluggy/items",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ item_id: "sandbox-item-id" }),
        }),
      ),
    );
  });
});
