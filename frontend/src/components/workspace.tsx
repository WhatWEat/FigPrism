"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bookmark,
  Clock,
  Copy,
  Download,
  FolderPlus,
  History,
  Palette,
  Plus,
  Settings2,
  ShieldCheck,
  Trash2,
  Users,
  RefreshCw,
  Database,
  ArrowRight,
  Pencil,
  Check,
} from "lucide-react";
import { api, post, put, rgb } from "@/lib/api";
import { Board, Domain, Figure, User } from "@/lib/types";
import { useUI } from "@/lib/store";
import { Empty, ErrorMessage, Modal, Spinner, useUser } from "./ui";
import { FigureCard } from "./figure-card";
export function SignInGate({ title }: { title: string }) {
  return (
    <Empty
      title={title}
      description="登录后，这些灵感会保存在你的独立空间里。"
      action={
        <button className="button primary" onClick={useUI.getState().openLogin}>
          登录 FigPrism <ArrowRight size={16} />
        </button>
      }
    />
  );
}
export function Boards({ onIds }: { onIds: (ids: string[]) => void }) {
  const user = useUser().data?.user;
  const cache = useQueryClient();
  const ui = useUI();
  const [selected, setSelected] = useState("");
  const [create, setCreate] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [rename, setRename] = useState("");
  const boards = useQuery({
    queryKey: ["boards"],
    queryFn: () => api<Board[]>("/collections"),
    enabled: !!user,
  });
  const cid = selected || boards.data?.[0]?.id;
  const board = useQuery({
    queryKey: ["board", cid],
    queryFn: async () => {
      const b = await api<Board>(`/collections/${cid}`);
      onIds(b.items?.map((f) => f.id) || []);
      return b;
    },
    enabled: !!user && !!cid,
  });
  async function createBoard(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const b = await post<Board>("/collections", { name });
      setSelected(b.id);
      setName("");
      setCreate(false);
      cache.invalidateQueries({ queryKey: ["boards"] });
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    try {
      await api("/collections/" + deleteId, { method: "DELETE" });
      setDeleteId(null);
      setSelected("");
      cache.invalidateQueries({ queryKey: ["boards"] });
    } catch (e) {
      ui.notify((e as Error).message);
    }
  }
  if (!user) return <SignInGate title="让灵感，有处可归" />;
  return (
    <>
      <div className="workspace-heading">
        <div>
          <div className="eyebrow">YOUR CREATIVE SPACE</div>
          <h1>
            灵感看板<span>.</span>
          </h1>
          <p>收藏好构图，也记下让你眼前一亮的细节。</p>
        </div>
        <button className="button primary" onClick={() => setCreate(true)}>
          <Plus size={16} />
          新建看板
        </button>
      </div>
      <ErrorMessage error={boards.error} />
      <div className="boards-layout">
        <aside className="board-nav">
          <span className="subtle-label">
            我的看板 / {boards.data?.length || 0}
          </span>
          {boards.data?.map((b) => (
            <button
              className={cid === b.id ? "active" : ""}
              key={b.id}
              onClick={() => setSelected(b.id)}
            >
              <Bookmark size={16} />
              <span>{b.name}</span>
              <small>{b.count}</small>
            </button>
          ))}
        </aside>
        <section className="board-content">
          {board.isFetching && <Spinner />}
          {board.error && <ErrorMessage error={board.error} />}{" "}
          {board.data && (
            <>
              <div className="board-title">
                <h2>{board.data.name}</h2>
                <div>
                  <button
                    className="icon-button"
                    title="重命名看板"
                    onClick={() => {
                      setRename(board.data!.name);
                      setRenaming(true);
                    }}
                  >
                    <Pencil size={15} />
                  </button>
                  <a
                    className="button small"
                    href={`/api/collections/${cid}/export`}
                  >
                    <Download size={14} />
                    导出看板
                  </a>
                  <button
                    className="icon-button danger"
                    aria-label="删除看板"
                    onClick={() => setDeleteId(cid || null)}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
              {!board.data.items?.length ? (
                <Empty
                  title="第一张灵感，等你发现"
                  description="浏览图库，点击卡片上的收藏图标，或在检视器中添加笔记。"
                  action={
                    <a href="/" className="button">
                      探索图表 <ArrowRight size={15} />
                    </a>
                  }
                />
              ) : (
                <div className="masonry board-masonry">
                  {board.data.items.map((f) => (
                    <FigureCard
                      key={f.id}
                      figure={f}
                      onSelect={(id) => {
                        ui.select(id, {
                          focus: f.collection_item?.focused_subitem_id,
                          note: f.collection_item?.user_note,
                          boardId: cid,
                        });
                      }}
                    >
                      <BoardNote
                        figure={f}
                        cid={cid!}
                        refresh={() => {
                          cache.invalidateQueries({ queryKey: ["board", cid] });
                          cache.invalidateQueries({ queryKey: ["boards"] });
                        }}
                      />
                    </FigureCard>
                  ))}
                </div>
              )}
            </>
          )}
          {!cid && !boards.isPending && (
            <Empty
              title="创建你的第一个看板"
              description="按论文主题、绘图风格或配色方案组织灵感。"
            />
          )}
        </section>
      </div>
      <Modal open={create} onOpenChange={setCreate} title="新建灵感看板">
        <form className="form" onSubmit={createBoard}>
          <label>
            看板名称
            <input
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如：新论文 Fig.1 构图参考"
            />
          </label>
          <ErrorMessage error={error} />
          <button className="button primary" disabled={busy}>
            {busy ? <Spinner /> : <FolderPlus size={16} />}创建看板
          </button>
        </form>
      </Modal>
      <Modal
        open={!!deleteId}
        onOpenChange={(v) => {
          if (!v) setDeleteId(null);
        }}
        title="删除这个看板？"
        description="看板和其中的笔记会被删除，原始论文和图表仍保留在图库中。"
      >
        <div className="form">
          <button className="button danger" onClick={remove}>
            确认删除看板
          </button>
        </div>
      </Modal>
      <Modal open={renaming} onOpenChange={setRenaming} title="重命名看板">
        <form
          className="form"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await api(`/collections/${cid}`, {
                method: "PATCH",
                body: JSON.stringify({
                  name: rename,
                  description: board.data?.description || "",
                }),
              });
              setRenaming(false);
              cache.invalidateQueries({ queryKey: ["boards"] });
              cache.invalidateQueries({ queryKey: ["board", cid] });
            } catch (e) {
              ui.notify((e as Error).message);
            }
          }}
        >
          <label>
            看板名称
            <input
              required
              value={rename}
              onChange={(e) => setRename(e.target.value)}
              maxLength={100}
            />
          </label>
          <button className="button primary">保存</button>
        </form>
      </Modal>
    </>
  );
}
function BoardNote({
  figure: f,
  cid,
  refresh,
}: {
  figure: Figure;
  cid: string;
  refresh: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState(f.collection_item?.user_note || "");
  const ui = useUI();
  return (
    <div className="sticky-note">
      {f.collection_item?.focused_subitem_id && (
        <small>聚焦子图 ({f.collection_item.focused_subitem_id})</small>
      )}
      {editing ? (
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          aria-label="编辑灵感笔记"
        />
      ) : (
        <p>{note || "写下这张图带给你的灵感…"}</p>
      )}
      <div>
        <button
          className="text-button"
          onClick={async () => {
            if (editing) {
              try {
                await put(`/collections/${cid}/items`, {
                  figure_id: f.id,
                  user_note: note,
                  focused_subitem_id: f.collection_item?.focused_subitem_id,
                });
                refresh();
              } catch (e) {
                ui.notify((e as Error).message);
                return;
              }
            }
            setEditing(!editing);
          }}
        >
          {editing ? <Check size={12} /> : <Pencil size={12} />}{" "}
          {editing ? "保存" : "编辑笔记"}
        </button>
        <button
          className="icon-button"
          title="移出看板"
          onClick={async () => {
            try {
              await api(`/collections/${cid}/items/${f.id}`, {
                method: "DELETE",
              });
              refresh();
            } catch (e) {
              ui.notify((e as Error).message);
            }
          }}
        >
          <Trash2 size={12} />
        </button>
      </div>
    </div>
  );
}

type ColorRecord = {
  id: number;
  figure_id: string;
  hex_code: string;
  title: string;
  version_hash: string;
  created_at: string;
};
export function HistoryPage({ onIds }: { onIds: (ids: string[]) => void }) {
  const user = useUser().data?.user;
  const [tab, setTab] = useState("views");
  const ui = useUI();
  const views = useQuery({
    queryKey: ["history", "views"],
    queryFn: async () => {
      const rows = await api<Figure[]>("/me/history?kind=views");
      onIds(rows.map((f) => f.id));
      return rows;
    },
    enabled: !!user && tab === "views",
  });
  const colors = useQuery({
    queryKey: ["history", "colors"],
    queryFn: () => api<ColorRecord[]>("/me/history?kind=colors"),
    enabled: !!user && tab === "colors",
  });
  if (!user) return <SignInGate title="每一次灵感，都有迹可循" />;
  const groups: Record<string, Figure[]> = {};
  for (const f of views.data || []) {
    const days = Math.floor(
      (Date.now() - new Date(f.viewed_at + "Z").getTime()) / 86400000,
    );
    const key =
      days < 1 ? "今天" : days < 2 ? "昨天" : days < 7 ? "本周" : "更早";
    (groups[key] ??= []).push(f);
  }
  return (
    <>
      <div className="workspace-heading">
        <div>
          <div className="eyebrow">FOLLOW YOUR INSPIRATION</div>
          <h1>
            灵感足迹<span>.</span>
          </h1>
          <p>重访让你停下来的图表，找回随手拾起的颜色。</p>
        </div>
      </div>
      <div className="history-tabs tab-row">
        <button
          className={tab === "views" ? "active" : ""}
          onClick={() => setTab("views")}
        >
          <History size={16} />
          最近浏览
        </button>
        <button
          className={tab === "colors" ? "active" : ""}
          onClick={() => setTab("colors")}
        >
          <Palette size={16} />
          取色剪贴板
        </button>
      </div>
      <ErrorMessage error={tab === "views" ? views.error : colors.error} />
      {tab === "views" ? (
        Object.keys(groups).length ? (
          Object.entries(groups).map(([name, items]) => (
            <section className="history-group" key={name}>
              <h3>
                <Clock size={14} />
                {name}
                <span>{items.length}</span>
              </h3>
              <div className="masonry">
                {items.map((f) => (
                  <FigureCard key={f.id} figure={f} />
                ))}
              </div>
            </section>
          ))
        ) : (
          <Empty
            title="从一张图开始探索"
            description="你查看过的图表会出现在这里。"
          />
        )
      ) : colors.data?.length ? (
        <div className="color-history">
          {colors.data.map((c) => (
            <article key={c.id}>
              <button
                className="history-color"
                style={{ background: c.hex_code }}
                aria-label={`复制 ${c.hex_code}`}
                onClick={async () => {
                  await navigator.clipboard.writeText(c.hex_code);
                  ui.notify("已复制 " + c.hex_code);
                }}
              >
                <Copy size={18} />
              </button>
              <div>
                <code>{c.hex_code}</code>
                <small>rgb({rgb(c.hex_code).join(", ")})</small>
                <span>
                  {new Date(c.created_at + "Z").toLocaleDateString("zh-CN")}
                </span>
              </div>
              <button
                className="color-source"
                title={c.title}
                onClick={() => ui.select(c.figure_id)}
              >
                <img
                  src={`/api/assets/thumb/${c.figure_id}.webp?v=${c.version_hash}`}
                  alt={c.title}
                />
              </button>
            </article>
          ))}
        </div>
      ) : (
        <Empty
          title="你的第一抹颜色"
          description="点击图表色卡或使用吸管，颜色会自动保存在这里。"
        />
      )}
    </>
  );
}

type AdminInfo = {
  users: (User & { is_active: number })[];
  review_count: number;
  repairs: { id: string; figure_id: string; status: string }[];
  domains: Domain[];
  vision_driver: string;
  vision_model: string;
};
const stageLabels: Record<string, string> = {
  metadata: "元数据查询",
  download: "论文下载",
  papers: "论文处理",
  cpu: "PDF 计算",
  vision: "视觉判图",
  upload: "WebDAV 上传",
  figures: "在途图表",
};
export function AdminPage() {
  const user = useUser().data?.user;
  const ui = useUI();
  const cache = useQueryClient();
  const [invite, setInvite] = useState("");
  const [editor, setEditor] = useState("");
  const [domain, setDomain] = useState("all");
  const [limit, setLimit] = useState(5);
  const [busy, setBusy] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const result = useQuery({
    queryKey: ["admin"],
    queryFn: () => api<AdminInfo>("/admin/overview"),
    enabled: user?.role === "admin",
  });
  const stages = useQuery({
    queryKey: ["pipeline"],
    queryFn: () =>
      api<{ stages: Record<string, { limit: number; active: number }> }>(
        "/admin/pipeline",
      ),
    enabled: user?.role === "admin",
    refetchInterval: 3000,
  });
  if (!user) return <SignInGate title="系统控制中心" />;
  if (user.role !== "admin")
    return (
      <Empty
        title="需要管理员权限"
        description="你的账号可以浏览、收藏、添加论文和修正切图。"
      />
    );
  async function sync(kind: string) {
    setBusy(true);
    try {
      await post("/admin/sync", { kind, domain, limit });
      cache.invalidateQueries({ queryKey: ["jobs"] });
      ui.notify("任务已加入队列");
    } catch (e) {
      ui.notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="workspace-heading">
        <div>
          <div className="eyebrow">CONTROL ROOM</div>
          <h1>
            系统控制中心<span>.</span>
          </h1>
          <p>管理研究领域、内容流水线与团队访问权限。</p>
        </div>
        <span className="status-pill">
          <ShieldCheck size={14} />
          管理员
        </span>
      </div>
      <ErrorMessage error={result.error} />
      {result.data && (
        <div className="admin-grid">
          <section className="admin-card">
            <h2>
              <RefreshCw size={18} />
              内容流水线
            </h2>
            <p>
              增量同步 HF 高热论文与 arXiv 顶会论文，或回溯 2025–2026 代表作。
            </p>
            {stages.data && (
              <div className="domain-list" aria-label="阶段并发状态">
                {Object.entries(stages.data.stages).map(([key, value]) => (
                  <div key={key}>
                    <strong>{stageLabels[key] || key}</strong>
                    <span>
                      运行 {value.active} / 上限 {value.limit}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <div className="form">
              <label>
                目标领域
                <select
                  value={domain}
                  onChange={(e) => setDomain(e.target.value)}
                >
                  <option value="all">全部激活领域</option>
                  {result.data.domains.map((d) => (
                    <option key={d.slug} value={d.slug}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                每个领域最多论文数
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={limit}
                  onChange={(e) => setLimit(Number(e.target.value))}
                />
              </label>
              <div className="button-row">
                <button
                  className="button primary"
                  disabled={busy}
                  onClick={() => sync("sync")}
                >
                  <RefreshCw size={15} />
                  增量同步
                </button>
                <button
                  className="button"
                  disabled={busy}
                  onClick={() => sync("backfill")}
                >
                  代表作冷启动
                </button>
              </div>
              <button
                className="button"
                disabled={busy}
                onClick={() => sync("rebuild")}
              >
                <Database size={15} />从 WebDAV 恢复索引
              </button>
            </div>
          </section>
          <section className="admin-card">
            <h2>
              <Settings2 size={18} />
              研究领域与视觉判图
            </h2>
            <div className="domain-list">
              {result.data.domains.map((d) => (
                <div key={d.slug}>
                  <i style={{ background: d.color_dot }} />
                  <strong>{d.name}</strong>
                  <span>{d.phrases.length} 短语</span>
                  <small>{d.is_active ? "已启用" : "已停用"}</small>
                </div>
              ))}
            </div>
            <button
              className="button"
              onClick={() => {
                setEditor(JSON.stringify(result.data!.domains, null, 2));
                setEditOpen(true);
              }}
            >
              编辑领域配置
            </button>
            <div className="admin-detail">
              <span>视觉引擎</span>
              <code>{result.data.vision_driver}</code>
              <span>配置模型</span>
              <code>{result.data.vision_model}</code>
              <span>待复核图表</span>
              <strong>{result.data.review_count}</strong>
            </div>
          </section>
          <section className="admin-card">
            <h2>
              <Users size={18} />
              账号与邀请
            </h2>
            <p>默认关闭公开注册，邀请链接 7 天内有效且仅可使用一次。</p>
            <button
              className="button primary"
              onClick={async () => {
                try {
                  setInvite(
                    (await post<{ url: string }>("/admin/invites")).url,
                  );
                } catch (e) {
                  ui.notify((e as Error).message);
                }
              }}
            >
              <Plus size={15} />
              生成邀请链接
            </button>
            {invite && (
              <div className="invite-box">
                <input readOnly value={invite} />
                <button
                  className="icon-button"
                  title="复制邀请链接"
                  onClick={() => {
                    navigator.clipboard.writeText(invite);
                    ui.notify("邀请链接已复制");
                  }}
                >
                  <Copy size={16} />
                </button>
              </div>
            )}
            <div className="user-list">
              {result.data.users.map((u) => (
                <div key={u.id}>
                  <span className="avatar">{u.username[0].toUpperCase()}</span>
                  <strong>{u.username}</strong>
                  <small>{u.role}</small>
                  {u.id !== user.id && (
                    <button
                      className="text-button"
                      onClick={async () => {
                        try {
                          await api(`/admin/users/${u.id}`, {
                            method: "PATCH",
                            body: JSON.stringify({ is_active: !u.is_active }),
                          });
                          cache.invalidateQueries({ queryKey: ["admin"] });
                        } catch (e) {
                          ui.notify((e as Error).message);
                        }
                      }}
                    >
                      {u.is_active ? "停用" : "启用"}
                    </button>
                  )}
                </div>
              ))}
            </div>
          </section>
          <section className="admin-card">
            <h2>
              <Pencil size={18} />
              精修任务队列
            </h2>
            <p>
              精修请求由 Codex CLI 领取处理。手动重切成功后会自动完成对应请求。
            </p>
            {result.data.repairs.length ? (
              result.data.repairs.map((r) => (
                <button
                  className="repair-row"
                  key={r.id}
                  onClick={() => ui.select(r.figure_id)}
                >
                  <span>图表 {r.figure_id.slice(0, 8)}</span>
                  <span>{r.status === "pending" ? "待处理" : "已完成"}</span>
                  <ArrowRight size={14} />
                </button>
              ))
            ) : (
              <div className="admin-empty">暂时没有精修请求</div>
            )}
          </section>
        </div>
      )}
      <Modal
        open={editOpen}
        onOpenChange={setEditOpen}
        title="编辑领域词库"
        description="JSON 配置会同步保存至 domains.yaml。支持新增领域、调整召回词和细分标签。"
        className="config-modal"
      >
        <form
          className="form"
          onSubmit={async (e) => {
            e.preventDefault();
            setError(null);
            try {
              const value = JSON.parse(editor);
              await put("/admin/domains", value);
              cache.invalidateQueries({ queryKey: ["admin"] });
              cache.invalidateQueries({ queryKey: ["domains"] });
              setEditOpen(false);
              ui.notify("领域配置已保存");
            } catch (e) {
              setError(e as Error);
            }
          }}
        >
          <textarea
            className="config-editor"
            value={editor}
            onChange={(e) => setEditor(e.target.value)}
            aria-label="领域 JSON 配置"
            spellCheck={false}
          />
          <ErrorMessage error={error} />
          <button className="button primary">保存领域配置</button>
        </form>
      </Modal>
    </>
  );
}
