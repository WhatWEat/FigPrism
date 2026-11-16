"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Database, RefreshCw } from "lucide-react";
import { api, post } from "@/lib/api";
import { ErrorMessage, Spinner } from "./ui";

type Insights = {
  cache: {
    hits: number;
    misses: number;
    coalesced: number;
    requests: number;
    hit_rate: number | null;
    started_at: string;
  };
  scan: {
    status: string;
    completed_at: string | null;
    started_at: string | null;
    error: string;
    directories: number;
    files: number;
  };
  resources: {
    remote_bytes: number | null;
    remote_files: number | null;
    local_bytes: number;
    local_only_bytes: number | null;
    total_bytes: number | null;
    total_files: number | null;
  };
};
const bytes = (value: number | null) =>
  value === null
    ? "—"
    : new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(
        value /
          (value >= 1e9 ? 1e9 : value >= 1e6 ? 1e6 : value >= 1e3 ? 1e3 : 1),
      ) +
      " " +
      (value >= 1e9 ? "GB" : value >= 1e6 ? "MB" : value >= 1e3 ? "KB" : "B");
const when = (value: string) =>
  new Date(value.replace(" ", "T") + "Z").toLocaleString("zh-CN");
export function ResourceInsights() {
  const result = useQuery({
    queryKey: ["resource-insights"],
    queryFn: () => api<Insights>("/admin/storage/insights"),
    refetchInterval: 5000,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const data = result.data;
  return (
    <section className="admin-card cache-panel" aria-label="缓存命中与资源统计">
      <div className="cache-heading">
        <h2>
          <Database size={18} />
          缓存命中与资源
        </h2>
        <button
          className="button small"
          disabled={busy || data?.scan.status === "running"}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await post("/admin/storage/scan");
              await result.refetch();
            } catch (e) {
              setError(e as Error);
            } finally {
              setBusy(false);
            }
          }}
        >
          <RefreshCw size={14} />
          刷新 WebDAV 盘点
        </button>
      </div>
      <ErrorMessage error={result.error || error} />
      {data ? (
        <>
          <div className="admin-metrics resource-metrics">
            <div className="admin-metric">
              <span>本地缓存命中率</span>
              <strong>
                {data.cache.hit_rate === null
                  ? "暂无请求"
                  : (data.cache.hit_rate * 100).toFixed(1) + "%"}
              </strong>
              <small>
                {data.cache.hits.toLocaleString()} 次命中 /{" "}
                {data.cache.requests.toLocaleString()} 次请求
              </small>
            </div>
            <div className="admin-metric">
              <span>资源总量（路径去重）</span>
              <strong>{bytes(data.resources.total_bytes)}</strong>
              <small>
                {data.resources.total_files === null
                  ? "等待首次完整盘点"
                  : `${data.resources.total_files.toLocaleString()} 个资源文件`}
              </small>
            </div>
            <div className="admin-metric">
              <span>WebDAV 文件大小</span>
              <strong>{bytes(data.resources.remote_bytes)}</strong>
              <small>
                {data.resources.remote_files === null
                  ? "尚无完整快照"
                  : `${data.resources.remote_files.toLocaleString()} 个远端文件`}
              </small>
            </div>
            <div className="admin-metric">
              <span>本地缓存实际占用</span>
              <strong>{bytes(data.resources.local_bytes)}</strong>
              <small>含本地已有的远端副本</small>
            </div>
          </div>
          <p className="cache-note">
            命中 {data.cache.hits.toLocaleString()} · 回源{" "}
            {data.cache.misses.toLocaleString()} · 合并等待{" "}
            {data.cache.coalesced.toLocaleString()}。自{" "}
            {when(data.cache.started_at)} 起统计到达服务端的图表请求，浏览器与
            CDN 直接命中不计入。
          </p>
          <p className="cache-note">
            资源总量包含论文、图表与元数据；本地和 WebDAV
            的同路径资源只计一次。WebDAV 为最近一次完整盘点快照。
          </p>
          {data.scan.status === "running" && (
            <p className="cache-loading" role="status">
              <Spinner />
              正在盘点 WebDAV · 已扫描 {data.scan.directories} 个目录、
              {data.scan.files} 个文件
            </p>
          )}
          {data.scan.error && (
            <p className="error-box" role="alert">
              {data.scan.error}
              {data.scan.completed_at ? "，当前展示上次成功盘点结果。" : ""}
            </p>
          )}
          {data.scan.completed_at && (
            <p className="cache-note">
              上次完整盘点：{when(data.scan.completed_at)}
            </p>
          )}
        </>
      ) : result.isPending ? (
        <p className="cache-loading">
          <Spinner />
          正在读取统计…
        </p>
      ) : null}
    </section>
  );
}
