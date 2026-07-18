import { Bar, Column } from "@ant-design/plots";
import { ProCard } from "@ant-design/pro-components";
import { Col, Empty, Row, Space, Spin, Typography } from "antd";

import type { ReceivableChartsData } from "../receivables/types";

interface ReceivableChartsProps {
  charts: ReceivableChartsData | null;
  loading?: boolean;
  selectedAging?: string;
  selectedCustomer?: string;
  onAgingSelect?: (label: string) => void;
  onCustomerSelect?: (customer: string) => void;
}

function hasOverdueData(charts: ReceivableChartsData): boolean {
  return charts.agingBuckets.some((item) => item.count > 0 || item.amount > 0);
}

export function ReceivableCharts({
  charts,
  loading = false,
  selectedAging = "",
  selectedCustomer = "",
  onAgingSelect,
  onCustomerSelect
}: ReceivableChartsProps) {
  if (loading && !charts) {
    return (
      <ProCard style={{ marginBottom: 16, textAlign: "center" }}>
        <Spin tip="图表加载中…" />
      </ProCard>
    );
  }

  if (!charts || !hasOverdueData(charts)) {
    return (
      <ProCard title="逾期分析" style={{ marginBottom: 16 }}>
        <Empty description="暂无真实逾期数据" />
      </ProCard>
    );
  }

  const amountData = charts.agingBuckets.map((item) => ({
    label: item.label,
    value: Number((item.amount / 10_000).toFixed(2)),
    rawAmount: item.amount
  }));

  const customerData = charts.topCustomers.map((item) => ({
    customer: item.customer,
    value: item.amount,
    count: item.count
  }));

  return (
    <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
      <Col xs={24} lg={11}>
        <ProCard title="系统测算逾期账龄">
          <Column
            data={amountData}
            xField="label"
            yField="value"
            height={280}
            label={{
              position: "top",
              formatter: (datum: { value?: number }) => `${datum.value ?? 0}万`
            }}
            tooltip={{
              formatter: (datum: { label?: string; rawAmount?: number }) => ({
                name: "未收金额",
                value: `¥${Number(datum.rawAmount ?? 0).toLocaleString("zh-CN")}`
              })
            }}
          />
          <Space size={[8, 8]} wrap>
            {charts.agingBuckets.map((bucket) => (
              <Typography.Link
                key={bucket.label}
                strong={selectedAging === bucket.label}
                onClick={() => onAgingSelect?.(bucket.label)}
              >
                {bucket.label}：{bucket.count} 笔
              </Typography.Link>
            ))}
          </Space>
        </ProCard>
      </Col>
      <Col xs={24} lg={13}>
        <ProCard title="风险客户（系统测算逾期）">
          {customerData.length ? (
            <>
              <Bar
                data={customerData}
                xField="value"
                yField="customer"
                height={Math.max(280, customerData.length * 36)}
                label={{ position: "right", formatter: (d: { value?: number }) => `¥${d.value ?? 0}` }}
              />
              <Space size={[8, 8]} wrap>
                {charts.topCustomers.map((item) => (
                  <Typography.Link
                    key={item.customer}
                    strong={selectedCustomer === item.customer}
                    onClick={() => onCustomerSelect?.(item.customer)}
                  >
                    {item.customer}：{item.count} 笔
                  </Typography.Link>
                ))}
              </Space>
            </>
          ) : (
            <Empty description="暂无客户逾期数据" />
          )}
        </ProCard>
      </Col>
    </Row>
  );
}
