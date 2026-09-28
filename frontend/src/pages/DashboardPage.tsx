import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { ErrorState, LoadingState } from "../components/PageState";
import { formatDate, formatMoney } from "../format";
import type { Dashboard, Transaction } from "../types";

function TransactionLine({ transaction }: { transaction: Transaction }) {
  const signal = transaction.direction === "credit" ? "+" : "−";
  return (
    <li className="transaction-line">
      <div className={`transaction-icon ${transaction.direction}`} aria-hidden="true">
        {transaction.direction === "credit" ? "↓" : "↑"}
      </div>
      <div className="transaction-copy">
        <strong>{transaction.description_raw}</strong>
        <span>{formatDate(transaction.transaction_date)}</span>
      </div>
      <span className={`transaction-value ${transaction.direction}`}>
        {signal} {formatMoney(transaction.amount)}
      </span>
    </li>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await api.dashboard());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Erro inesperado.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) return <ErrorState message={error} retry={() => void load()} />;
  if (!data) return <LoadingState label="Calculando sua visão financeira…" />;

  const maxCategory = Math.max(
    ...data.spending_by_category.map((item) => Number(item.amount)),
    1,
  );

  return (
    <div className="page dashboard-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Hoje</p>
          <h1>Visão geral</h1>
          <p>Acompanhe o que pode gastar sem comprometer os próximos dias.</p>
        </div>
        <Link className="button secondary" to="/transacoes">
          Ver transações
        </Link>
      </header>

      <section className="metric-grid" aria-label="Resumo financeiro">
        <article className="metric-card primary-metric">
          <span>Disponível até a próxima entrada</span>
          <strong>{formatMoney(data.available_until_next_income)}</strong>
          {data.next_income ? (
            <small>
              Próxima entrada em {formatDate(data.next_income.expected_date)} ·{" "}
              {formatMoney(data.next_income.expected_amount)}
            </small>
          ) : (
            <small>
              <Link to="/planejamento">Cadastre a próxima entrada</Link> para calcular este
              valor.
            </small>
          )}
        </article>
        <article className="metric-card">
          <span>Limite seguro diário</span>
          <strong>{formatMoney(data.daily_safe_limit)}</strong>
          <small>Do dia atual até a véspera da entrada</small>
        </article>
        <article className="metric-card">
          <span>Saldo atual</span>
          <strong>{formatMoney(data.current_balance)}</strong>
          <small>Consolidado a partir do último saldo apurado</small>
        </article>
        <article className="metric-card">
          <span>Próxima entrada</span>
          <strong className="metric-date">
            {data.next_income ? formatDate(data.next_income.expected_date) : "Não configurada"}
          </strong>
          <small>{data.next_income?.name ?? "Adicione uma renda no planejamento"}</small>
        </article>
      </section>

      <section className="insight-strip">
        <div>
          <span>Entradas no mês</span>
          <strong className="credit">{formatMoney(data.month_income)}</strong>
        </div>
        <div>
          <span>Saídas no mês</span>
          <strong>{formatMoney(data.month_expense)}</strong>
        </div>
        <div>
          <span>Compromissos previstos</span>
          <strong>{formatMoney(data.committed_expenses)}</strong>
        </div>
        <div>
          <span>Reserva protegida</span>
          <strong>{formatMoney(data.minimum_reserve)}</strong>
        </div>
      </section>

      <div className="dashboard-columns">
        <section className="panel category-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Mês atual</p>
              <h2>Gastos por categoria</h2>
            </div>
          </div>
          {data.spending_by_category.length ? (
            <div className="category-bars">
              {data.spending_by_category.map((item, index) => (
                <div className="category-bar-row" key={item.category_id ?? "none"}>
                  <div className="category-bar-label">
                    <span>{item.category_name}</span>
                    <strong>{formatMoney(item.amount)}</strong>
                  </div>
                  <div className="category-track">
                    <span
                      style={{
                        width: `${(Number(item.amount) / maxCategory) * 100}%`,
                        background: `var(--chart-${(index % 5) + 1})`,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">Ainda não há despesas no mês atual.</p>
          )}
        </section>

        <section className="panel review-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Organização</p>
              <h2>Itens para revisar</h2>
            </div>
            <Link to="/transacoes?revisar=1">Revisar</Link>
          </div>
          <div className="review-number">{data.review_count}</div>
          <p>
            {data.uncategorized_count} transações ainda estão sem categoria. Revise aos poucos
            para melhorar seus relatórios.
          </p>
          <div className="progress-track" aria-label="Progresso da categorização">
            <span
              style={{
                width: `${Math.max(4, 100 - Math.min(100, data.uncategorized_count / 40))}%`,
              }}
            />
          </div>
        </section>
      </div>

      <section className="panel recent-panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Movimentação</p>
            <h2>Últimas transações</h2>
          </div>
          <Link to="/transacoes">Ver todas</Link>
        </div>
        <ul className="transaction-list">
          {data.recent_transactions.map((transaction) => (
            <TransactionLine transaction={transaction} key={transaction.id} />
          ))}
        </ul>
      </section>
    </div>
  );
}
