import type { ContractAttachment, ContractOverdueRow, OverdueStatus } from "../types";

const STATUS_LABEL: Record<OverdueStatus, string> = {
  overdue: "已逾期",
  upcoming: "即将逾期",
  normal: "正常",
  paid: "已付清"
};

function formatMoney(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 2
  }).format(value);
}

function formatDays(days: number): string {
  if (days < 0) {
    return `逾期 ${Math.abs(days)} 天`;
  }
  if (days === 0) {
    return "今天到期";
  }
  return `${days} 天`;
}

interface OverdueTableProps {
  rows: ContractOverdueRow[];
  onOpenAttachments: (row: ContractOverdueRow) => void;
  showRank?: boolean;
  emptyText?: string;
}

export function OverdueTable({
  rows,
  onOpenAttachments,
  showRank = false,
  emptyText = "当前筛选条件下暂无付款期次"
}: OverdueTableProps) {
  if (rows.length === 0) {
    return <div className="empty-state">{emptyText}</div>;
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {showRank ? <th>排行</th> : null}
            <th>合同编码</th>
            <th>供应商</th>
            <th>采购员</th>
            <th>期次</th>
            <th>应付金额</th>
            <th>已付</th>
            <th>未付</th>
            <th>应付日期</th>
            <th>距今天数</th>
            <th>状态</th>
            <th>附件</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.contractId}-${row.source}-${row.payPeriod}-${row.dueDate}-${row.status}-${index}`}>
              {showRank ? <td className="rank-cell">{index + 1}</td> : null}
              <td>{row.contractCode || row.contractId || "—"}</td>
              <td>{row.supplier}</td>
              <td>{row.person}</td>
              <td>{row.payPeriod ?? "—"}</td>
              <td>{formatMoney(row.payTaxMoney)}</td>
              <td>{formatMoney(row.paidAmount)}</td>
              <td>{formatMoney(row.unpaidAmount)}</td>
              <td>{row.dueDate}</td>
              <td>{formatDays(row.daysUntilDue)}</td>
              <td>
                <span className={`status-pill status-${row.status}`}>{STATUS_LABEL[row.status]}</span>
              </td>
              <td>
                {row.attachments.length > 0 ? (
                  <button type="button" className="link-button" onClick={() => onOpenAttachments(row)}>
                    {row.attachments.length}
                  </button>
                ) : (
                  "—"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface AttachmentDrawerProps {
  open: boolean;
  title: string;
  attachments: ContractAttachment[];
  onClose: () => void;
}

export function AttachmentDrawer({ open, title, attachments, onClose }: AttachmentDrawerProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="drawer-backdrop" onClick={onClose} role="presentation">
      <aside className="drawer-panel" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
        <header className="drawer-header">
          <div>
            <span className="eyebrow">合同附件</span>
            <strong>{title}</strong>
          </div>
          <button type="button" className="link-button" onClick={onClose}>
            关闭
          </button>
        </header>
        <ul className="attachment-list">
          {attachments.map((item) => (
            <li key={`${item.type}-${item.fileId || item.url}`}>
              <div>
                <strong>{item.label}</strong>
                {item.fileId ? <small>文件 ID：{item.fileId}</small> : null}
              </div>
              {item.url ? (
                <a className="link-button" href={item.url} target="_blank" rel="noreferrer">
                  打开
                </a>
              ) : (
                <span className="muted">暂无直链</span>
              )}
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
