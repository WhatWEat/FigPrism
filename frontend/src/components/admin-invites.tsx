"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Copy, Plus } from "lucide-react";
import { api, post } from "@/lib/api";
import { useUI } from "@/lib/store";
import { ErrorMessage, Spinner } from "./ui";

type Invite = {
  code: string;
  url: string;
  max_uses: number;
  used_count: number;
  remaining_uses: number;
  expires_at: string;
  status: "active" | "expired" | "exhausted";
};
export function AdminInvites() {
  const ui = useUI();
  const [uses, setUses] = useState("1");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<Invite | null>(null);
  const result = useQuery({
    queryKey: ["admin-invites"],
    queryFn: () => api<{ items: Invite[] }>("/admin/invites"),
    refetchInterval: 5000,
  });
  const count = Number(uses);
  const valid = Number.isInteger(count) && count >= 1 && count <= 1000;
  const items = result.data?.items || [];
  const invites =
    created && !items.some((item) => item.code === created.code)
      ? [created, ...items]
      : items;
  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      ui.notify("邀请链接已复制");
    } catch {
      ui.notify("请手动复制邀请链接");
    }
  }
  return (
    <section className="admin-invites" aria-label="邀请链接管理">
      <div className="invite-create">
        <label>
          可使用次数
          <input
            aria-label="可使用次数"
            type="number"
            min="1"
            max="1000"
            step="1"
            value={uses}
            onChange={(event) => setUses(event.target.value)}
          />
        </label>
        <button
          className="button primary"
          disabled={busy || !valid}
          onClick={async () => {
            setBusy(true);
            try {
              const invite = await post<Invite>("/admin/invites", {
                max_uses: count,
              });
              setCreated(invite);
              await result.refetch();
            } catch (error) {
              ui.notify((error as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? <Spinner /> : <Plus size={15} />}生成邀请链接
        </button>
      </div>
      <p className="cache-note">
        每个链接 7 天内有效，可供指定人数成功注册；注册失败不消耗次数。默认 1
        次，最多 1000 次。
      </p>
      {!valid && (
        <p className="error-box" role="alert">
          请输入 1–1000 之间的整数。
        </p>
      )}
      <ErrorMessage error={result.error} retry={() => result.refetch()} />
      {result.isPending && !created ? (
        <p className="cache-loading">
          <Spinner />
          正在读取邀请…
        </p>
      ) : invites.length ? (
        <div className="invite-list">
          {invites.map((item) => (
            <div className="invite-entry" key={item.code}>
              <div className="invite-entry-heading">
                <strong>
                  已用 {item.used_count} / {item.max_uses} 次 · 剩余{" "}
                  {item.remaining_uses} 次
                </strong>
                <span>
                  {item.status === "active"
                    ? "可使用"
                    : item.status === "expired"
                      ? "已过期"
                      : "已用完"}
                </span>
              </div>
              <div className="invite-box">
                <input aria-label="邀请链接" readOnly value={item.url} />
                <button
                  className="icon-button"
                  aria-label="复制邀请链接"
                  onClick={() => copy(item.url)}
                >
                  <Copy size={16} />
                </button>
              </div>
              <small>
                有效期至{" "}
                {new Date(
                  item.expires_at.replace(" ", "T") + "Z",
                ).toLocaleString("zh-CN")}
              </small>
            </div>
          ))}
        </div>
      ) : !result.error ? (
        <p className="cache-note">暂无邀请链接。</p>
      ) : null}
      {invites.length > 0 && (
        <p className="cache-note">最近 20 条邀请 · 每 5 秒更新使用次数</p>
      )}
    </section>
  );
}
