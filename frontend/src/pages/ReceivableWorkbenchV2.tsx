import {
  BarChartOutlined,
  DatabaseOutlined,
  ReloadOutlined,
  SyncOutlined,
  UnorderedListOutlined,
  WarningOutlined
} from "@ant-design/icons";
import type { ProColumns } from "@ant-design/pro-components";
import { PageContainer, ProCard, ProTable, StatisticCard } from "@ant-design/pro-components";
import {
  Alert,
  Button,
  Col,
  ConfigProvider,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Progress,
  Row,
  Segmented,
  Skeleton,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message
} from "antd";
import zhCN from "antd/locale/zh_CN";
import dayjs from "dayjs";
import { useEffect, useMemo, useRef, useState } from "react";

import type { AuthUser } from "../auth";
import { ContractReceivableSummaryTable } from "../components/ContractReceivableSummary";
import { NotificationManager } from "../components/NotificationManager";
import { ReceivableCharts } from "../components/ReceivableCharts";
import { ReceivableSyncStatusBanner, ReceivableSyncStatusInline } from "../components/ReceivableSyncStatus";
import {
  fetchContractOverdue,
  fetchContractOverdueSyncStatus,
  triggerContractOverdueSync
} from "../receivables/api";
import type { ContractOverdueResult, ContractOverdueRow, MatchQuality } from "../receivables/types";

const { Text } = Typography;

type ProductView = "workbench" | "management" | "health";
type WorkbenchTab = "today" | "all" | "exceptions" | "settled";
type WorkItemKind = "overdue" | "review" | "upcoming" | "normal";
type StatusFilter = "all" | "overdue" | "upcoming";

interface WorkItem {
  key: string;
  customer: string;
  contractCode: string;
  outstanding: number;
  overdueAmount: number;
  invoiceCount: number;
  longestOverdueDays: number;
  nearestDueDays: number;
  matchQuality: MatchQuality;
  owner: string;
  kind: WorkItemKind;
  invoices: ContractOverdueRow[];
}

const QUALITY_LABEL: Record<MatchQuality, string> = {
  exact: "发票号或订单号精确关联",
  partial_exact: "精确关联，尚未收清",
  contract: "合同内按时间分配",
  estimated: "客户维度估算，待核实",
  unpaid: "尚未发现可关联收款"
};

const QUALITY_RANK: Record<MatchQuality, number> = {
  estimated: 0,
  unpaid: 1,
  contract: 2,
  partial_exact: 3,
  exact: 4
};

function money(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 0
  }).format(value);
}

function trueStatus(row: ContractOverdueRow): string {
  return row.trueStatus ?? row.status;
}

function qualityTag(quality: MatchQuality) {
  if (quality === "exact" || quality === "partial_exact") return <Tag color="success">高可信</Tag>;
  if (quality === "contract") return <Tag color="processing">合同内分配</Tag>;
  if (quality === "estimated") return <Tag color="warning">待核实</Tag>;
  return <Tag>未确认</Tag>;
}

function riskTag(kind: WorkItemKind) {
  if (kind === "overdue") return <Tag color="error">高风险</Tag>;
  if (kind === "review") return <Tag color="warning">待核实</Tag>;
  if (kind === "upcoming") return <Tag color="gold">即将到期</Tag>;
  return <Tag color="success">正常</Tag>;
}

