# 应收逾期管理

交付版聚焦销售发票、销售合同与收款单的同步、匹配和应收逾期分析。采购驾驶舱、工资模板和本体管理属于实验室功能，不进入客户交付物。

## 本地 PostgreSQL 与 SQLBot

应收主数据使用 PostgreSQL，SQLite 仅保留为历史迁移源和通讯录缓存。

```bash
brew install postgresql@17
brew services start postgresql@17
make postgres-config
make postgres-setup
make postgres-migrate
make sqlbot-up
make sqlbot-config
make verify-postgres-sqlbot
```

SQLBot 访问 `http://localhost:8080`，首次配置百炼模型、只读数据源和页面嵌入应用的步骤见 [infra/sqlbot/README.md](infra/sqlbot/README.md)。

## 运行入口

```bash
# 交付版
make dev-product-backend
make dev-product-frontend

# 实验室（后端端口 8001）
make dev-labs-backend
make dev-labs-frontend
```

## 后端

后端接口：

- `GET /health`
- `GET /api/auth/config`
- `POST /api/auth/dingtalk-login`
- `GET /api/auth/me`
- `GET /api/bi/contract-overdue`
- `GET /api/bi/contract-overdue/sync-status`
- `POST /api/bi/contract-overdue/sync`
- `/api/notifications/*`：通讯录搜索与逾期摘要定时任务管理
- `GET /api/sqlbot/embed-token`：签发 SQLBot 页面嵌入短期凭证

除健康检查和登录接口外，生产 API 均要求钉钉登录。必要环境变量见 `.env.example`。用友和钉钉 Secret 只在后端读取，前端仅获得钉钉 `corpId` 与应用 `appKey`（作为 JSAPI `clientId`）。

钉钉企业内部应用需开通免登、通讯录只读和机器人单聊权限，并配置 `DINGTALK_APP_KEY`、`DINGTALK_APP_SECRET`、`DINGTALK_CORP_ID`、`DINGTALK_ROBOT_CODE`。生产环境必须使用 HTTPS，设置随机 `APP_SESSION_SECRET`，并保持 `COOKIE_SECURE=true`。

本地浏览器调试可临时设置 `ALLOW_BROWSER_LOGIN=true`；该入口会使用配置的本地用户身份，生产环境必须保持关闭。

## 前端

交付版在钉钉内自动免登后进入应收管理，可在“应收管理 / 智能问数”之间切换。用户可搜索企业通讯录，立即发送当前逾期摘要，并创建分钟、小时、每天或每周执行的通知任务；任务可在页面启停和删除。实验页面使用独立入口和构建命令。

开发时 Vite 已监听 `0.0.0.0`，同一局域网内其他人可通过 `http://<本机IP>:5173` 访问（启动后终端会打印 Network 地址）。后端仍只需在本机 `8000` 端口运行，API 由 Vite 代理转发。

## 测试

生产测试、构建与交付打包：

```bash
make test-product
make build-product
make delivery
```

交付包输出到 `dist/yongyou-receivables.zip`，仅包含生产后端白名单和生产前端资源。

## OpenSpec

本项目使用 [OpenSpec](https://github.com/Fission-AI/OpenSpec) 做规格驱动开发。规格与变更提案在 `openspec/`，Cursor 斜杠命令在 `.cursor/commands/`。

常用流程（在 Cursor 聊天中）：

1. `/opsx:explore` — 先摸清现状与方案（可选）
2. `/opsx:propose <改动名>` — 写提案、规格增量与任务清单
3. `/opsx:apply` — 按任务实现
4. `/opsx:archive` — 归档并把规格合并回 `openspec/specs/`

本地 CLI（需 Node.js ≥ 20.19）：

```bash
npm install -g @fission-ai/openspec@latest
openspec list
openspec validate --all
```
