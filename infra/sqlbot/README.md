# SQLBot 本地配置

## 启动

```bash
docker compose -f infra/sqlbot/compose.yml up -d
```

访问 `http://localhost:8080`，首次登录账号为 `admin`、密码为
`SQLBot@123456`。登录后必须立即修改默认密码。

## 阿里云百炼模型

在“系统管理 → AI 模型配置”新增阿里云百炼模型：

- 模型：`qwen-plus`
- API 地址：`https://dashscope.aliyuncs.com/compatible-mode/v1`
- API Key：从百炼控制台获取，不写入仓库

将该模型设为默认模型并授权给应收工作空间。

在应收工作空间创建内部成员账号，账号必须与后端
`SQLBOT_EMBED_ACCOUNT` 一致。

## 应收数据源

新建 PostgreSQL 数据源：

- 主机：`host.docker.internal`
- 端口：`5432`
- 数据库：`yongyou_receivables`
- 用户：`sqlbot_reader`
- 密码：本地 `SQLBOT_DB_PASSWORD`
- Schema：仅选择 `receivable_analytics`

只开启以下表或视图：

- `invoice_facts`：发票级应收事实
- `contract_receivable_summary`：合同应收汇总
- `customer_aging_summary`：客户账龄汇总

## 问数校准

建议问题：

1. 当前真实逾期金额最高的 10 个客户是谁？
2. 未来 7 天有哪些发票到期？
3. 各客户逾期 1-7 天、8-30 天、31-90 天和 90 天以上的金额是多少？
4. 哪些合同尚有未收金额？
5. 本月已收金额和未收金额分别是多少？
6. 哪些发票尚未匹配到销售合同？
7. 哪些发票缺少审核时间？
8. 张三负责的真实逾期发票有哪些？
9. 已部分回款但仍逾期的发票有哪些？
10. 真实逾期金额最高的 10 份合同是什么？

口径说明：

- “真实逾期”对应 `true_status = 'true_overdue'`。
- “未收金额”使用 `outstanding`，不要用发票含税金额代替。
- “即将到期”对应 `true_status = 'upcoming'`。
- “已结清”对应 `true_status = 'settled'`。
- 所有金额均为人民币，保留两位小数。

## 交付版嵌入

在“系统管理 → 嵌入式管理 → 页面嵌入”创建应用：

- 跨域地址：`http://localhost:5173`
- 记录数值 ID、App ID 和 App Secret
- 分别填入后端 `.env` 的 `SQLBOT_EMBEDDED_ID`、`SQLBOT_APP_ID`、
  `SQLBOT_APP_SECRET`

后端签发 5 分钟有效的 HS256 token，前端只拿短期 token，App Secret
不会进入浏览器构建产物。
