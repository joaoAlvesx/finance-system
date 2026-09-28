import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../api";
import { EmptyState, ErrorState, LoadingState } from "../components/PageState";
import { formatDate, formatMoney } from "../format";
import type { Account, Category, Transaction } from "../types";

type ReviewFilter = "all" | "pending" | "reviewed" | "uncategorized";

export default function TransactionsPage() {
  const [searchParams] = useSearchParams();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [accountId, setAccountId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [review, setReview] = useState<ReviewFilter>(
    searchParams.get("revisar") ? "pending" : "all",
  );
  const [applyToSimilar, setApplyToSimilar] = useState(true);
  const [showCategoryForm, setShowCategoryForm] = useState(false);
  const [newCategory, setNewCategory] = useState({
    name: "",
    kind: "expense" as Category["kind"],
    color: "#46dea8",
  });
  const [notice, setNotice] = useState<string | null>(null);

  const categoryMap = useMemo(
    () => new Map(categories.map((category) => [category.id, category.name])),
    [categories],
  );
  const accountMap = useMemo(
    () => new Map(accounts.map((account) => [account.id, account.name])),
    [accounts],
  );

  const buildParams = useCallback(
    (nextCursor?: string | null) => {
      const params = new URLSearchParams({ limit: "50" });
      if (nextCursor) params.set("cursor", nextCursor);
      if (search.trim()) params.set("search", search.trim());
      if (accountId) params.set("account_id", accountId);
      if (categoryId) params.set("category_id", categoryId);
      if (review === "pending") params.set("is_reviewed", "false");
      if (review === "reviewed") params.set("is_reviewed", "true");
      if (review === "uncategorized") params.set("uncategorized", "true");
      return params;
    },
    [accountId, categoryId, review, search],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [page, categoryList, accountList] = await Promise.all([
        api.transactions(buildParams()),
        api.categories(),
        api.accounts(),
      ]);
      setTransactions(page.items);
      setCursor(page.next_cursor);
      setCategories(categoryList);
      setAccounts(accountList);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Erro inesperado.");
    } finally {
      setLoading(false);
    }
  }, [buildParams]);

  useEffect(() => {
    const handle = window.setTimeout(() => void load(), 250);
    return () => window.clearTimeout(handle);
  }, [load]);

  async function loadMore() {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const page = await api.transactions(buildParams(cursor));
      setTransactions((current) => [...current, ...page.items]);
      setCursor(page.next_cursor);
    } finally {
      setLoadingMore(false);
    }
  }

  async function updateCategory(transaction: Transaction, nextCategoryId: string) {
    setError(null);
    setNotice(null);
    if (applyToSimilar && nextCategoryId) {
      try {
        const result = await api.applyCategoryToSimilar(transaction.id, nextCategoryId);
        setNotice(
          `${result.updated_count} transações do mesmo recebedor foram atualizadas. A regra valerá para futuras importações.`,
        );
        await load();
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Falha ao aplicar a categoria.");
      }
      return;
    }
    const updated = await api.updateTransaction(transaction.id, {
      category_id: nextCategoryId || null,
      is_reviewed: Boolean(nextCategoryId),
    });
    setTransactions((items) =>
      items.map((item) => (item.id === transaction.id ? updated : item)),
    );
  }

  async function createCategory(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    try {
      const created = await api.createCategory({
        name: newCategory.name,
        kind: newCategory.kind,
        color: newCategory.color,
        icon: null,
        parent_id: null,
      });
      setCategories((items) =>
        [...items, created].sort((left, right) => left.name.localeCompare(right.name, "pt-BR")),
      );
      setNewCategory({ name: "", kind: "expense", color: "#46dea8" });
      setShowCategoryForm(false);
      setNotice(`Categoria “${created.name}” criada.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao criar a categoria.");
    }
  }

  async function markReviewed(transaction: Transaction) {
    const updated = await api.updateTransaction(transaction.id, { is_reviewed: true });
    setTransactions((items) =>
      items.map((item) => (item.id === transaction.id ? updated : item)),
    );
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Histórico financeiro</p>
          <h1>Transações</h1>
          <p>Consulte e organize as movimentações importadas da sua conta.</p>
        </div>
        <button
          className="button secondary category-create-button"
          type="button"
          onClick={() => setShowCategoryForm((visible) => !visible)}
        >
          + Nova categoria
        </button>
      </header>

      {notice && (
        <div className="inline-success" role="status">
          {notice}
        </div>
      )}

      {showCategoryForm && (
        <section className="panel category-creator">
          <div>
            <p className="eyebrow">Organização</p>
            <h2>Criar categoria</h2>
            <p>A nova categoria ficará disponível imediatamente nas transações.</p>
          </div>
          <form onSubmit={(event) => void createCategory(event)}>
            <label>
              <span>Nome</span>
              <input
                required
                maxLength={100}
                value={newCategory.name}
                onChange={(event) =>
                  setNewCategory({ ...newCategory, name: event.target.value })
                }
                placeholder="Ex.: Restaurante universitário"
              />
            </label>
            <label>
              <span>Tipo</span>
              <select
                value={newCategory.kind}
                onChange={(event) =>
                  setNewCategory({
                    ...newCategory,
                    kind: event.target.value as Category["kind"],
                  })
                }
              >
                <option value="expense">Despesa</option>
                <option value="income">Receita</option>
                <option value="both">Ambas</option>
              </select>
            </label>
            <label>
              <span>Cor</span>
              <input
                type="color"
                value={newCategory.color}
                onChange={(event) =>
                  setNewCategory({ ...newCategory, color: event.target.value })
                }
              />
            </label>
            <button className="button primary" type="submit">
              Criar categoria
            </button>
          </form>
        </section>
      )}

      <section className="filter-bar" aria-label="Filtros de transações">
        <label className="search-field">
          <span className="sr-only">Buscar descrição</span>
          <span aria-hidden="true">⌕</span>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar uma transação"
          />
        </label>
        <label>
          <span className="sr-only">Conta</span>
          <select value={accountId} onChange={(event) => setAccountId(event.target.value)}>
            <option value="">Todas as contas</option>
            {accounts.map((account) => (
              <option value={account.id} key={account.id}>
                {account.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Categoria</span>
          <select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
            <option value="">Todas as categorias</option>
            {categories.map((category) => (
              <option value={category.id} key={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Estado da revisão</span>
          <select
            value={review}
            onChange={(event) => setReview(event.target.value as ReviewFilter)}
          >
            <option value="all">Todas</option>
            <option value="pending">A revisar</option>
            <option value="uncategorized">Sem categoria</option>
            <option value="reviewed">Revisadas</option>
          </select>
        </label>
        <label className="bulk-category-toggle">
          <input
            type="checkbox"
            checked={applyToSimilar}
            onChange={(event) => setApplyToSimilar(event.target.checked)}
          />
          <span>
            <strong>Agrupar por recebedor</strong>
            Aplicar categoria a descrições iguais e aprender a regra
          </span>
        </label>
      </section>

      {error ? (
        <ErrorState message={error} retry={() => void load()} />
      ) : loading ? (
        <LoadingState label="Carregando transações…" />
      ) : transactions.length === 0 ? (
        <EmptyState title="Nenhuma transação encontrada">
          Ajuste os filtros ou importe um extrato CSV.
        </EmptyState>
      ) : (
        <section className="panel transaction-table-panel">
          <div className="table-scroll">
            <table className="transaction-table">
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Descrição</th>
                  <th>Conta</th>
                  <th>Categoria</th>
                  <th>Situação</th>
                  <th className="align-right">Valor</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((transaction) => (
                  <tr key={transaction.id}>
                    <td data-label="Data">{formatDate(transaction.transaction_date)}</td>
                    <td data-label="Descrição" className="description-cell">
                      <strong>{transaction.description_raw}</strong>
                      <span>{transaction.source.toUpperCase()}</span>
                    </td>
                    <td data-label="Conta">{accountMap.get(transaction.account_id) ?? "Conta"}</td>
                    <td data-label="Categoria">
                      <select
                        className="category-select"
                        value={transaction.category_id ?? ""}
                        aria-label={`Categoria de ${transaction.description_raw}`}
                        onChange={(event) =>
                          void updateCategory(transaction, event.target.value)
                        }
                      >
                        <option value="">Sem categoria</option>
                        {categories.map((category) => (
                          <option value={category.id} key={category.id}>
                            {category.name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td data-label="Situação">
                      {transaction.is_reviewed ? (
                        <span className="badge success">Revisada</span>
                      ) : (
                        <button
                          type="button"
                          className="badge warning badge-button"
                          onClick={() => void markReviewed(transaction)}
                          title="Marcar como revisada"
                        >
                          A revisar
                        </button>
                      )}
                    </td>
                    <td
                      data-label="Valor"
                      className={`align-right money-cell ${transaction.direction}`}
                    >
                      {transaction.direction === "credit" ? "+ " : "− "}
                      {formatMoney(transaction.amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <footer className="table-footer">
            <span>
              {transactions.length} transações exibidas ·{" "}
              {transactions.filter((item) => !item.is_reviewed).length} a revisar nesta página
            </span>
            {cursor && (
              <button
                type="button"
                className="button secondary"
                disabled={loadingMore}
                onClick={() => void loadMore()}
              >
                {loadingMore ? "Carregando…" : "Carregar mais"}
              </button>
            )}
          </footer>
        </section>
      )}

      <div className="mobile-summary" aria-hidden="true">
        {categoryMap.size} categorias disponíveis
      </div>
    </div>
  );
}
