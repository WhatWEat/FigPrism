"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
import {
  QueryClient,
  QueryClientProvider,
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Bookmark,
  Check,
  ChevronDown,
  ChevronUp,
  Columns3,
  Command,
  Filter,
  History,
  LayoutGrid,
  LogOut,
  Plus,
  Search,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  Triangle,
  X,
} from "lucide-react";
import { api, post } from "@/lib/api";
import {
  Board,
  Domain,
  FigurePage,
  Job,
  archetypes,
  archetypeNames,
} from "@/lib/types";
import { useUI } from "@/lib/store";
import { Logo, Empty, ErrorMessage, Spinner, useUser } from "./ui";
import { FigureCard } from "./figure-card";
import { AuthModal, IngestModal } from "./auth-ingest";
import { Inspector } from "./inspector";
import { Boards, HistoryPage, AdminPage } from "./workspace";
export type Page = "gallery" | "collections" | "history" | "admin";
export default function GalleryApp({ page = "gallery" }: { page?: Page }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <Shell page={page} />
    </QueryClientProvider>
  );
}
function Shell({ page }: { page: Page }) {
  const ui = useUI();
  const cache = useQueryClient();
  const { data: auth } = useUser();
  const user = auth?.user;
  const [query, setQuery] = useState("");
  const [ids, setIds] = useState<string[]>([]);
  const [menu, setMenu] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const [newCount, setNewCount] = useState(0);
  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);
  useEffect(() => {
    const stream = new EventSource("/api/stream/events");
    const created = () => setNewCount((n) => n + 1);
    const updated = () => {
      cache.invalidateQueries({ queryKey: ["figure"] });
      cache.invalidateQueries({ queryKey: ["figures"] });
    };
    stream.addEventListener("figure.created", created);
    stream.addEventListener("figure.updated", updated);
    stream.addEventListener("library.rebuilt", updated);
    return () => stream.close();
  }, [cache]);
  useEffect(() => {
    const density = Number(localStorage.getItem("figprism-density"));
    if ([3, 4, 5].includes(density)) ui.setDensity(density);
  }, []);
  const changeIds = useCallback((value: string[]) => setIds(value), []);
  return (
    <>
      <header className="site-header">
        <Link href="/" className="brand-link" aria-label="FigPrism 首页">
          <Logo />
        </Link>
        <div className="global-search">
          <Search size={16} />
          <input
            ref={searchRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索图表、论文、方法名…"
            aria-label="搜索图表"
            onKeyDown={(e) => {
              if (e.key === "Enter" && page !== "gallery")
                window.location.href = "/?q=" + encodeURIComponent(query);
            }}
          />
          <kbd>⌘ K</kbd>
          {query && (
            <button
              className="clear-search"
              onClick={() => setQuery("")}
              aria-label="清空搜索"
            >
              <X size={12} />
            </button>
          )}
        </div>
        <nav className="primary-nav" aria-label="主导航">
          <Link className={page === "gallery" ? "active" : ""} href="/">
            <LayoutGrid size={15} />
            探索
          </Link>
          <Link
            className={page === "collections" ? "active" : ""}
            href="/collections"
          >
            <Bookmark size={15} />
            看板
          </Link>
          <Link className={page === "history" ? "active" : ""} href="/history">
            <History size={15} />
            足迹
          </Link>
        </nav>
        <div className="account-actions">
          {user ? (
            <>
              <button className="button primary small" onClick={ui.openIngest}>
                <Plus size={15} />
                <span>添加论文</span>
              </button>
              <div className="account-menu">
                <button
                  className="avatar"
                  onClick={() => setMenu(!menu)}
                  aria-label="账号菜单"
                  aria-expanded={menu}
                >
                  {user.username[0].toUpperCase()}
                </button>
                {menu && (
                  <>
                    <button
                      className="menu-dismiss"
                      onClick={() => setMenu(false)}
                      aria-label="关闭账号菜单"
                    />
                    <div className="dropdown">
                      <strong>{user.username}</strong>
                      <span className="subtle-label">浏览密度</span>
                      <div className="density-controls">
                        {[3, 4, 5].map((n) => (
                          <button
                            key={n}
                            className={ui.density === n ? "active" : ""}
                            onClick={() => {
                              ui.setDensity(n);
                              localStorage.setItem(
                                "figprism-density",
                                String(n),
                              );
                            }}
                          >
                            {n} 列
                          </button>
                        ))}
                      </div>
                      {user.role === "admin" && (
                        <Link href="/admin">
                          <Settings2 size={14} />
                          系统控制中心
                        </Link>
                      )}
                      <button
                        onClick={async () => {
                          await post("/auth/logout");
                          cache.clear();
                          setMenu(false);
                          ui.notify("已退出登录");
                        }}
                      >
                        <LogOut size={14} />
                        退出登录
                      </button>
                    </div>
                  </>
                )}
              </div>
            </>
          ) : (
            <>
              <span className="guest-label">
                <span />
                访客只读
              </span>
              <button className="button small" onClick={ui.openLogin}>
                登录 <ArrowUpRight size={13} />
              </button>
            </>
          )}
        </div>
      </header>
      <main
        className={`main-container ${page === "gallery" ? "gallery-page" : ""}`}
      >
        {page === "gallery" ? (
          <Gallery
            query={query}
            setQuery={setQuery}
            onIds={changeIds}
            newCount={newCount}
            resetNew={() => setNewCount(0)}
          />
        ) : page === "collections" ? (
          <Boards onIds={changeIds} />
        ) : page === "history" ? (
          <HistoryPage onIds={changeIds} />
        ) : (
          <AdminPage />
        )}
      </main>
      <footer className="site-footer">
        <Logo />
        <span>好研究，也值得被好好画出来。</span>
        <span className="footer-meta">
          FIGURE-FIRST RESEARCH LIBRARY <i /> {new Date().getFullYear()}
        </span>
      </footer>
      <AuthModal />
      <IngestModal />
      <Inspector ids={ids} />
      <JobToast />
      {ui.toast && (
        <div className="toast" role="status">
          <Check size={16} />
          {ui.toast}
        </div>
      )}
    </>
  );
}
const hues = [
  "#d87575",
  "#d69b6d",
  "#c7b56e",
  "#a0b776",
  "#73b395",
  "#74b3b0",
  "#7babc7",
  "#7f98c8",
  "#8b85c0",
  "#aa81bd",
  "#be81ac",
  "#c78192",
];
const hueNames = [
  "红色",
  "橙色",
  "琥珀",
  "黄绿",
  "翠绿",
  "青绿",
  "青蓝",
  "天蓝",
  "钴蓝",
  "靛紫",
  "品红",
  "玫红",
];
const emptyFilters = {
  domain: "",
  venue: "",
  layout: "",
  span: "",
  archetype: "",
  color: "",
  honors: false,
  show_cases: false,
  sub_tags: [] as string[],
  tag_mode: "any",
};
function Gallery({
  query,
  setQuery,
  onIds,
  newCount,
  resetNew,
}: {
  query: string;
  setQuery: (q: string) => void;
  onIds: (ids: string[]) => void;
  newCount: number;
  resetNew: () => void;
}) {
  const ui = useUI();
  const user = useUser().data?.user;
  const cache = useQueryClient();
  const [filters, setFilters] = useState(emptyFilters);
  const [view, setView] = useState("all");
  const [sort, setSort] = useState("newest");
  const [expanded, setExpanded] = useState(true);
  const [debounced, setDebounced] = useState(query);
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) setQuery(q);
  }, []);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 250);
    return () => clearTimeout(t);
  }, [query]);
  const domains = useQuery({
    queryKey: ["domains"],
    queryFn: () => api<Domain[]>("/domains"),
  });
  const stats = useQuery({
    queryKey: ["stats"],
    queryFn: () =>
      api<{
        figures: number;
        papers: number;
        domains: number;
        updated_at: string | null;
      }>("/stats"),
  });
  const parameters = new URLSearchParams({
    q: debounced,
    view,
    sort,
    ...Object.fromEntries(
      Object.entries(filters).map(([k, v]) => [
        k,
        Array.isArray(v) ? v.join("|") : String(v),
      ]),
    ),
  }).toString();
  const result = useInfiniteQuery({
    queryKey: ["figures", parameters],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      api<FigurePage>(`/figures?${parameters}&offset=${pageParam}`),
    getNextPageParam: (last) => last.next_offset ?? undefined,
  });
  const items = result.data?.pages.flatMap((p) => p.items) || [];
  const signature = items.map((f) => f.id).join(",");
  useEffect(
    () => onIds(signature ? signature.split(",") : []),
    [signature, onIds],
  );
  useEffect(() => {
    const target = bottom.current;
    if (!target) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (
          entries[0].isIntersecting &&
          result.hasNextPage &&
          !result.isFetchingNextPage
        )
          void result.fetchNextPage();
      },
      { rootMargin: "500px" },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [result.hasNextPage, result.isFetchingNextPage, result.fetchNextPage]);
  function set<K extends keyof typeof filters>(
    key: K,
    value: (typeof filters)[K],
  ) {
    setFilters((f) => ({ ...f, [key]: value }));
  }
  const active =
    Object.entries(filters).some(
      ([k, v]) => k !== "tag_mode" && (Array.isArray(v) ? v.length : !!v),
    ) ||
    query ||
    view !== "all";
  const domain = domains.data?.find((d) => d.slug === filters.domain);
  function reset() {
    setFilters(emptyFilters);
    setQuery("");
    setView("all");
  }
  return (
    <>
      <section className="gallery-intro">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" /> A PRISM FOR YOUR NEXT IDEA
          </div>
          <h1>
            从一张好图，<span>看见新灵感。</span>
            <span className="intro-spark">
              <Sparkles size={24} strokeWidth={1.25} />
            </span>
          </h1>
          <p>发现前沿论文中的构图与配色，让下一张科研图表有迹可循。</p>
        </div>
        <div className="library-stats">
          <div>
            <strong>{stats.data?.figures?.toLocaleString() ?? "—"}</strong>
            <span>图表灵感</span>
          </div>
          <i />
          <div>
            <strong>{stats.data?.papers?.toLocaleString() ?? "—"}</strong>
            <span>研究论文</span>
          </div>
          <div className="library-caption">
            <span />
            持续生长的科研图谱
          </div>
        </div>
      </section>
      <section className="filter-panel" aria-label="图表筛选">
        <div className="domain-filter">
          <span className="filter-label">研究领域</span>
          <div className="domain-chips">
            <button
              className={`chip ${!filters.domain ? "active" : ""}`}
              onClick={() => {
                set("domain", "");
                set("sub_tags", []);
              }}
            >
              全部领域
            </button>
            {domains.data?.map((d) => (
              <button
                key={d.slug}
                className={`chip ${filters.domain === d.slug ? "active" : ""}`}
                onClick={() =>
                  setFilters((f) => ({
                    ...f,
                    domain: f.domain === d.slug ? "" : d.slug,
                    sub_tags: [],
                  }))
                }
              >
                <i style={{ background: d.color_dot }} />
                {d.name
                  .replace("推理与计算扩展", "推理扩展")
                  .replace("自演化与递归改进", "自演化 RSI")}
              </button>
            ))}
          </div>
          <button
            className="icon-button filter-toggle"
            title={expanded ? "收起筛选" : "展开筛选"}
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
          >
            {expanded ? (
              <ChevronUp size={17} />
            ) : (
              <SlidersHorizontal size={17} />
            )}
          </button>
        </div>
        {domain && domain.sub_tags.length > 0 && (
          <div className="subtag-filter">
            <span className="filter-label">细分方向</span>
            {domain.sub_tags.map((t) => (
              <button
                key={t}
                className={`chip tiny ${filters.sub_tags.includes(t) ? "selected" : ""}`}
                onClick={() =>
                  set(
                    "sub_tags",
                    filters.sub_tags.includes(t)
                      ? filters.sub_tags.filter((x) => x !== t)
                      : [...filters.sub_tags, t],
                  )
                }
              >
                {t}
              </button>
            ))}
            <button
              className="text-button"
              onClick={() =>
                set("tag_mode", filters.tag_mode === "any" ? "all" : "any")
              }
            >
              {filters.tag_mode === "any" ? "匹配任一" : "匹配全部"}
            </button>
          </div>
        )}
        {expanded && (
          <>
            <div className="secondary-filters">
              <span className="filter-label">会议来源</span>
              <div className="venue-chips">
                {[
                  "ICLR",
                  "ICML",
                  "CVPR",
                  "ACL",
                  "EMNLP",
                  "NeurIPS",
                  "HF 高热",
                ].map((v) => (
                  <button
                    key={v}
                    className={filters.venue === v ? "selected" : ""}
                    onClick={() => set("venue", filters.venue === v ? "" : v)}
                  >
                    {v}
                  </button>
                ))}
              </div>
              <span className="filter-divider" />
              <button
                className={`honor-filter ${filters.honors ? "selected" : ""}`}
                onClick={() => set("honors", !filters.honors)}
              >
                <Sparkles size={12} />
                Oral / Spotlight
              </button>
              <div className="layout-selects">
                <select
                  aria-label="论文版式"
                  value={filters.layout}
                  onChange={(e) => set("layout", e.target.value)}
                >
                  <option value="">全部版式</option>
                  <option value="single">单栏论文</option>
                  <option value="double">双栏论文</option>
                </select>
                <select
                  aria-label="图表跨栏"
                  value={filters.span}
                  onChange={(e) => set("span", e.target.value)}
                >
                  <option value="">全部宽度</option>
                  <option value="full">通栏宽图</option>
                  <option value="column">半栏窄图</option>
                </select>
              </div>
            </div>
            <div className="color-filter-row">
              <span className="filter-label">配色灵感</span>
              <div className="hue-filter">
                {hues.map((color, i) => (
                  <button
                    key={i}
                    title={hueNames[i]}
                    aria-label={`筛选${hueNames[i]}配色`}
                    aria-pressed={filters.color === String(i)}
                    className={filters.color === String(i) ? "selected" : ""}
                    style={{ background: color }}
                    onClick={() =>
                      set("color", filters.color === String(i) ? "" : String(i))
                    }
                  />
                ))}
                <button
                  className={`muted-hue ${filters.color === "muted" ? "selected" : ""}`}
                  aria-label="筛选低饱和配色"
                  title="莫兰迪低饱和"
                  onClick={() =>
                    set("color", filters.color === "muted" ? "" : "muted")
                  }
                />
                <button
                  className={`contrast-hue ${filters.color === "contrast" ? "selected" : ""}`}
                  aria-label="筛选冷暖撞色"
                  title="冷暖撞色"
                  onClick={() =>
                    set("color", filters.color === "contrast" ? "" : "contrast")
                  }
                />
              </div>
              <span className="color-hint">从一抹颜色开始探索</span>
              {active && (
                <button className="reset-filter" onClick={reset}>
                  <X size={12} />
                  重置筛选
                </button>
              )}
            </div>
          </>
        )}
      </section>
      <div className="gallery-toolbar">
        <div className="view-tabs">
          <button
            className={view === "all" ? "active" : ""}
            onClick={() => {
              setView("all");
              set("archetype", "");
            }}
          >
            <LayoutGrid size={14} />
            全部精选<span>{result.data?.pages[0]?.total ?? "—"}</span>
          </button>
          <button
            className={view === "method" ? "active" : ""}
            onClick={() => {
              setView("method");
              set("archetype", "");
            }}
          >
            方法架构图
          </button>
          <button
            className={view === "data" ? "active" : ""}
            onClick={() => {
              setView("data");
              set("archetype", "");
            }}
          >
            数据实验图
          </button>
        </div>
        <div className="gallery-options">
          <label className="case-toggle">
            <input
              type="checkbox"
              checked={filters.show_cases}
              onChange={(e) => set("show_cases", e.target.checked)}
            />
            <span className="toggle" />
            显示定性案例
          </label>
          <span className="filter-divider" />
          <select
            aria-label="排序方式"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
          >
            <option value="newest">最新收录</option>
            <option value="popular">讨论热度</option>
          </select>
        </div>
      </div>
      <div className="archetype-row">
        <button
          className={!filters.archetype ? "active" : ""}
          onClick={() => set("archetype", "")}
        >
          所有图表类型
        </button>
        {archetypes
          .filter((a) => a !== "Case Study")
          .map((a) => (
            <button
              key={a}
              className={filters.archetype === a ? "active" : ""}
              onClick={() => {
                set("archetype", a === filters.archetype ? "" : a);
                setView("all");
              }}
            >
              {archetypeNames[a]}
            </button>
          ))}
      </div>
      {/^https:\/\/(arxiv.org|huggingface.co|openreview.net)/.test(query) && (
        <div className="search-suggestion">
          <LinkIcon />
          识别到论文链接，添加后即可自动拆解图表。
          <button
            className="text-button"
            onClick={() => (user ? ui.openIngest() : ui.openLogin())}
          >
            添加论文 <ArrowRight size={14} />
          </button>
        </div>
      )}
      {newCount > 0 && (
        <button
          className="new-figures"
          onClick={() => {
            cache.invalidateQueries({ queryKey: ["figures"] });
            cache.invalidateQueries({ queryKey: ["stats"] });
            resetNew();
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        >
          <Sparkles size={14} />
          {newCount} 张新图表已入库 · 点击刷新
        </button>
      )}
      <ErrorMessage error={result.error} retry={() => result.refetch()} />
      {result.isPending ? (
        <div className="masonry skeletons">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
            <div className="skeleton-card" key={n}>
              <div style={{ height: [190, 260, 170, 210][n % 4] }} />
              <span />
            </div>
          ))}
        </div>
      ) : items.length ? (
        <div className={`masonry density-${ui.density}`}>
          {items.map((f) => (
            <FigureCard key={f.id} figure={f} />
          ))}
        </div>
      ) : (
        !result.error && (
          <Empty
            title={active ? "还没有匹配的图表" : "让第一篇论文，点亮灵感库"}
            description={
              active
                ? "换一个关键词、领域或配色，再看看。"
                : "通过论文链接或本地 PDF，开始构建你的科研图表收藏。"
            }
            action={
              active ? (
                <button className="button" onClick={reset}>
                  重置所有筛选
                </button>
              ) : (
                <button
                  className="button primary"
                  onClick={() => (user ? ui.openIngest() : ui.openLogin())}
                >
                  <Plus size={15} />
                  添加论文
                </button>
              )
            }
          />
        )
      )}
      <div ref={bottom} className="load-more">
        {result.isFetchingNextPage ? (
          <>
            <Spinner />
            更多灵感正在加载
          </>
        ) : result.hasNextPage ? (
          <button className="button" onClick={() => result.fetchNextPage()}>
            加载更多 <ArrowDown size={14} />
          </button>
        ) : items.length > 0 ? (
          <>
            <span />
            灵感暂时翻到底了，下一个发现就在下一篇论文。
            <span />
          </>
        ) : null}
      </div>
    </>
  );
}
function LinkIcon() {
  return <ArrowUpRight size={16} />;
}
function JobToast() {
  const user = useUser().data?.user;
  const [hidden, setHidden] = useState("");
  const result = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api<Job[]>("/jobs"),
    enabled: !!user,
    refetchInterval: 5000,
  });
  const job =
    result.data?.find((j) => j.status === "running" || j.status === "queued") ||
    result.data?.[0];
  if (!user || !job || job.id === hidden) return null;
  const active = ["queued", "running"].includes(job.status);
  return (
    <aside className="job-toast" aria-live="polite">
      <div>
        {active ? (
          <span className="pulse-dot" />
        ) : job.status === "completed" ? (
          <Check size={15} />
        ) : (
          <X size={15} />
        )}
        <strong>
          {active
            ? "论文处理任务"
            : job.status === "completed"
              ? "处理完成"
              : "任务未完成"}
        </strong>
        <button
          className="icon-button"
          title="收起任务提示"
          onClick={() => setHidden(job.id)}
        >
          <X size={13} />
        </button>
      </div>
      <p>{job.message || "任务已排队，等待开始处理…"}</p>
      {active && (
        <div className="progress-track">
          <i style={{ width: job.progress + "%" }} />
        </div>
      )}
    </aside>
  );
}
