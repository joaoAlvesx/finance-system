import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("API de categorias", () => {
  it("cria categoria com JSON validado pelo backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({
        id: "category-id",
        name: "Restaurante universitário",
        parent_id: null,
        color: "#46dea8",
        icon: null,
        kind: "expense",
        is_active: true,
        created_at: "2026-09-15T12:00:00Z",
        updated_at: "2026-09-15T12:00:00Z",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.createCategory({
      name: "Restaurante universitário",
      kind: "expense",
      color: "#46dea8",
      icon: null,
      parent_id: null,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/categories",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("aplica a categoria ao grupo e solicita a criação da regra", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        category_id: "category-id",
        updated_count: 4,
        rule_created: true,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.applyCategoryToSimilar("transaction-id", "category-id");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/transactions/transaction-id/category/apply-to-similar",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ category_id: "category-id", create_rule: true }),
      }),
    );
  });
});
