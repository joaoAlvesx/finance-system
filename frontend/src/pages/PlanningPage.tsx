import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../api";
import { ErrorState, LoadingState } from "../components/PageState";
import { formatDate, formatMoney, normalizeMoneyInput } from "../format";
import type {
  BudgetSettings,
  Category,
  ExpectedIncome,
  PlannedExpense,
} from "../types";

const emptyIncome = {
  name: "",
  expected_amount: "",
  expected_date: "",
  recurrence: "none" as "none" | "monthly",
  amount_is_variable: false,
};

const emptyExpense = {
  name: "",
  expected_amount: "",
  due_date: "",
  recurrence: "none" as "none" | "monthly",
  amount_is_variable: false,
  category_id: "",
};

export default function PlanningPage() {
  const [incomes, setIncomes] = useState<ExpectedIncome[]>([]);
  const [expenses, setExpenses] = useState<PlannedExpense[]>([]);
  const [settings, setSettings] = useState<BudgetSettings | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [incomeForm, setIncomeForm] = useState(emptyIncome);
  const [expenseForm, setExpenseForm] = useState(emptyExpense);
  const [editingIncome, setEditingIncome] = useState<string | null>(null);
  const [editingExpense, setEditingExpense] = useState<string | null>(null);
  const [reserve, setReserve] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const categoryMap = useMemo(
    () => new Map(categories.map((category) => [category.id, category.name])),
    [categories],
  );

  const load = useCallback(async () => {
    setError(null);
    try {
      const [incomeList, expenseList, currentSettings, categoryList] = await Promise.all([
        api.incomes(),
        api.expenses(),
        api.settings(),
        api.categories(),
      ]);
      setIncomes(incomeList);
      setExpenses(expenseList);
      setSettings(currentSettings);
      setReserve(currentSettings.minimum_reserve);
      setCategories(categoryList);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Erro inesperado.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function showNotice(message: string) {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 2600);
  }

  async function submitIncome(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    const payload = {
      ...incomeForm,
      expected_amount: normalizeMoneyInput(incomeForm.expected_amount),
    };
    try {
      if (editingIncome) {
        await api.updateIncome(editingIncome, payload);
        showNotice("Entrada atualizada.");
      } else {
        await api.createIncome(payload);
        showNotice("Entrada planejada adicionada.");
      }
      setIncomeForm(emptyIncome);
      setEditingIncome(null);
      await load();
    } finally {
      setSaving(false);
    }
  }

  async function submitExpense(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    const payload = {
      ...expenseForm,
      expected_amount: normalizeMoneyInput(expenseForm.expected_amount),
      category_id: expenseForm.category_id || null,
    };
    try {
      if (editingExpense) {
        await api.updateExpense(editingExpense, payload);
        showNotice("Despesa atualizada.");
      } else {
        await api.createExpense(payload);
        showNotice("Despesa planejada adicionada.");
      }
      setExpenseForm(emptyExpense);
      setEditingExpense(null);
      await load();
    } finally {
      setSaving(false);
    }
  }

  async function saveReserve(event: FormEvent) {
    event.preventDefault();
    const updated = await api.updateSettings({
      minimum_reserve: normalizeMoneyInput(reserve),
      include_pending_transactions: settings?.include_pending_transactions ?? true,
      telegram_notifications_enabled: settings?.telegram_notifications_enabled ?? false,
    });
    setSettings(updated);
    setReserve(updated.minimum_reserve);
    showNotice("Reserva mínima atualizada.");
  }

  async function toggleTelegramNotifications(enabled: boolean) {
    if (!settings) return;
    const updated = await api.updateSettings({
      minimum_reserve: settings.minimum_reserve,
      include_pending_transactions: settings.include_pending_transactions,
      telegram_notifications_enabled: enabled,
    });
    setSettings(updated);
    showNotice(enabled ? "Alertas do Telegram habilitados." : "Alertas do Telegram pausados.");
  }

  function editIncome(income: ExpectedIncome) {
    setEditingIncome(income.id);
    setIncomeForm({
      name: income.name,
      expected_amount: income.expected_amount,
      expected_date: income.expected_date,
      recurrence: income.recurrence,
      amount_is_variable: income.amount_is_variable,
    });
  }

  function editExpense(expense: PlannedExpense) {
    setEditingExpense(expense.id);
    setExpenseForm({
      name: expense.name,
      expected_amount: expense.expected_amount,
      due_date: expense.due_date,
      recurrence: expense.recurrence,
      amount_is_variable: expense.amount_is_variable,
      category_id: expense.category_id ?? "",
    });
  }

  if (error) return <ErrorState message={error} retry={() => void load()} />;
  if (loading) return <LoadingState label="Carregando planejamento…" />;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Próximos dias</p>
          <h1>Planejamento</h1>
          <p>Informe entradas e compromissos para calcular seu limite com segurança.</p>
        </div>
      </header>

      {notice && <div className="toast" role="status">{notice}</div>}

      <section className="panel reserve-panel">
        <div>
          <p className="eyebrow">Proteção</p>
          <h2>Reserva mínima</h2>
          <p>Este valor sempre é descontado do disponível para gastar.</p>
        </div>
        <form className="inline-form" onSubmit={(event) => void saveReserve(event)}>
          <label>
            <span>Valor em reais</span>
            <input
              required
              inputMode="decimal"
              value={reserve}
              onChange={(event) => setReserve(event.target.value)}
              placeholder="0,00"
            />
          </label>
          <button className="button primary" type="submit">Salvar reserva</button>
        </form>
      </section>

      <section className="panel telegram-settings-panel">
        <div>
          <p className="eyebrow">Notificações</p>
          <h2>Alertas pelo Telegram</h2>
          <p>Receba novos gastos e consulte saldo e disponível pelo bot configurado.</p>
        </div>
        <label className="checkbox-field telegram-toggle">
          <input
            type="checkbox"
            checked={settings?.telegram_notifications_enabled ?? false}
            onChange={(event) => void toggleTelegramNotifications(event.target.checked)}
          />
          <span>Habilitar alertas após configurar o bot no servidor</span>
        </label>
      </section>

      <div className="planning-grid">
        <section className="panel planning-section">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Recebimentos</p>
              <h2>Entradas esperadas</h2>
            </div>
          </div>
          <form className="stacked-form" onSubmit={(event) => void submitIncome(event)}>
            <div className="form-row two-columns">
              <label>
                <span>Nome</span>
                <input
                  required
                  value={incomeForm.name}
                  onChange={(event) =>
                    setIncomeForm({ ...incomeForm, name: event.target.value })
                  }
                  placeholder="Ex.: Salário"
                />
              </label>
              <label>
                <span>Valor previsto</span>
                <input
                  required
                  inputMode="decimal"
                  value={incomeForm.expected_amount}
                  onChange={(event) =>
                    setIncomeForm({ ...incomeForm, expected_amount: event.target.value })
                  }
                  placeholder="1.600,00"
                />
              </label>
            </div>
            <div className="form-row two-columns">
              <label>
                <span>Data esperada</span>
                <input
                  required
                  type="date"
                  value={incomeForm.expected_date}
                  onChange={(event) =>
                    setIncomeForm({ ...incomeForm, expected_date: event.target.value })
                  }
                />
              </label>
              <label>
                <span>Repetição</span>
                <select
                  value={incomeForm.recurrence}
                  onChange={(event) =>
                    setIncomeForm({
                      ...incomeForm,
                      recurrence: event.target.value as "none" | "monthly",
                    })
                  }
                >
                  <option value="none">Somente esta vez</option>
                  <option value="monthly">Mensal</option>
                </select>
              </label>
            </div>
            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={incomeForm.amount_is_variable}
                onChange={(event) =>
                  setIncomeForm({ ...incomeForm, amount_is_variable: event.target.checked })
                }
              />
              O valor pode variar
            </label>
            <div className="form-actions">
              {editingIncome && (
                <button
                  className="button ghost"
                  type="button"
                  onClick={() => {
                    setEditingIncome(null);
                    setIncomeForm(emptyIncome);
                  }}
                >
                  Cancelar
                </button>
              )}
              <button className="button primary" disabled={saving} type="submit">
                {editingIncome ? "Salvar entrada" : "Adicionar entrada"}
              </button>
            </div>
          </form>
          <ul className="planning-list">
            {incomes.map((income) => (
              <li key={income.id}>
                <div>
                  <strong>{income.name}</strong>
                  <span>
                    {formatDate(income.expected_date)} · {income.recurrence === "monthly" ? "Mensal" : "Pontual"}
                  </span>
                </div>
                <strong className="credit">{formatMoney(income.expected_amount)}</strong>
                <div className="row-actions">
                  <button type="button" onClick={() => editIncome(income)}>Editar</button>
                  <button
                    type="button"
                    onClick={() => void api.deleteIncome(income.id).then(load)}
                  >
                    Remover
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel planning-section">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Compromissos</p>
              <h2>Despesas planejadas</h2>
            </div>
          </div>
          <form className="stacked-form" onSubmit={(event) => void submitExpense(event)}>
            <div className="form-row two-columns">
              <label>
                <span>Nome</span>
                <input
                  required
                  value={expenseForm.name}
                  onChange={(event) =>
                    setExpenseForm({ ...expenseForm, name: event.target.value })
                  }
                  placeholder="Ex.: Aluguel"
                />
              </label>
              <label>
                <span>Valor previsto</span>
                <input
                  required
                  inputMode="decimal"
                  value={expenseForm.expected_amount}
                  onChange={(event) =>
                    setExpenseForm({ ...expenseForm, expected_amount: event.target.value })
                  }
                  placeholder="800,00"
                />
              </label>
            </div>
            <div className="form-row two-columns">
              <label>
                <span>Vencimento</span>
                <input
                  required
                  type="date"
                  value={expenseForm.due_date}
                  onChange={(event) =>
                    setExpenseForm({ ...expenseForm, due_date: event.target.value })
                  }
                />
              </label>
              <label>
                <span>Categoria</span>
                <select
                  value={expenseForm.category_id}
                  onChange={(event) =>
                    setExpenseForm({ ...expenseForm, category_id: event.target.value })
                  }
                >
                  <option value="">Sem categoria</option>
                  {categories.map((category) => (
                    <option value={category.id} key={category.id}>{category.name}</option>
                  ))}
                </select>
              </label>
            </div>
            <div className="form-row two-columns compact-row">
              <label>
                <span>Repetição</span>
                <select
                  value={expenseForm.recurrence}
                  onChange={(event) =>
                    setExpenseForm({
                      ...expenseForm,
                      recurrence: event.target.value as "none" | "monthly",
                    })
                  }
                >
                  <option value="none">Somente esta vez</option>
                  <option value="monthly">Mensal</option>
                </select>
              </label>
              <label className="checkbox-field align-checkbox">
                <input
                  type="checkbox"
                  checked={expenseForm.amount_is_variable}
                  onChange={(event) =>
                    setExpenseForm({ ...expenseForm, amount_is_variable: event.target.checked })
                  }
                />
                O valor pode variar
              </label>
            </div>
            <div className="form-actions">
              {editingExpense && (
                <button
                  className="button ghost"
                  type="button"
                  onClick={() => {
                    setEditingExpense(null);
                    setExpenseForm(emptyExpense);
                  }}
                >
                  Cancelar
                </button>
              )}
              <button className="button primary" disabled={saving} type="submit">
                {editingExpense ? "Salvar despesa" : "Adicionar despesa"}
              </button>
            </div>
          </form>
          <ul className="planning-list">
            {expenses.map((expense) => (
              <li key={expense.id}>
                <div>
                  <strong>{expense.name}</strong>
                  <span>
                    {formatDate(expense.due_date)} ·{" "}
                    {expense.category_id ? categoryMap.get(expense.category_id) : "Sem categoria"}
                  </span>
                </div>
                <strong>{formatMoney(expense.expected_amount)}</strong>
                <div className="row-actions">
                  <button type="button" onClick={() => editExpense(expense)}>Editar</button>
                  <button
                    type="button"
                    onClick={() => void api.deleteExpense(expense.id).then(load)}
                  >
                    Remover
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
