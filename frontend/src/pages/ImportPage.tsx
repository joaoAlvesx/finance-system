import { type FormEvent, useEffect, useState } from "react";

import { api } from "../api";
import { ErrorState, LoadingState } from "../components/PageState";
import { formatDate, formatMoney } from "../format";
import type { Account, ImportPreview, ImportRow } from "../types";

const statusLabels: Record<ImportRow["status"], string> = {
  valid: "Válida",
  possible_duplicate: "Possível duplicidade",
  invalid: "Inválida",
  imported: "Importada",
};

export default function ImportPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [rows, setRows] = useState<ImportRow[]>([]);
  const [selectedDuplicates, setSelectedDuplicates] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  useEffect(() => {
    api.accounts()
      .then((items) => {
        setAccounts(items);
        setAccountId(items[0]?.id ?? "");
      })
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setLoading(false));
  }, []);

  async function submitPreview(event: FormEvent) {
    event.preventDefault();
    if (!file || !accountId) return;
    setProcessing(true);
    setError(null);
    setResult(null);
    try {
      const nextPreview = await api.previewImport(accountId, file);
      setPreview(nextPreview);
      setRows(nextPreview.rows);
      setSelectedDuplicates(new Set());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao analisar o arquivo.");
    } finally {
      setProcessing(false);
    }
  }

  async function loadMoreRows() {
    if (!preview) return;
    setProcessing(true);
    try {
      const nextPage = await api.importDetails(preview.id, rows.length);
      setRows((current) => [...current, ...nextPage.rows]);
      setPreview({ ...nextPage, rows: [...rows, ...nextPage.rows] });
    } finally {
      setProcessing(false);
    }
  }

  function toggleDuplicate(rowNumber: number) {
    setSelectedDuplicates((current) => {
      const next = new Set(current);
      if (next.has(rowNumber)) next.delete(rowNumber);
      else next.add(rowNumber);
      return next;
    });
  }

  async function confirm() {
    if (!preview) return;
    setProcessing(true);
    setError(null);
    try {
      const response = await api.confirmImport(preview.id, [...selectedDuplicates]);
      setResult(
        `${response.imported_rows} transações importadas. ${response.skipped_possible_duplicates} possíveis duplicidades foram ignoradas.`,
      );
      setPreview({ ...preview, status: "imported", imported_rows: response.imported_rows });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao confirmar a importação.");
    } finally {
      setProcessing(false);
    }
  }

  if (loading) return <LoadingState label="Preparando importação…" />;
  if (!accounts.length) {
    return (
      <ErrorState message="Cadastre uma conta antes de importar um extrato." />
    );
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Histórico bancário</p>
          <h1>Importar CSV</h1>
          <p>Confira todas as informações antes de gravar novas transações.</p>
        </div>
      </header>

      {error && <div className="inline-error" role="alert">{error}</div>}
      {result && <div className="inline-success" role="status">{result}</div>}

      <section className="panel upload-panel">
        <div className="step-number">1</div>
        <div className="upload-copy">
          <h2>Selecione o extrato</h2>
          <p>Formato atual: CSV da conta corrente Banco Inter, com valores em BRL.</p>
        </div>
        <form className="upload-form" onSubmit={(event) => void submitPreview(event)}>
          <label>
            <span>Conta de destino</span>
            <select value={accountId} onChange={(event) => setAccountId(event.target.value)}>
              {accounts.map((account) => (
                <option value={account.id} key={account.id}>{account.name}</option>
              ))}
            </select>
          </label>
          <label className="file-drop">
            <input
              required
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <span className="file-symbol" aria-hidden="true">⇧</span>
            <strong>{file?.name ?? "Escolher arquivo CSV"}</strong>
            <small>O arquivo fica no seu servidor e não é enviado para IA.</small>
          </label>
          <button className="button primary" disabled={!file || processing} type="submit">
            {processing ? "Analisando…" : "Gerar prévia"}
          </button>
        </form>
      </section>

      {preview && (
        <>
          <section className="preview-section">
            <div className="section-title-with-step">
              <div className="step-number">2</div>
              <div>
                <h2>Revise o resumo</h2>
                <p>{preview.filename}</p>
              </div>
            </div>
            <div className="preview-metrics">
              <article><span>Linhas encontradas</span><strong>{preview.total_rows}</strong></article>
              <article><span>Transações válidas</span><strong>{preview.valid_rows}</strong></article>
              <article className="warning-card"><span>Possíveis duplicidades</span><strong>{preview.possible_duplicate_rows}</strong></article>
              <article className={preview.invalid_rows ? "danger-card" : ""}><span>Linhas inválidas</span><strong>{preview.invalid_rows}</strong></article>
              <article><span>Período</span><strong className="small-value">{formatDate(preview.period_start)} — {formatDate(preview.period_end)}</strong></article>
              <article><span>Saldo líquido</span><strong className="small-value">{formatMoney(preview.net_amount)}</strong></article>
            </div>
          </section>

          <section className="panel preview-table-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Prévia</p>
                <h2>Linhas do arquivo</h2>
              </div>
              <span>{rows.length} de {preview.total_rows}</span>
            </div>
            <div className="table-scroll">
              <table className="transaction-table compact-table">
                <thead>
                  <tr><th>Linha</th><th>Data</th><th>Descrição</th><th>Status</th><th className="align-right">Valor</th></tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.row_number}>
                      <td>{row.row_number}</td>
                      <td>{formatDate(row.transaction_date)}</td>
                      <td className="description-cell"><strong>{row.description ?? "—"}</strong><span>{row.historical_label}</span></td>
                      <td>
                        {row.status === "possible_duplicate" ? (
                          <label className="duplicate-choice">
                            <input
                              type="checkbox"
                              checked={selectedDuplicates.has(row.row_number)}
                              onChange={() => toggleDuplicate(row.row_number)}
                            />
                            Importar mesmo assim
                          </label>
                        ) : (
                          <span className={`badge ${row.status === "invalid" ? "danger" : "success"}`}>
                            {statusLabels[row.status]}
                          </span>
                        )}
                      </td>
                      <td className={`align-right money-cell ${row.direction ?? ""}`}>
                        {row.direction === "credit" ? "+ " : row.direction === "debit" ? "− " : ""}
                        {formatMoney(row.amount)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {rows.length < preview.total_rows && (
              <button className="button secondary centered-button" disabled={processing} onClick={() => void loadMoreRows()} type="button">
                Carregar mais linhas
              </button>
            )}
          </section>

          <section className="confirm-panel">
            <div className="section-title-with-step">
              <div className="step-number">3</div>
              <div>
                <h2>Confirmar importação</h2>
                <p>A operação é transacional e pode ser repetida sem duplicar o arquivo.</p>
              </div>
            </div>
            <button
              className="button primary large-button"
              disabled={processing || preview.status === "imported"}
              onClick={() => void confirm()}
              type="button"
            >
              {preview.status === "imported" ? "Arquivo já importado" : processing ? "Importando…" : "Confirmar e importar"}
            </button>
          </section>
        </>
      )}
    </div>
  );
}
