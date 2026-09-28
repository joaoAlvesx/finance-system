import { NavLink, Route, Routes } from "react-router-dom";

import DashboardPage from "./pages/DashboardPage";
import AssistantPage from "./pages/AssistantPage";
import ImportPage from "./pages/ImportPage";
import PlanningPage from "./pages/PlanningPage";
import SettingsPage from "./pages/SettingsPage";
import TransactionsPage from "./pages/TransactionsPage";

const navigation = [
  { to: "/", label: "Visão geral", symbol: "◫", end: true },
  { to: "/transacoes", label: "Transações", symbol: "↕" },
  { to: "/planejamento", label: "Planejamento", symbol: "◷" },
  { to: "/assistente", label: "Assistente", symbol: "✦" },
  { to: "/importar", label: "Importar CSV", symbol: "⇧" },
  { to: "/configuracoes", label: "Configurações", symbol: "⚙" },
];

function Navigation() {
  return (
    <nav className="navigation" aria-label="Navegação principal">
      {navigation.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
        >
          <span className="nav-symbol" aria-hidden="true">
            {item.symbol}
          </span>
          <span>{item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

export default function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">F</span>
          <div>
            <strong>Finanças</strong>
            <small>Pessoal e privado</small>
          </div>
        </div>
        <Navigation />
        <div className="privacy-note">
          <span className="status-dot" />
          Dados no seu servidor
        </div>
      </aside>

      <main className="main-content">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/transacoes" element={<TransactionsPage />} />
          <Route path="/planejamento" element={<PlanningPage />} />
          <Route path="/assistente" element={<AssistantPage />} />
          <Route path="/importar" element={<ImportPage />} />
          <Route path="/configuracoes" element={<SettingsPage />} />
        </Routes>
      </main>

      <div className="mobile-navigation">
        <Navigation />
      </div>
    </div>
  );
}
