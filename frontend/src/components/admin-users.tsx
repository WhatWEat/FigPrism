"use client";
import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { api } from "@/lib/api";
import { Figure, User } from "@/lib/types";
import { useUI } from "@/lib/store";
import { Empty, ErrorMessage, Modal, Spinner, useUser } from "./ui";
import { SignInGate } from "./workspace";
import { AdminInvites } from "./admin-invites";

type Account = User & {
  is_active: number;
  created_at: string;
  last_viewed_at: string | null;
  board_count: number;
  item_count: number;
  figure_count: number;
  paper_count: number;
};
type UserList = {
  users: Account[];
  summary: {
    users: number;
    active_users: number;
    boards: number;
    items: number;
    figures: number;
  };
};
type Detail = {
  user: Account;
  boards: { id: string; name: string; count: number }[];
  items: (Figure & {
    item_id: string;
    collection_id: string;
    collection_name: string;
    saved_at: string;
  })[];
  total: number;
  next_offset: number | null;
};
const when = (value: string | null) =>
  value
    ? new Date(value.replace(" ", "T") + "Z").toLocaleString("zh-CN")
    : "暂无记录";

export function AdminUsers() {
  const user = useUser().data?.user;
  const ui = useUI();
  const cache = useQueryClient();
  const [selected, setSelected] = useState<number | null>(null);
  const result = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => api<UserList>("/admin/users"),
    enabled: user?.role === "admin",
  });
  if (!user) return <SignInGate title="用户管理" />;
  if (user.role !== "admin")
    return (
      <Empty
        title="需要管理员权限"
        description="仅管理员可查看账号与收藏统计。"
      />
    );
  return (
    <>
      <div className="workspace-heading">
        <div>
          <div className="eyebrow">PEOPLE & COLLECTIONS</div>
          <h1>
            用户管理<span>.</span>
          </h1>
          <p>管理账号与邀请，查看用户收藏概况。</p>
        </div>
        <Link className="button" href="/admin">
          系统控制中心
        </Link>
      </div>
      <ErrorMessage error={result.error} retry={() => result.refetch()} />
      {result.isPending ? (
        <div className="cache-loading">
          <Spinner />
          正在读取用户…
        </div>
      ) : (
        result.data && (
          <>
            <div className="admin-metrics" aria-label="用户总体统计">
              <Metric label="账号总数" value={result.data.summary.users} />
              <Metric
                label="启用账号"
                value={result.data.summary.active_users}
              />
              <Metric label="收藏条目" value={result.data.summary.items} />
              <Metric
                label="收藏图表（按用户去重）"
                value={result.data.summary.figures}
              />
            </div>
            <section className="admin-card">
              <div className="cache-heading">
                <h2>
                  <Users size={18} />
                  账号与邀请
                </h2>
              </div>
              <AdminInvites />
              <p>收藏图表按每个用户跨看板去重统计。</p>
              <div className="managed-users">
                {result.data.users.map((account) => (
                  <div className="managed-user" key={account.id}>
                    <button
                      className="user-detail-trigger"
                      onClick={() => setSelected(account.id)}
                      aria-label={`查看 ${account.username} 的详情`}
                    >
                      <span className="avatar">
                        {account.username[0].toUpperCase()}
                      </span>
                      <span>
                        <strong>{account.username}</strong>
                        <small>
                          {account.role === "admin" ? "管理员" : "成员"} ·{" "}
                          {account.is_active ? "已启用" : "已停用"}
                        </small>
                      </span>
                    </button>
                    <span>
                      {account.figure_count} 张图 · {account.board_count} 个看板
                    </span>
                    <button
                      className="button small"
                      onClick={() => setSelected(account.id)}
                    >
                      详情
                    </button>
                    {account.id !== user.id && (
                      <button
                        className="text-button"
                        onClick={async () => {
                          try {
                            await api(`/admin/users/${account.id}`, {
                              method: "PATCH",
                              body: JSON.stringify({
                                is_active: !account.is_active,
                              }),
                            });
                            cache.invalidateQueries({
                              queryKey: ["admin-users"],
                            });
                            cache.invalidateQueries({
                              queryKey: ["admin-user"],
                            });
                          } catch (e) {
                            ui.notify((e as Error).message);
                          }
                        }}
                      >
                        {account.is_active ? "停用" : "启用"}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </section>
          </>
        )
      )}
      <Modal
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
        title="用户详情"
        className="admin-user-modal"
      >
        {selected !== null && <UserDetails key={selected} id={selected} />}
      </Modal>
    </>
  );
}
export function Metric({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="admin-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
function UserDetails({ id }: { id: number }) {
  const [board, setBoard] = useState("");
  const [offset, setOffset] = useState(0);
  const result = useQuery({
    queryKey: ["admin-user", id, board, offset],
    queryFn: () =>
      api<Detail>(
        `/admin/users/${id}?offset=${offset}&limit=24${board ? "&collection_id=" + encodeURIComponent(board) : ""}`,
      ),
  });
  if (result.isPending)
    return (
      <div className="detail-loading">
        <Spinner />
        正在读取用户详情…
      </div>
    );
  if (result.error)
    return <ErrorMessage error={result.error} retry={() => result.refetch()} />;
  const data = result.data;
  return (
    <div className="admin-user-detail">
      <div className="user-detail-heading">
        <h2>{data.user.username}</h2>
        <p>
          {data.user.role === "admin" ? "管理员" : "成员"} ·{" "}
          {data.user.is_active ? "已启用" : "已停用"}
        </p>
        <p>
          注册时间：{when(data.user.created_at)}
          <br />
          最近浏览：{when(data.user.last_viewed_at)}
        </p>
      </div>
      <div className="admin-metrics">
        <Metric label="看板" value={data.user.board_count} />
        <Metric label="收藏条目" value={data.user.item_count} />
        <Metric label="去重图表" value={data.user.figure_count} />
        <Metric label="去重论文" value={data.user.paper_count} />
      </div>
      <div className="user-collection-heading">
        <h3>收藏内容 · {data.total} 条</h3>
        <select
          aria-label="筛选用户看板"
          value={board}
          onChange={(e) => {
            setBoard(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">全部看板</option>
          {data.boards.map((item) => (
            <option value={item.id} key={item.id}>
              {item.name}（{item.count}）
            </option>
          ))}
        </select>
      </div>
      {data.items.length ? (
        <div className="admin-favorites">
          {data.items.map((item) => (
            <article key={item.item_id}>
              <a
                href={item.hd_url}
                target="_blank"
                rel="noreferrer"
                aria-label={`查看收藏图 ${item.fig_label} ${item.title}`}
              >
                <img
                  className="fig-paper-blend"
                  src={item.thumb_url}
                  alt={item.caption || item.fig_label}
                  loading="lazy"
                />
              </a>
              <div>
                <strong>{item.title}</strong>
                <p>
                  {item.fig_label} · {item.collection_name}
                </p>
                <small>收藏于 {when(item.saved_at)}</small>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <Empty
          title="还没有收藏"
          description="该用户或所选看板暂无收藏图表。"
        />
      )}
      <div className="admin-pagination">
        <button
          className="button small"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 24))}
        >
          上一页
        </button>
        <span>第 {Math.floor(offset / 24) + 1} 页</span>
        <button
          className="button small"
          disabled={data.next_offset === null}
          onClick={() => setOffset(data.next_offset!)}
        >
          下一页
        </button>
      </div>
    </div>
  );
}
