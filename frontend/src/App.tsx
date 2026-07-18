import { RobotOutlined, UnorderedListOutlined } from "@ant-design/icons";
import { Button, Result, Segmented, Spin } from "antd";
import { useEffect, useState } from "react";

import { initializeAuth, type AuthUser } from "./auth";
import { SqlBotPanel } from "./components/SqlBotPanel";
import { ReceivableWorkbenchV2 } from "./pages/ReceivableWorkbenchV2";

export default function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [view, setView] = useState<"receivables" | "sqlbot">("receivables");

  useEffect(() => {
    setError("");
    initializeAuth()
      .then(setUser)
      .catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : "钉钉登录失败")
      );
  }, [attempt]);

  if (error) {
    return (
      <Result
        status="warning"
        title="无法进入应收账款工作台"
        subTitle={error}
        extra={<Button type="primary" onClick={() => setAttempt((value) => value + 1)}>重试</Button>}
      />
    );
  }
  if (!user) {
    return <Spin fullscreen tip="正在完成钉钉登录…" />;
  }
  return (
    <div>
      <div style={{ background: "#fff", borderBottom: "1px solid #eef0f3", padding: "12px 24px" }}>
        <Segmented<"receivables" | "sqlbot">
          onChange={setView}
          options={[
            { value: "receivables", label: "应收管理", icon: <UnorderedListOutlined /> },
            { value: "sqlbot", label: "智能问数", icon: <RobotOutlined /> }
          ]}
          value={view}
        />
      </div>
      {view === "receivables" ? (
        <ReceivableWorkbenchV2 currentUser={user} />
      ) : (
        <main style={{ padding: 24 }}>
          <SqlBotPanel />
        </main>
      )}
    </div>
  );
}
