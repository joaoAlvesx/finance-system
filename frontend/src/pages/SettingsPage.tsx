import { useCallback, useEffect, useRef, useState } from "react";
import { PluggyConnect } from "react-pluggy-connect";
import type { ConnectEventPayload } from "react-pluggy-connect";

import { api } from "../api";
import { ErrorState, LoadingState } from "../components/PageState";
import { formatDateTime, formatMoney } from "../format";
import type { Account, PluggyStatus } from "../types";

type ConnectMode = "sandbox" | "personal";

export default function SettingsPage() {
  const [status, setStatus] = useState<PluggyStatus | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [connectToken, setConnectToken] = useState<string | null>(null);
  const [connectMode, setConnectMode] = useState<ConnectMode>("personal");
  const [updateItem, setUpdateItem] = useState<string | undefined>();
  const [existingItemId, setExistingItemId] = useState("");
  const [selections, setSelections] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const observedItemId = useRef<string | null>(null);
  const registrationsInProgress = useRef(new Set<string>());

  const load = useCallback(async () => {
    setError(null);
    try {
      const [pluggyStatus, localAccounts] = await Promise.all([
        api.pluggyStatus(),
        api.accounts(),
      ]);
      setStatus(pluggyStatus);
      setAccounts(localAccounts);
      setSelections((current) => {
        const next = { ...current };
        for (const item of pluggyStatus.items) {
          for (const account of item.accounts) {
            if (account.local_account_id) next[account.id] = account.local_account_id;
          }
        }
        return next;
      });
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
    window.setTimeout(() => setNotice(null), 3200);
  }

  async function openConnect(mode: ConnectMode, itemId?: string) {
    setBusy(true);
    setError(null);
    try {
      const response = await api.pluggyConnectToken(itemId);
      setConnectMode(mode);
      setUpdateItem(itemId);
      setConnectToken(response.connect_token);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível abrir a Pluggy.");
    } finally {
      setBusy(false);
    }
  }

  async function registerConnection(itemId: string, closeWidget: boolean) {
    const normalizedItemId = itemId.trim();
    if (!normalizedItemId || registrationsInProgress.current.has(normalizedItemId)) return;
    registrationsInProgress.current.add(normalizedItemId);
    observedItemId.current = normalizedItemId;
    if (closeWidget) setConnectToken(null);
    setBusy(true);
    setError(null);
    try {
      await api.registerPluggyItem(normalizedItemId);
      await load();
      setExistingItemId("");
      showNotice(
        closeWidget
          ? "Conexão registrada. Vincule as contas antes de sincronizar."
          : "Conexão identificada. Acompanhando o processamento da Pluggy.",
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível registrar a conexão.");
    } finally {
      registrationsInProgress.current.delete(normalizedItemId);
      setBusy(false);
    }
  }

  function captureConnectionEvent(payload: ConnectEventPayload) {
    if (!("item" in payload) || !payload.item.id) return;
    observedItemId.current = payload.item.id;
    if (payload.event === "LOGIN_SUCCESS" || payload.event === "LOGIN_STEP_COMPLETED") {
      void registerConnection(payload.item.id, false);
    }
  }

  function closeConnectWidget() {
    setConnectToken(null);
    const itemId = observedItemId.current;
    if (itemId) void registerConnection(itemId, true);
  }

  async function linkAccount(linkId: string) {
    const accountId = selections[linkId];
    if (!accountId) return;
    setBusy(true);
    try {
      await api.linkPluggyAccount(linkId, accountId);
      await load();
      showNotice("Conta externa vinculada à conta local.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível vincular a conta.");
    } finally {
      setBusy(false);
    }
  }

  async function requestSync(itemId: string, full = false) {
    setBusy(true);
    try {
      await api.syncPluggy(itemId, full);
      await load();
      showNotice(full ? "Reconciliação completa agendada." : "Sincronização agendada.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível agendar a sincronização.");
    } finally {
      setBusy(false);
    }
  }

  if (error && !status) return <ErrorState message={error} retry={() => void load()} />;
  if (loading || !status) return <LoadingState label="Carregando integrações…" />;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Integrações</p>
          <h1>Configurações</h1>
          <p>Conecte suas próprias contas e acompanhe a sincronização sem expor credenciais.</p>
        </div>
      </header>

      {notice && <div className="toast" role="status">{notice}</div>}
      {error && <div className="inline-error" role="alert">{error}</div>}

      <section className="panel pluggy-overview">
        <div>
          <p className="eyebrow">Open Finance</p>
          <h2>Pluggy</h2>
          <p>{status.provider_refresh_note}</p>
        </div>
        <div className="integration-actions">
          <span className={`badge ${status.configured ? "success" : "warning"}`}>
            {status.configured ? "Servidor configurado" : "Aguardando configuração"}
          </span>
          <button
            className="button primary"
            type="button"
            disabled={!status.configured || busy}
            onClick={() => void openConnect("personal")}
          >
            Conectar Meu Pluggy
          </button>
          {status.include_sandbox && (
            <button
              className="button secondary"
              type="button"
              disabled={!status.configured || busy}
              onClick={() => void openConnect("sandbox")}
            >
              Testar sandbox
            </button>
          )}
        </div>
      </section>

      {!status.configured && (
        <section className="panel integration-help">
          <h2>Preparação segura</h2>
          <p>
            Ative a integração somente no backend com as variáveis
            <code> FINANCE_PLUGGY_CLIENT_ID </code> e
            <code> FINANCE_PLUGGY_CLIENT_SECRET</code>. Elas nunca são enviadas ao navegador.
          </p>
        </section>
      )}

      {status.configured && (
        <section className="panel integration-help">
          <h2>Item já criado na Pluggy</h2>
          <p>
            Se a conexão terminou no painel da Pluggy, informe o Item ID para o sistema
            acompanhar a sincronização.
          </p>
          <div className="integration-actions">
            <input
              aria-label="Item ID da Pluggy"
              value={existingItemId}
              placeholder="00000000-0000-0000-0000-000000000000"
              onChange={(event) => setExistingItemId(event.target.value)}
            />
            <button
              className="button secondary"
              type="button"
              disabled={busy || !existingItemId.trim()}
              onClick={() => void registerConnection(existingItemId, true)}
            >
              Registrar item existente
            </button>
          </div>
        </section>
      )}

      <div className="integration-list">
        {status.items.map((item) => (
          <section className="panel integration-item" key={item.id}>
            <div className="panel-header">
              <div>
                <p className="eyebrow">{item.connector_name ?? "Conexão Pluggy"}</p>
                <h2>{item.status}</h2>
                <p>
                  Última sincronização: {formatDateTime(item.last_successful_sync_at)} ·
                  Reconciliação: {formatDateTime(item.last_full_sync_at)}
                </p>
              </div>
              <span className={`badge ${item.requires_user_action ? "danger" : "success"}`}>
                {item.requires_user_action ? "Ação necessária" : item.execution_status ?? "Aguardando"}
              </span>
            </div>

            {item.error_code && <div className="inline-error">Código: {item.error_code}</div>}

            <div className="integration-actions">
              <button
                className="button secondary"
                type="button"
                disabled={busy}
                onClick={() => void requestSync(item.id)}
              >
                Sincronizar agora
              </button>
              <button
                className="button ghost"
                type="button"
                disabled={busy}
                onClick={() => void requestSync(item.id, true)}
              >
                Reconciliação completa
              </button>
              {item.requires_user_action && (
                <button
                  className="button primary"
                  type="button"
                  disabled={busy}
                  onClick={() => void openConnect("personal", item.external_item_id)}
                >
                  Renovar consentimento
                </button>
              )}
            </div>

            <div className="external-account-list">
              {item.accounts.map((externalAccount) => (
                <article className="external-account" key={externalAccount.id}>
                  <div>
                    <strong>{externalAccount.name}</strong>
                    <span>
                      {externalAccount.subtype ?? externalAccount.account_type} ·
                      {formatMoney(externalAccount.balance)}
                    </span>
                  </div>
                  <select
                    aria-label={`Conta local para ${externalAccount.name}`}
                    value={selections[externalAccount.id] ?? ""}
                    disabled={busy}
                    onChange={(event) =>
                      setSelections((current) => ({
                        ...current,
                        [externalAccount.id]: event.target.value,
                      }))
                    }
                  >
                    <option value="">Selecione a conta local</option>
                    {accounts.map((account) => (
                      <option value={account.id} key={account.id}>{account.name}</option>
                    ))}
                  </select>
                  <button
                    className="button secondary"
                    type="button"
                    disabled={busy || !selections[externalAccount.id]}
                    onClick={() => void linkAccount(externalAccount.id)}
                  >
                    {externalAccount.local_account_id ? "Atualizar vínculo" : "Vincular"}
                  </button>
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>

      {status.latest_run && (
        <section className="panel sync-summary">
          <div>
            <p className="eyebrow">Última execução</p>
            <h2>{status.latest_run.status}</h2>
            <p>Finalizada em {formatDateTime(status.latest_run.finished_at)}</p>
          </div>
          <dl>
            <div><dt>Novas</dt><dd>{status.latest_run.created_count}</dd></div>
            <div><dt>Atualizadas</dt><dd>{status.latest_run.updated_count}</dd></div>
            <div><dt>Reconciliadas</dt><dd>{status.latest_run.reconciled_count}</dd></div>
            <div><dt>Ignoradas</dt><dd>{status.latest_run.ignored_count}</dd></div>
          </dl>
        </section>
      )}

      {connectToken && (
        <PluggyConnect
          connectToken={connectToken}
          includeSandbox={connectMode === "sandbox"}
          connectorIds={connectMode === "personal" && !updateItem ? [status.connector_id] : undefined}
          updateItem={updateItem}
          language="pt"
          theme="dark"
          onEvent={captureConnectionEvent}
          onSuccess={({ item }) => registerConnection(item.id, true)}
          onError={() => {
            setConnectToken(null);
            setError("A conexão não foi concluída. Revise o consentimento e tente novamente.");
          }}
          onClose={closeConnectWidget}
        />
      )}
    </div>
  );
}
