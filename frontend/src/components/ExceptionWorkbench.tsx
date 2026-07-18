import { useCallback, useEffect, useState } from "react";

import { fetchExceptionDetail, fetchGroupedExceptions } from "../services/api";
import type { ExceptionGroup, GroupedExceptions } from "../payroll/types";

interface ExceptionWorkbenchProps {
  month: string;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  onViewEvidence?: (userid: string, field: string) => void;
}

const PAGE_SIZE = 20;

export function ExceptionWorkbench({
  month,
  collapsed = true,
  onToggleCollapsed,
  onViewEvidence
}: ExceptionWorkbenchProps) {
  const [data, setData] = useState<GroupedExceptions | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeCode, setActiveCode] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [detailItems, setDetailItems] = useState<ExceptionGroup["items"]>([]);
  const [detailTotal, setDetailTotal] = useState(0);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    let ignore = false;
    setLoading(true);
    fetchGroupedExceptions(month)
      .then((result) => {
        if (!ignore) {
          setData(result);
          setActiveCode(null);
          setOffset(0);
          setDetailItems([]);
        }
      })
      .catch(() => {
        if (!ignore) {
          setData(null);
        }
      })
      .finally(() => {
        if (!ignore) {
          setLoading(false);
        }
      });
    return () => {
      ignore = true;
    };
  }, [month]);

  const loadDetail = useCallback(
    async (code: string, nextOffset: number, keyword: string) => {
      setDetailLoading(true);
      try {
        const result = await fetchExceptionDetail(month, {
          code,
          offset: nextOffset,
          limit: PAGE_SIZE,
          search: keyword
        });
        setDetailItems(result.items ?? []);
        setDetailTotal(result.totalCount ?? 0);
        setOffset(nextOffset);
      } finally {
        setDetailLoading(false);
      }
    },
    [month]
  );

  function openGroup(group: ExceptionGroup) {
    setActiveCode(group.code);
    setSearch("");
    setOffset(0);
    void loadDetail(group.code, 0, "");
  }

  function handleSearchSubmit() {
    if (!activeCode) {
      return;
    }
    void loadDetail(activeCode, 0, search);
  }

  const total = data?.summary.total ?? 0;
  const groupCount = data?.summary.groupCount ?? 0;
  const groups = data?.groups ?? [];
  const totalPages = Math.max(1, Math.ceil(detailTotal / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const activeGroup = groups.find((group) => group.code === activeCode);

  if (loading) {
    return (
      <section className="exception-workbench">
        <p className="payroll-evidence-empty">异常数据加载中…</p>
      </section>
    );
  }

  if (total === 0) {
    return null;
  }

  return (
    <section className={`exception-workbench ${collapsed ? "collapsed" : "expanded"}`}>
      <div className="exception-workbench-header">
        <div>
          <span>异常工作台</span>
          <strong>
            {total} 项 · {groupCount} 类
          </strong>
        </div>
        <button type="button" className="payroll-advanced-toggle" onClick={onToggleCollapsed}>
          {collapsed ? "展开" : "收起"}
        </button>
      </div>

      {!collapsed ? (
        <>
          <div className="exception-chip-row">
            {groups.map((group) => (
              <button
                key={group.code}
                type="button"
                className={
                  activeCode === group.code ? "exception-chip active" : "exception-chip"
                }
                onClick={() => openGroup(group)}
              >
                <strong>{group.label}</strong>
                <span>{group.count} 人</span>
              </button>
            ))}
          </div>

          {activeCode && activeGroup ? (
            <div className="exception-detail-panel">
              <div className="exception-detail-toolbar">
                <div>
                  <strong>{activeGroup.label}</strong>
                  <span>{detailTotal} 人</span>
                  <p>{activeGroup.explanation}</p>
                </div>
                <div className="exception-search-row">
                  <input
                    type="search"
                    placeholder="搜索姓名或 userid"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        handleSearchSubmit();
                      }
                    }}
                  />
                  <button type="button" className="payroll-advanced-toggle" onClick={handleSearchSubmit}>
                    搜索
                  </button>
                </div>
              </div>

              {detailLoading ? (
                <p className="payroll-evidence-empty">加载明细…</p>
              ) : (
                <div className="exception-table-wrap">
                  <table className="exception-table">
                    <thead>
                      <tr>
                        <th>姓名</th>
                        <th>部门</th>
                        <th>说明</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detailItems.map((item) => (
                        <tr key={item.exceptionId ?? `${item.userid}-${item.name}`}>
                          <td>{item.name || item.userid}</td>
                          <td>{item.deptName || "—"}</td>
                          <td>{item.message || "—"}</td>
                          <td>
                            {item.userid && onViewEvidence ? (
                              <button
                                type="button"
                                className="payroll-advanced-toggle"
                                onClick={() =>
                                  onViewEvidence(
                                    item.userid!,
                                    activeGroup.field || "标准月薪"
                                  )
                                }
                              >
                                查看依据
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
              )}

              <div className="exception-pagination">
                <button
                  type="button"
                  className="payroll-advanced-toggle"
                  disabled={offset <= 0}
                  onClick={() => void loadDetail(activeCode, Math.max(0, offset - PAGE_SIZE), search)}
                >
                  上一页
                </button>
                <span>
                  {currentPage} / {totalPages}
                </span>
                <button
                  type="button"
                  className="payroll-advanced-toggle"
                  disabled={offset + PAGE_SIZE >= detailTotal}
                  onClick={() => void loadDetail(activeCode, offset + PAGE_SIZE, search)}
                >
                  下一页
                </button>
              </div>
            </div>
          ) : (
            <p className="payroll-evidence-empty">点击上方汇总卡查看明细</p>
          )}
        </>
      ) : (
        <div className="exception-chip-row compact">
          {groups.slice(0, 4).map((group) => (
            <button
              key={group.code}
              type="button"
              className="exception-chip"
              onClick={() => {
                onToggleCollapsed?.();
                openGroup(group);
              }}
            >
              <strong>{group.label}</strong>
              <span>{group.count}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
