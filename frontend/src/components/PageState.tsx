import type { ReactNode } from "react";

export function LoadingState({ label = "Carregando dados…" }: { label?: string }) {
  return (
    <div className="state-panel" role="status">
      <span className="spinner" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="state-panel error-panel" role="alert">
      <strong>Não foi possível carregar</strong>
      <p>{message}</p>
      {retry && (
        <button className="button secondary" onClick={retry} type="button">
          Tentar novamente
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{children}</p>
    </div>
  );
}
