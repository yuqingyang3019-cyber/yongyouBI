import { Alert, Button, Spin } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";

import { fetchSqlBotEmbedConfig } from "../receivables/api";
import type { SqlBotEmbedConfig } from "../receivables/api";


const EVENT_NAME = "sqlbot_embedded_event";


export function SqlBotPanel() {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [config, setConfig] = useState<SqlBotEmbedConfig | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const loadConfig = useCallback(async () => {
    setError("");
    setReady(false);
    try {
      setConfig(await fetchSqlBotEmbedConfig());
    } catch (exc) {
      setConfig(null);
      setError(exc instanceof Error ? exc.message : "SQLBot 配置加载失败");
    }
  }, []);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig, reloadKey]);

  useEffect(() => {
    if (!config) {
      return;
    }
    const sqlbotOrigin = new URL(config.baseUrl).origin;

    const sendCertificate = (current: SqlBotEmbedConfig) => {
      const contentWindow = iframeRef.current?.contentWindow;
      contentWindow?.postMessage(
        {
          eventName: EVENT_NAME,
          messageId: String(current.embeddedId),
          hostOrigin: window.location.origin
        },
        sqlbotOrigin
      );
      contentWindow?.postMessage(
        {
          eventName: EVENT_NAME,
          messageId: String(current.embeddedId),
          busi: "certificate",
          type: 4,
          certificate: current.token
        },
        sqlbotOrigin
      );
    };

    const onMessage = (event: MessageEvent) => {
      if (
        event.origin === sqlbotOrigin &&
        event.data?.eventName === EVENT_NAME &&
        String(event.data?.messageId) === String(config.embeddedId) &&
        event.data?.busi === "ready"
      ) {
        sendCertificate(config);
        setReady(true);
      }
    };
    window.addEventListener("message", onMessage);

    const refreshTimer = window.setInterval(async () => {
      try {
        const refreshed = await fetchSqlBotEmbedConfig();
        setConfig(refreshed);
        sendCertificate(refreshed);
      } catch {
        setError("SQLBot 会话续期失败，请刷新后重试");
      }
    }, 4 * 60 * 1000);

    const readyTimer = window.setTimeout(() => {
      setReady((current) => {
        if (!current) {
          setError("SQLBot 暂时无法连接，应收工作台不受影响");
        }
        return current;
      });
    }, 15_000);

    return () => {
      window.removeEventListener("message", onMessage);
      window.clearInterval(refreshTimer);
      window.clearTimeout(readyTimer);
    };
  }, [config]);

  if (error && !config) {
    return (
      <Alert
        action={<Button onClick={() => setReloadKey((value) => value + 1)}>重试</Button>}
        description="请确认 SQLBot 已启动，且管理员已完成嵌入应用配置。"
        message={error}
        showIcon
        type="warning"
      />
    );
  }

  if (!config) {
    return <Spin tip="正在连接智能问数…" />;
  }

  const source = `${config.baseUrl}/#/embeddedPage?id=${config.embeddedId}&type=4&history=true`;
  return (
    <div style={{ minHeight: 680, position: "relative" }}>
      {!ready ? <Spin fullscreen={false} tip="正在加载 SQLBot…" /> : null}
      {error ? <Alert closable message={error} showIcon type="warning" /> : null}
      <iframe
        allow="clipboard-read; clipboard-write"
        ref={iframeRef}
        src={source}
        style={{ border: 0, display: "block", height: 720, width: "100%" }}
        title="应收智能问数"
      />
    </div>
  );
}
