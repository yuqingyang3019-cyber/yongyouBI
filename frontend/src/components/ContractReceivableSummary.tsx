import type { ProColumns } from "@ant-design/pro-components";
import { ProTable } from "@ant-design/pro-components";
import { Empty, Space, Tag, Typography } from "antd";

import type { ContractReceivableSummary } from "../receivables/types";

const { Text } = Typography;

function formatMoney(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 0
  }).format(value);
}

const columns: ProColumns<ContractReceivableSummary>[] = [
  {
    title: "合同编号",
    dataIndex: "contractCode",
    width: 150,
    copyable: true
  },
  {
    title: "客户",
    dataIndex: "customer",
    width: 180,
    ellipsis: true
  },
  {
    title: "发票笔数",
    dataIndex: "invoiceCount",
    width: 90
  },
  {
    title: "应收合计",
    dataIndex: "receivableAmount",
    valueType: "money",
    width: 130
  },
  {
    title: "已收合计",
    dataIndex: "collectedAmount",
    valueType: "money",
    width: 130
  },
  {
    title: "未收余额",
    dataIndex: "outstanding",
    valueType: "money",
    width: 130,
    render: (_, row) => (
      <Text type={row.outstanding > 0 ? "danger" : undefined}>{formatMoney(row.outstanding)}</Text>
    )
  },
  {
    title: "真实逾期笔数",
    dataIndex: "trueOverdueCount",
    width: 110,
    render: (_, row) =>
      row.trueOverdueCount > 0 ? <Tag color="error">{row.trueOverdueCount}</Tag> : row.trueOverdueCount
  },
  {
    title: "真实逾期金额",
    dataIndex: "trueOverdueAmount",
    valueType: "money",
    width: 140,
    render: (_, row) => (
      <Text type={row.trueOverdueAmount > 0 ? "danger" : undefined}>
        {formatMoney(row.trueOverdueAmount)}
      </Text>
    )
  }
];

interface ContractReceivableSummaryTableProps {
  rows: ContractReceivableSummary[];
}

export function ContractReceivableSummaryTable({ rows }: ContractReceivableSummaryTableProps) {
  const overdueContracts = rows.filter((row) => row.trueOverdueCount > 0).length;
  const overdueAmount = rows.reduce((sum, row) => sum + row.trueOverdueAmount, 0);

  if (!rows.length) {
    return <Empty description="暂无合同汇总数据" />;
  }

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Text type="secondary">
        {overdueContracts} 份合同存在真实逾期，未收逾期合计 {formatMoney(overdueAmount)}
      </Text>
      <ProTable<ContractReceivableSummary>
        rowKey="contractCode"
        search={false}
        options={false}
        scroll={{ x: "max-content" }}
        pagination={{ pageSize: 10, showSizeChanger: true }}
        dataSource={rows}
        columns={columns}
        headerTitle="合同应收汇总"
      />
    </Space>
  );
}