function buildWorkItems(rows: ContractOverdueRow[]): WorkItem[] {
  const groups = new Map<string, ContractOverdueRow[]>();
  rows.forEach((row) => {
    const key = `${row.customer}::${row.contractCode || "missing"}`;
    groups.set(key, [...(groups.get(key) ?? []), row]);
  });
  const priority: Record<WorkItemKind, number> = { review: 0, overdue: 1, upcoming: 2, normal: 3 };

  return Array.from(groups.entries())
    .map(([key, invoices]) => {
      const matchQuality = invoices
        .map((row) => row.matchQuality)
        .reduce((worst, value) => (QUALITY_RANK[value] < QUALITY_RANK[worst] ? value : worst));
      const owners = Array.from(
        new Set(invoices.map((row) => row.salesman).filter((value) => value && value !== "未分配"))
      );
      const hasOverdue = invoices.some((row) => trueStatus(row) === "true_overdue");
      const hasUpcoming = invoices.some((row) => trueStatus(row) === "upcoming");
      const kind: WorkItemKind =
        matchQuality === "estimated" ? "review" : hasOverdue ? "overdue" : hasUpcoming ? "upcoming" : "normal";
      const futureDays = invoices.filter((row) => row.daysUntilDue >= 0).map((row) => row.daysUntilDue);
      return {
        key,
        customer: invoices[0]?.customer ?? "未填写",
        contractCode: invoices[0]?.contractCode || "缺少合同",
        outstanding: invoices.reduce((sum, row) => sum + row.outstanding, 0),
        overdueAmount: invoices
          .filter((row) => trueStatus(row) === "true_overdue")
          .reduce((sum, row) => sum + row.outstanding, 0),
        invoiceCount: invoices.length,
        longestOverdueDays: Math.max(
          0,
          ...invoices.map((row) => (row.daysUntilDue < 0 ? Math.abs(row.daysUntilDue) : 0))
        ),
        nearestDueDays: futureDays.length ? Math.min(...futureDays) : Number.POSITIVE_INFINITY,
        matchQuality,
        owner: owners.length === 1 ? owners[0] : "待确认",
        kind,
        invoices
      };
    })
    .sort(
      (left, right) =>
        priority[left.kind] - priority[right.kind] ||
        right.longestOverdueDays - left.longestOverdueDays ||
        right.outstanding - left.outstanding
    );
}

