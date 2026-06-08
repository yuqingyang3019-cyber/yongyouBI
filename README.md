# YonBIP BI

读取 YonBIP 采购链路接口，并按月份统计每个业务执行人的执行数量和执行金额。

第一版统计范围：

- 采购合同：按 `purPersonName` 统计，金额取 `taxMoney` 优先。
- 采购订单：按 `operator_name` 统计，金额取 `oriSum` / `moneysum` / `listOriSum` 优先。
- 付款申请单：按 `staff_name` 统计，金额取 `oriAmount` / `bodyItem_oriAmount` 优先。

## 后端

后端接口：

- `GET /health`
- `GET /api/bi/execution-summary?month=YYYY-MM`

必要环境变量见 `.env.example`。用友密钥只在后端读取，前端不会接触 `appKey`、`secret` 或 `access_token`。

## 前端

前端提供月份筛选、单据类型筛选、KPI 卡片和 ECharts 图表，入口在 `frontend/src/pages/Dashboard.tsx`。
