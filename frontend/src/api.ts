import type {
  Account,
  AssistantAnswer,
  AssistantInsights,
  BudgetSettings,
  Category,
  CategorySuggestion,
  Dashboard,
  ExpectedIncome,
  ImportPreview,
  PlannedExpense,
  PluggyAccount,
  PluggyItem,
  PluggyStatus,
  PluggySyncRun,
  Transaction,
  TransactionPage,
} from "./types";

const API_ROOT = "/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, options);
  if (!response.ok) {
    let message = "Não foi possível concluir a operação.";
    try {
      const payload = (await response.json()) as { detail?: { message?: string } };
      message = payload.detail?.message ?? message;
    } catch {
      // Respostas sem JSON usam a mensagem segura acima.
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const jsonHeaders = { "Content-Type": "application/json" };

export const api = {
  dashboard: () => request<Dashboard>("/dashboard"),
  accounts: () => request<Account[]>("/accounts"),
  categories: () => request<Category[]>("/categories"),
  createCategory: (body: object) =>
    request<Category>("/categories", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),
  transactions: (params: URLSearchParams) =>
    request<TransactionPage>(`/transactions?${params.toString()}`),
  updateTransaction: (id: string, body: object) =>
    request<Transaction>(`/transactions/${id}`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),
  applyCategoryToSimilar: (id: string, categoryId: string) =>
    request<{ category_id: string; updated_count: number; rule_created: boolean }>(
      `/transactions/${id}/category/apply-to-similar`,
      {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify({ category_id: categoryId, create_rule: true }),
      },
    ),
  incomes: () => request<ExpectedIncome[]>("/planning/incomes"),
  createIncome: (body: object) =>
    request<ExpectedIncome>("/planning/incomes", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),
  updateIncome: (id: string, body: object) =>
    request<ExpectedIncome>(`/planning/incomes/${id}`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),
  deleteIncome: (id: string) =>
    request<void>(`/planning/incomes/${id}`, { method: "DELETE" }),
  expenses: () => request<PlannedExpense[]>("/planning/expenses"),
  createExpense: (body: object) =>
    request<PlannedExpense>("/planning/expenses", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),
  updateExpense: (id: string, body: object) =>
    request<PlannedExpense>(`/planning/expenses/${id}`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),
  deleteExpense: (id: string) =>
    request<void>(`/planning/expenses/${id}`, { method: "DELETE" }),
  settings: () => request<BudgetSettings>("/planning/settings"),
  updateSettings: (body: object) =>
    request<BudgetSettings>("/planning/settings", {
      method: "PUT",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),
  previewImport: (accountId: string, file: File) => {
    const body = new FormData();
    body.append("account_id", accountId);
    body.append("file", file);
    return request<ImportPreview>("/imports/csv/preview", { method: "POST", body });
  },
  importDetails: (id: string, offset: number) =>
    request<ImportPreview>(`/imports/${id}?row_offset=${offset}&row_limit=200`),
  confirmImport: (id: string, duplicateRows: number[]) =>
    request<{ imported_rows: number; skipped_possible_duplicates: number }>(
      `/imports/${id}/confirm`,
      {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify({ duplicate_row_numbers_to_import: duplicateRows }),
      },
    ),
  pluggyStatus: () => request<PluggyStatus>("/integrations/pluggy/status"),
  pluggyConnectToken: (itemId?: string) =>
    request<{ connect_token: string }>("/integrations/pluggy/connect-token", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ item_id: itemId ?? null }),
    }),
  registerPluggyItem: (itemId: string) =>
    request<PluggyItem>("/integrations/pluggy/items", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ item_id: itemId }),
    }),
  linkPluggyAccount: (linkId: string, accountId: string) =>
    request<PluggyAccount>(`/integrations/pluggy/accounts/${linkId}/link`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ account_id: accountId }),
    }),
  syncPluggy: (itemId: string, fullReconciliation = false) =>
    request<{ runs: PluggySyncRun[] }>("/integrations/pluggy/sync", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        item_id: itemId,
        full_reconciliation: fullReconciliation,
      }),
    }),
  assistantInsights: () => request<AssistantInsights>("/assistant/insights"),
  assistantQuery: (question: string) =>
    request<AssistantAnswer>("/assistant/query", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ question }),
    }),
  categorySuggestions: () =>
    request<CategorySuggestion[]>("/assistant/suggestions"),
  decideCategorySuggestion: (id: string, decision: "accept" | "reject") =>
    request<CategorySuggestion>(`/assistant/suggestions/${id}/decision`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ decision }),
    }),
};