function exportCsv(rows: ContractOverdueRow[]) {
  const headers = ["发票编号", "客户", "合同编号", "应收金额", "已匹配收款", "未收余额", "到期日", "匹配方式"];
  const content = [
    headers,
    ...rows.map((row) => [
      row.invoiceCode,
      row.customer,
      row.contractCode,
      row.taxAmount,
      row.collectedAmount,
      row.outstanding,
      row.dueDate,
      QUALITY_LABEL[row.matchQuality]
    ])
  ]
    .map((line) => line.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(","))
    .join("\n");
  const url = URL.createObjectURL(new Blob(["\ufeff" + content], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `应收明细_${dayjs().format("YYYYMMDD_HHmm")}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

const invoiceColumns: ProColumns<ContractOverdueRow>[] = [
  {
    title: "搜索",
    dataIndex: "keyword",
    hideInTable: true,
    fieldProps: { placeholder: "发票号 / 客户 / 合同号 / 责任信息" }
  },
  { title: "发票编号", dataIndex: "invoiceCode", width: 140, copyable: true, search: false },
  { title: "客户", dataIndex: "customer", width: 180, ellipsis: true, search: false },
  { title: "合同编号", dataIndex: "contractCode", width: 140, search: false },
  { title: "应收金额", dataIndex: "taxAmount", valueType: "money", width: 120, search: false, sorter: true },
  { title: "已匹配收款", dataIndex: "collectedAmount", valueType: "money", width: 130, search: false },
  {
    title: "未收余额",
    dataIndex: "outstanding",
    width: 120,
    search: false,
    sorter: true,
    render: (_, row) => <Text type={row.outstanding > 0 ? "danger" : undefined}>{money(row.outstanding)}</Text>
  },
  {
    title: "匹配可信度",
    dataIndex: "matchQuality",
    width: 130,
    valueType: "select",
    valueEnum: {
      exact: { text: "高可信" },
      partial_exact: { text: "高可信，未收清" },
      contract: { text: "合同内分配" },
      estimated: { text: "待核实" },
      unpaid: { text: "未确认" }
    },
    render: (_, row) => qualityTag(row.matchQuality)
  },
  { title: "到期日", dataIndex: "dueDate", valueType: "dateRange", width: 120, sorter: true },
  {
    title: "逾期 / 到期",
    dataIndex: "daysUntilDue",
    width: 110,
    search: false,
    sorter: true,
    render: (_, row) =>
      row.daysUntilDue < 0 ? (
        <Text type="danger">逾期 {Math.abs(row.daysUntilDue)} 天</Text>
      ) : (
        `${row.daysUntilDue} 天后`
      )
  },
  { title: "责任信息", dataIndex: "salesman", width: 110, valueType: "text" }
];

const readOnlyColumns = invoiceColumns.map((column) => ({ ...column, search: false }));

function filterRows(
  rows: ContractOverdueRow[],
  params: Record<string, unknown>,
  statusFilter: StatusFilter
): ContractOverdueRow[] {
  const keyword = String(params.keyword ?? "").trim().toLowerCase();
  const quality = String(params.matchQuality ?? "");
  const owner = String(params.salesman ?? "").trim().toLowerCase();
  const range = params.dueDate as [string, string] | undefined;
  return rows.filter((row) => {
    const matchesStatus =
      statusFilter === "all" ||
      (statusFilter === "overdue" && trueStatus(row) === "true_overdue") ||
      (statusFilter === "upcoming" && trueStatus(row) === "upcoming");
    const matchesKeyword =
      !keyword ||
      [row.invoiceCode, row.customer, row.contractCode, row.salesman].some((value) =>
        value.toLowerCase().includes(keyword)
      );
    const matchesQuality = !quality || row.matchQuality === quality;
    const matchesOwner = !owner || row.salesman.toLowerCase().includes(owner);
    const matchesDate = !range?.[0] || !range?.[1] || (row.dueDate >= range[0] && row.dueDate <= range[1]);
    return matchesStatus && matchesKeyword && matchesQuality && matchesOwner && matchesDate;
  });
}

function Metric({
  title,
  count,
  amount,
  onClick,
  tooltip
}: {
  title: string;
  count: number;
  amount: number;
  onClick?: () => void;
  tooltip?: string;
}) {
  return (
    <StatisticCard
      hoverable={Boolean(onClick)}
      onClick={onClick}
      statistic={{
        title: tooltip ? <Tooltip title={tooltip}>{title}</Tooltip> : title,
        value: count,
        description: money(amount)
      }}
      style={{ cursor: onClick ? "pointer" : "default", height: "100%" }}
    />
  );
}

function WorkItemDrawer({ item, onClose }: { item: WorkItem | null; onClose: () => void }) {
  return (
    <Drawer
      title={item ? `${item.customer} / ${item.contractCode}` : "应收详情"}
      width={720}
      open={Boolean(item)}
      onClose={onClose}
    >
      {item ? (
        <>
          <Space wrap>
            {riskTag(item.kind)}
            {qualityTag(item.matchQuality)}
            <Text type="secondary">{item.invoiceCount} 张发票</Text>
          </Space>
          <Descriptions column={2} bordered size="small" style={{ marginTop: 16 }}>
            <Descriptions.Item label="未收余额">
              <Text strong type="danger">{money(item.outstanding)}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="系统测算逾期">{money(item.overdueAmount)}</Descriptions.Item>
            <Descriptions.Item label="最长逾期">
              {item.longestOverdueDays ? `${item.longestOverdueDays} 天` : "尚未逾期"}
            </Descriptions.Item>
            <Descriptions.Item label="责任信息">
              {item.owner} <Text type="secondary">（来源待确认）</Text>
            </Descriptions.Item>
          </Descriptions>
          <Divider orientation="left">计算与收款依据</Divider>
          {item.matchQuality === "estimated" ? (
            <Alert
              type="warning"
              showIcon
              icon={<WarningOutlined />}
              message="该收款关系由系统估算"
              description="收款缺少精确关联字段，系统按客户和发票时间顺序分配。此结果不是用友核销关系。"
              style={{ marginBottom: 16 }}
            />
          ) : null}
          <Table<ContractOverdueRow>
            rowKey="invoiceId"
            size="small"
            pagination={false}
            dataSource={item.invoices}
            scroll={{ x: 720 }}
            columns={[
              { title: "发票", dataIndex: "invoiceCode", width: 120 },
              { title: "应收", dataIndex: "taxAmount", align: "right", render: (value) => money(value) },
              { title: "已匹配", dataIndex: "collectedAmount", align: "right", render: (value) => money(value) },
              {
                title: "未收",
                dataIndex: "outstanding",
                align: "right",
                render: (value) => <Text type="danger">{money(value)}</Text>
              },
              {
                title: "到期日依据",
                key: "basis",
                width: 190,
                render: (_, row) => (
                  <Space direction="vertical" size={0}>
                    <Text>{row.dueDate || "无法计算"}</Text>
                    <Text type="secondary">审核日 + {row.paymentTermDays} 天账期</Text>
                  </Space>
                )
              },
              { title: "匹配", dataIndex: "matchQuality", render: (value) => QUALITY_LABEL[value as MatchQuality] }
            ]}
          />
        </>
      ) : null}
    </Drawer>
  );
}

export function ReceivableWorkbenchV2({ currentUser }: { currentUser: AuthUser }) {
  const updatedAtRef = useRef("");
  const [data, setData] = useState<ContractOverdueResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [productView, setProductView] = useState<ProductView>("workbench");
  const [workbenchTab, setWorkbenchTab] = useState<WorkbenchTab>("today");
  const [selectedItem, setSelectedItem] = useState<WorkItem | null>(null);
  const [selectedAging, setSelectedAging] = useState("");
  const [selectedCustomer, setSelectedCustomer] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [exportRows, setExportRows] = useState<ContractOverdueRow[]>([]);

  function load(sync = true, showLoading = true) {
    if (showLoading) setLoading(true);
    setError("");
    return fetchContractOverdue(["overdue", "upcoming", "normal"], sync)
      .then((result) => {
        setData(result);
        updatedAtRef.current = result.meta.updatedAt || result.meta.sync.updatedAt || "";
      })
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "数据加载失败"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load(true);
  }, []);

  useEffect(() => {
    let ignore = false;
    const timer = window.setInterval(() => {
      fetchContractOverdueSyncStatus()
        .then((status) => {
          const updatedAt = status.updatedAt || "";
          if (!ignore && status.status === "done" && updatedAt && updatedAt !== updatedAtRef.current) {
            updatedAtRef.current = updatedAt;
            load(false, false).then(() => message.info("数据已更新"));
          }
        })
        .catch(() => undefined);
    }, 3000);
    return () => {
      ignore = true;
      window.clearInterval(timer);
    };
  }, []);

  const rows = data?.rows ?? [];
  const workItems = useMemo(() => buildWorkItems(rows), [rows]);
  const reviewRows = rows.filter((row) => row.matchQuality === "estimated");
  const exceptionRows = [...(data?.pendingAuditRows ?? []), ...(data?.unmatchedRows ?? [])];
  const allKnownRows = [...rows, ...(data?.settledRows ?? []), ...exceptionRows];
  const reviewAmount = reviewRows.reduce((sum, row) => sum + row.outstanding, 0);
  const exceptionAmount = exceptionRows.reduce((sum, row) => sum + row.taxAmount, 0);
  const highConfidenceCount = allKnownRows.filter((row) =>
    ["exact", "partial_exact"].includes(row.matchQuality)
  ).length;
  const matchCoverage = allKnownRows.length ? Math.round((highConfidenceCount / allKnownRows.length) * 100) : 0;
  const isSyncing =
    data?.meta.sync.status === "running" || data?.meta.collectionSync?.status === "running";

  const workItemColumns = [
    { title: "优先级", dataIndex: "kind", width: 100, render: (_: unknown, row: WorkItem) => riskTag(row.kind) },
    {
      title: "客户 / 合同",
      key: "subject",
      render: (_: unknown, row: WorkItem) => (
        <Space direction="vertical" size={0}>
          <Text strong>{row.customer}</Text>
          <Text type="secondary">{row.contractCode}</Text>
        </Space>
      )
    },
    { title: "未收余额", dataIndex: "outstanding", align: "right" as const, render: (value: number) => <Text strong>{money(value)}</Text> },
    {
      title: "风险原因",
      key: "reason",
      render: (_: unknown, row: WorkItem) =>
        row.kind === "review"
          ? "收款按客户维度估算，需要核对"
          : row.longestOverdueDays
            ? `最长逾期 ${row.longestOverdueDays} 天`
            : `${row.nearestDueDays} 天后到期`
    },
    { title: "匹配可信度", dataIndex: "matchQuality", width: 130, render: (value: MatchQuality) => qualityTag(value) },
    { title: "责任信息", dataIndex: "owner", width: 110 },
    {
      title: "",
      key: "action",
      width: 90,
      render: (_: unknown, row: WorkItem) => <Button type="link" onClick={() => setSelectedItem(row)}>查看详情</Button>
    }
  ];

  const analysisRows = rows.filter((row) => {
    if (selectedCustomer) return row.customer === selectedCustomer;
    if (!selectedAging) return true;
    if (trueStatus(row) !== "true_overdue") return false;
    const days = Math.abs(row.daysUntilDue);
    if (selectedAging === "1-7天") return days <= 7;
    if (selectedAging === "8-30天") return days >= 8 && days <= 30;
    if (selectedAging === "31-90天") return days >= 31 && days <= 90;
    return days > 90;
  });

  const invoiceTable = (
    <ProTable<ContractOverdueRow>
      rowKey="invoiceId"
      columns={invoiceColumns}
      loading={loading}
      headerTitle={
        statusFilter === "overdue"
          ? "系统测算逾期发票"
          : statusFilter === "upcoming"
            ? "7天内到期发票"
            : "未结应收发票"
      }
      params={{ statusFilter }}
      search={{ labelWidth: "auto", defaultCollapsed: false }}
      scroll={{ x: "max-content" }}
      pagination={{ pageSize: 20, showSizeChanger: true }}
      columnsState={{ persistenceKey: "receivable-invoice-columns-v2", persistenceType: "localStorage" }}
      options={{ density: true, setting: true, reload: false }}
      toolBarRender={() => [
        <Button key="export" disabled={!exportRows.length} onClick={() => exportCsv(exportRows)}>
          导出筛选结果（{exportRows.length} 条）
        </Button>
      ]}
      request={async (params, sort) => {
        const filtered = filterRows(rows, params, statusFilter);
        const sortField = Object.keys(sort ?? {})[0] as keyof ContractOverdueRow | undefined;
        const order = Object.values(sort ?? {})[0];
        const sorted = sortField && order
          ? [...filtered].sort((left, right) => {
              const a = left[sortField] ?? 0;
              const b = right[sortField] ?? 0;
              const value = typeof a === "number" && typeof b === "number"
                ? a - b
                : String(a).localeCompare(String(b));
              return order === "ascend" ? value : -value;
            })
          : filtered;
        setExportRows(sorted);
        return { data: sorted, success: true, total: sorted.length };
      }}
    />
  );

  const workbench = (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={12} xl={6}>
          <Metric title="系统测算逾期" count={data?.summary.trueOverdue.count ?? 0} amount={data?.summary.trueOverdue.amount ?? 0} tooltip="已超过测算到期日且尚未收清，不等同于用友核销结论" onClick={() => { setStatusFilter("overdue"); setWorkbenchTab("all"); }} />
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Metric title="7天内到期" count={data?.summary.upcoming.count ?? 0} amount={data?.summary.upcoming.amount ?? 0} onClick={() => { setStatusFilter("upcoming"); setWorkbenchTab("all"); }} />
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Metric title="匹配待核实" count={reviewRows.length} amount={reviewAmount} tooltip="收款缺少精确关联字段，由系统按客户和时间顺序估算" onClick={() => setWorkbenchTab("today")} />
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Metric title="数据异常" count={exceptionRows.length} amount={exceptionAmount} onClick={() => setWorkbenchTab("exceptions")} />
        </Col>
      </Row>
      <ProCard>
        <Tabs
          activeKey={workbenchTab}
          onChange={(value) => setWorkbenchTab(value as WorkbenchTab)}
          items={[
            {
              key: "today",
              label: `今日待处理（${workItems.filter((item) => item.kind !== "normal").length}）`,
              children: workItems.some((item) => item.kind !== "normal") ? (
                <Table<WorkItem>
                  rowKey="key"
                  columns={workItemColumns}
                  dataSource={workItems.filter((item) => item.kind !== "normal")}
                  pagination={{ pageSize: 10 }}
                  scroll={{ x: 920 }}
                />
              ) : <Empty description="当前没有待处理应收" />
            },
            {
              key: "all",
              label: "全部未结应收",
              children: (
                <>
                  {statusFilter !== "all" ? (
                    <Alert
                      type="info"
                      showIcon
                      message={statusFilter === "overdue" ? "当前仅显示系统测算逾期" : "当前仅显示 7 天内到期"}
                      action={<Button size="small" onClick={() => setStatusFilter("all")}>查看全部</Button>}
                      style={{ marginBottom: 16 }}
                    />
                  ) : null}
                  {invoiceTable}
                </>
              )
            },
            {
              key: "exceptions",
              label: `数据异常（${exceptionRows.length}）`,
              children: (
                <Tabs items={[
                  {
                    key: "audit",
                    label: `缺少有效审核时间（${data?.pendingAuditRows.length ?? 0}）`,
                    children: <ProTable rowKey="invoiceId" search={false} options={false} dataSource={data?.pendingAuditRows ?? []} columns={readOnlyColumns} scroll={{ x: "max-content" }} />
                  },
                  {
                    key: "term",
                    label: `缺少合同或有效账期（${data?.unmatchedRows.length ?? 0}）`,
                    children: <ProTable rowKey="invoiceId" search={false} options={false} dataSource={data?.unmatchedRows ?? []} columns={readOnlyColumns} scroll={{ x: "max-content" }} />
                  }
                ]} />
              )
            },
            {
              key: "settled",
              label: `已结清归档（${data?.settledRows.length ?? 0}）`,
              children: <ProTable rowKey="invoiceId" search={false} options={false} dataSource={data?.settledRows ?? []} columns={readOnlyColumns} scroll={{ x: "max-content" }} />
            }
          ]}
        />
      </ProCard>
    </>
  );

  const management = (
    <>
      <Alert type="info" showIcon message="当前无历史快照，不展示环比趋势；责任人来源尚未确认，暂不输出团队风险排名。" style={{ marginBottom: 16 }} />
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={12} xl={6}><Metric title="未结应收" count={rows.length} amount={rows.reduce((sum, row) => sum + row.outstanding, 0)} /></Col>
        <Col xs={24} md={12} xl={6}><Metric title="系统测算逾期" count={data?.summary.trueOverdue.count ?? 0} amount={data?.summary.trueOverdue.amount ?? 0} /></Col>
        <Col xs={24} md={12} xl={6}><Metric title="7天内到期" count={data?.summary.upcoming.count ?? 0} amount={data?.summary.upcoming.amount ?? 0} /></Col>
        <Col xs={24} md={12} xl={6}><Metric title="待核实金额" count={reviewRows.length} amount={reviewAmount} /></Col>
      </Row>
      <ReceivableCharts
        charts={data?.charts ?? null}
        loading={loading}
        selectedAging={selectedAging}
        selectedCustomer={selectedCustomer}
        onAgingSelect={(value) => { setSelectedAging((current) => current === value ? "" : value); setSelectedCustomer(""); }}
        onCustomerSelect={(value) => { setSelectedCustomer((current) => current === value ? "" : value); setSelectedAging(""); }}
      />
      {selectedAging || selectedCustomer ? (
        <ProCard title={selectedAging ? `${selectedAging}明细` : `${selectedCustomer}明细`} extra={<Button onClick={() => { setSelectedAging(""); setSelectedCustomer(""); }}>清除筛选</Button>}>
          <ProTable rowKey="invoiceId" search={false} options={false} dataSource={analysisRows} columns={readOnlyColumns} scroll={{ x: "max-content" }} />
        </ProCard>
      ) : <ContractReceivableSummaryTable rows={data?.contractSummary ?? []} />}
    </>
  );

  const health = (
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={14}>
        <ProCard title="数据新鲜度">
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="统计范围">{data?.range.start ?? "-"} 至 {data?.range.end ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="最近更新">{data?.meta.updatedAt || "尚未完成同步"}</Descriptions.Item>
            <Descriptions.Item label="发票同步">{data?.meta.sync.status ?? "准备中"}，缓存 {data?.meta.cachedInvoiceCount ?? 0} 张</Descriptions.Item>
            <Descriptions.Item label="收款同步">{data?.meta.collectionSync?.status ?? "准备中"}，缓存 {data?.meta.cachedCollectionCount ?? 0} 笔</Descriptions.Item>
            <Descriptions.Item label="合同缓存">{data?.meta.cachedContractCount ?? 0} 份</Descriptions.Item>
          </Descriptions>
        </ProCard>
      </Col>
      <Col xs={24} lg={10}>
        <ProCard title="匹配质量">
          <Text>发票号或订单号精确关联</Text>
          <Progress percent={matchCoverage} />
          <Space direction="vertical">
            <Text type="secondary">高可信 {highConfidenceCount} 笔</Text>
            <Text type="secondary">客户维度估算 {reviewRows.length} 笔</Text>
            <Text type="secondary">尚未发现可关联收款 {allKnownRows.filter((row) => row.matchQuality === "unpaid").length} 笔</Text>
          </Space>
        </ProCard>
      </Col>
      <Col span={24}>
        <ProCard title="数据缺失">
          <Row gutter={[16, 16]}>
            <Col xs={24} md={12}><Alert type={data?.pendingAuditRows.length ? "warning" : "success"} showIcon message={`缺少有效审核时间 ${data?.pendingAuditRows.length ?? 0} 笔`} description="无法据此判断上游是否处于审批中，只能确认审核时间字段无效。" /></Col>
            <Col xs={24} md={12}><Alert type={data?.unmatchedRows.length ? "warning" : "success"} showIcon message={`缺少合同或有效账期 ${data?.unmatchedRows.length ?? 0} 笔`} description="这些发票不会被错误归类为正常或逾期。" /></Col>
          </Row>
        </ProCard>
      </Col>
    </Row>
  );

  return (
    <ConfigProvider locale={zhCN}>
      <PageContainer
        title="应收账款"
        subTitle="识别回款风险，核对测算依据"
        extra={
          <Space wrap>
            <Text type="secondary">{currentUser.name}</Text>
            <NotificationManager />
            <ReceivableSyncStatusInline data={data} />
            <Button icon={<ReloadOutlined />} onClick={() => load(false)}>刷新缓存</Button>
            <Button
              type="primary"
              icon={<SyncOutlined spin={isSyncing} />}
              loading={isSyncing}
              disabled={isSyncing}
              onClick={() => triggerContractOverdueSync().then(() => message.success("已开始同步上游数据")).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "触发同步失败"))}
            >
              同步数据
            </Button>
          </Space>
        }
      >
        {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} /> : null}
        <ReceivableSyncStatusBanner data={data} />
        {loading && !data ? (
          <ProCard><Skeleton active paragraph={{ rows: 10 }} /></ProCard>
        ) : (
          <>
            <Segmented<ProductView>
              block
              value={productView}
              onChange={setProductView}
              options={[
                { value: "workbench", label: "应收工作台", icon: <UnorderedListOutlined /> },
                { value: "management", label: "管理概览", icon: <BarChartOutlined /> },
                { value: "health", label: "数据健康", icon: <DatabaseOutlined /> }
              ]}
              style={{ marginBottom: 16 }}
            />
            {productView === "workbench" ? workbench : productView === "management" ? management : health}
          </>
        )}
        <WorkItemDrawer item={selectedItem} onClose={() => setSelectedItem(null)} />
      </PageContainer>
    </ConfigProvider>
  );
}
