import * as echarts from "echarts";
import { useEffect, useRef } from "react";

type ChartKind = "bar" | "horizontalBar" | "stackedBar";

interface SeriesItem {
  name: string;
  values: number[];
}

interface ExecutionChartProps {
  title: string;
  categories: string[];
  series: SeriesItem[];
  kind?: ChartKind;
  valueLabel?: string;
}

export function ExecutionChart({ title, categories, series, kind = "bar", valueLabel = "" }: ExecutionChartProps) {
  const chartRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!chartRef.current) {
      return;
    }
    const chart = echarts.init(chartRef.current);
    const isHorizontal = kind === "horizontalBar";
    const option = {
      title: { text: title, left: 8, top: 4, textStyle: { fontSize: 15 } },
      tooltip: { trigger: "axis" },
      grid: { left: isHorizontal ? 132 : 48, right: 32, top: 56, bottom: 42 },
      legend: series.length > 1 ? { top: 28 } : undefined,
      xAxis: {
        type: isHorizontal ? "value" : "category",
        data: isHorizontal ? undefined : categories,
        axisLabel: { color: "#5f6b7a", overflow: "truncate", width: isHorizontal ? 120 : undefined }
      },
      yAxis: {
        type: isHorizontal ? "category" : "value",
        data: isHorizontal ? categories : undefined,
        axisLabel: { color: "#5f6b7a" }
      },
      series: series.map((item) => ({
        name: item.name,
        type: "bar",
        stack: kind === "stackedBar" ? "total" : undefined,
        barMaxWidth: 34,
        data: item.values,
        label: {
          show: kind !== "stackedBar",
          position: isHorizontal ? "right" : "top",
          formatter: `{c}${valueLabel}`
        }
      }))
    };
    chart.setOption(option);

    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [categories, kind, series, title, valueLabel]);

  return <div className="chart" ref={chartRef} />;
}
