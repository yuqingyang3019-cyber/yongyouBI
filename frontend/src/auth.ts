export interface AuthUser {
  userid: string;
  name: string;
  avatar?: string;
  title?: string;
}

interface DingTalkConfig {
  configured: boolean;
  corpId: string;
  clientId: string;
  dingtalkLoginEnabled: boolean;
  browserLoginEnabled: boolean;
}

declare global {
  interface Window {
    dd?: {
      env?: { platform?: string };
      ready?: (callback: () => void) => void;
      error?: (callback: (error: unknown) => void) => void;
      runtime?: {
        permission?: {
          requestAuthCode?: (options: {
            corpId: string;
            clientId: string;
            onSuccess: (result: { code?: string }) => void;
            onFail: (error: unknown) => void;
          }) => void;
        };
      };
    };
  }
}

async function responseJson<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(String(body.detail || body.message || `请求失败：${response.status}`));
  }
  return body as T;
}

async function requestAuthCode(config: DingTalkConfig): Promise<string> {
  const dd = window.dd;
  const platform = String(dd?.env?.platform || "").toLowerCase();
  if (!dd?.runtime?.permission?.requestAuthCode || platform === "notindingtalk") {
    throw new Error("请在钉钉客户端内打开应收账款工作台");
  }
  await new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error("等待钉钉 JSAPI 就绪超时")), 12000);
    const done = (callback: () => void) => {
      window.clearTimeout(timer);
      callback();
    };
    dd.ready?.(() => done(resolve));
    dd.error?.((error) => done(() => reject(error)));
  });
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error("获取钉钉免登码超时")), 12000);
    dd.runtime!.permission!.requestAuthCode!({
      corpId: config.corpId,
      clientId: config.clientId,
      onSuccess: (result) => {
        window.clearTimeout(timer);
        result.code ? resolve(result.code) : reject(new Error("钉钉未返回免登码"));
      },
      onFail: (error) => {
        window.clearTimeout(timer);
        reject(error);
      }
    });
  });
}

function isDingTalkClient(): boolean {
  const platform = String(window.dd?.env?.platform || "").toLowerCase();
  return Boolean(
    window.dd?.runtime?.permission?.requestAuthCode
    && platform !== "notindingtalk"
  );
}

export async function initializeAuth(): Promise<AuthUser> {
  const me = await fetch("/api/auth/me", { credentials: "include" });
  if (me.ok) return (await responseJson<{ user: AuthUser }>(me)).user;

  const config = await responseJson<DingTalkConfig>(
    await fetch("/api/auth/config", { credentials: "include" })
  );
  if (config.browserLoginEnabled && (!config.dingtalkLoginEnabled || !isDingTalkClient())) {
    const browserLogin = await responseJson<{ user: AuthUser }>(
      await fetch("/api/auth/browser-login", {
        method: "POST",
        credentials: "include"
      })
    );
    return browserLogin.user;
  }
  if (!config.dingtalkLoginEnabled) throw new Error("登录功能未启用");
  if (!config.configured) throw new Error("钉钉登录未配置，请联系管理员");
  const code = await requestAuthCode(config);
  const login = await responseJson<{ user: AuthUser }>(
    await fetch("/api/auth/dingtalk-login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, corpId: config.corpId })
    })
  );
  return login.user;
}
