import { FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { ErrorState, LoadingState } from "../components/PageState";
import { formatMoney } from "../format";
import type {
  AssistantAnswer,
  AssistantInsights,
  AssistantValueKind,
  CategorySuggestion,
} from "../types";

const kindLabels: Record<AssistantValueKind, string> = {
  calculated: "Calculado",
  prediction: "Previsão",
  suggestion: "Sugestão",
};

interface Message {
  role: "user" | "assistant";
  text: string;
  kind?: AssistantValueKind;
}

export default function AssistantPage() {
  const [insights, setInsights] = useState<AssistantInsights | null>(null);
  const [suggestions, setSuggestions] = useState<CategorySuggestion[]>([]);
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "Pergunte sobre saldo, disponível, contas futuras, resumo mensal ou simule uma compra.",
      kind: "suggestion",
    },
  ]);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [nextInsights, nextSuggestions] = await Promise.all([
        api.assistantInsights(),
        api.categorySuggestions(),
      ]);
      setInsights(nextInsights);
      setSuggestions(nextSuggestions);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Erro inesperado.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function ask(event?: FormEvent, preset?: string) {
    event?.preventDefault();
    const text = (preset ?? question).trim();
    if (!text || busy) return;
    setQuestion("");
    setBusy(true);
    setMessages((current) => [...current, { role: "user", text }]);
    try {
      const answer: AssistantAnswer = await api.assistantQuery(text);
      setMessages((current) => [
        ...current,
        { role: "assistant", text: answer.answer, kind: answer.value_kind },
      ]);
    } catch (cause) {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: cause instanceof Error ? cause.message : "Não foi possível responder.",
          kind: "suggestion",
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function decide(id: string, decision: "accept" | "reject") {
    setBusy(true);
    try {
      await api.decideCategorySuggestion(id, decision);
      setSuggestions((current) => current.filter((item) => item.id !== id));
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível revisar a sugestão.");
    } finally {
      setBusy(false);
    }
  }

  if (error && !insights) return <ErrorState message={error} retry={() => void load()} />;
  if (!insights) return <LoadingState label="Calculando insights locais…" />;

  return (
    <div className="page assistant-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Fase 6</p>
          <h1>Assistente financeiro</h1>
          <p>Respostas locais e determinísticas, disponíveis mesmo sem Hermes ou IA.</p>
        </div>
      </header>

      {error && <div className="inline-error">{error}</div>}

      <section className="assistant-insights" aria-label="Insights financeiros">
        {insights.cards.map((card) => (
          <article className={`panel insight-card ${card.severity}`} key={card.key}>
            <span className={`value-kind ${card.value_kind}`}>
              {kindLabels[card.value_kind]}
            </span>
            <h2>{card.title}</h2>
            <p>{card.text}</p>
          </article>
        ))}
      </section>

      <div className="assistant-layout">
        <section className="panel chat-panel">
          <div className="panel-header">
            <div>
              <h2>Pergunte aos seus dados</h2>
              <p>Os valores vêm da API financeira.</p>
            </div>
          </div>
          <div className="chat-messages" aria-live="polite">
            {messages.map((message, index) => (
              <div className={`chat-message ${message.role}`} key={`${message.role}-${index}`}>
                {message.kind && (
                  <span className={`value-kind ${message.kind}`}>
                    {kindLabels[message.kind]}
                  </span>
                )}
                <p>{message.text}</p>
              </div>
            ))}
          </div>
          <div className="suggested-questions">
            {insights.suggested_questions.map((item) => (
              <button type="button" disabled={busy} key={item} onClick={() => void ask(undefined, item)}>
                {item}
              </button>
            ))}
          </div>
          <form className="assistant-form" onSubmit={(event) => void ask(event)}>
            <label className="sr-only" htmlFor="assistant-question">Pergunta</label>
            <input
              id="assistant-question"
              maxLength={500}
              placeholder="Ex.: quanto posso gastar até a próxima entrada?"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
            />
            <button className="button primary" type="submit" disabled={busy || !question.trim()}>
              {busy ? "Consultando…" : "Perguntar"}
            </button>
          </form>
        </section>

        <section className="panel suggestion-panel">
          <div className="panel-header">
            <div>
              <h2>Categorias sugeridas</h2>
              <p>Nenhuma sugestão altera seus dados sem revisão.</p>
            </div>
          </div>
          {suggestions.length === 0 ? (
            <p className="muted">Não há sugestões pendentes.</p>
          ) : (
            <ul className="suggestion-list">
              {suggestions.map((item) => (
                <li key={item.id}>
                  <strong>{item.transaction_description}</strong>
                  <span>{formatMoney(item.transaction_amount)} · {item.suggested_category_name}</span>
                  <small>Confiança {Math.round(Number(item.confidence) * 100)}%</small>
                  <div className="row-actions">
                    <button type="button" disabled={busy} onClick={() => void decide(item.id, "accept")}>
                      Aceitar
                    </button>
                    <button type="button" disabled={busy} onClick={() => void decide(item.id, "reject")}>
                      Rejeitar
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
