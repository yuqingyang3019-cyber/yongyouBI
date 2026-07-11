import { useState } from "react";

import { ContractOverdue } from "./pages/ContractOverdue";
import { Dashboard } from "./pages/Dashboard";

type AppTab = "dashboard" | "overdue";

export default function App() {
  const [tab, setTab] = useState<AppTab>("dashboard");

  return (
    <div className="app-shell">
      <nav className="app-tabs" aria-label="主导航">
        <button
          type="button"
          className={tab === "dashboard" ? "app-tab active" : "app-tab"}
          onClick={() => setTab("dashboard")}
        >
          采购驾驶舱
        </button>
        <button
          type="button"
          className={tab === "overdue" ? "app-tab active" : "app-tab"}
          onClick={() => setTab("overdue")}
        >
          合同逾期
        </button>
      </nav>
      {tab === "dashboard" ? <Dashboard /> : <ContractOverdue />}
    </div>
  );
}
