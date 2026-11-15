"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  useQuery,
  useQueryClient,
  keepPreviousData,
} from "@tanstack/react-query";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  Bookmark,
  Check,
  ChevronDown,
  Code2,
  Copy,
  Crop,
  ExternalLink,
  Focus,
  Minus,
  MousePointer2,
  Pipette,
  Plus,
  RotateCcw,
  Scissors,
  Sparkles,
  Type,
  X,
  ZoomIn,
} from "lucide-react";
import { api, post, put, paletteCode, rgb } from "@/lib/api";
import {
  Figure,
  Board,
  figureTypeLabel,
  methodSubTypes,
  methodStyles,
  methodTopologies,
  methodCrafts,
  dataChartTypes,
  dataChartLayouts,
} from "@/lib/types";
import { useUI } from "@/lib/store";
import { Modal, Spinner, ErrorMessage, useUser, copyColor } from "./ui";
import { quickSave } from "./figure-card";
import { SiblingFigures } from "./paper-groups";
import { useInspectorImage } from "@/lib/use-inspector-image";
import { warmFigureImage } from "@/lib/decoded-image-cache";

import { useInspectorViewport } from "@/lib/use-inspector-viewport";
import { ZoomRail } from "./zoom-rail";
import { RichCaption } from "./rich-caption";
const EMPTY_BOARDS: Board[] = [];

export function Inspector({ ids }: { ids: string[] }) {
  const ui = useUI();
  const user = useUser().data?.user || null;
  const cache = useQueryClient();
  const result = useQuery({
    queryKey: ["figure", ui.selectedId],
    queryFn: () => api<Figure>(`/figures/${ui.selectedId}`),
    enabled: !!ui.selectedId,
    placeholderData: keepPreviousData,
  });
  const f = result.data;
  const feedQuery = ui.selectedContext?.feedQuery;
  const feedLabel = ui.selectedContext?.feedLabel || "当前筛选";
  const [showAll, setShowAll] = useState(false);
  const siblingQuery = useQuery({
    queryKey: ["siblings", f?.paper_id, feedQuery || "all"],
    queryFn: () =>
      api<{ items: Figure[]; total: number; matched_count: number }>(
        `/papers/${f?.paper_id}/figures${feedQuery ? "?" + feedQuery : ""}`,
      ),
    enabled: !!f?.paper_id,
  });
  const allQuery = useQuery({
    queryKey: ["siblings", f?.paper_id, "all"],
    queryFn: () =>
      api<{ items: Figure[]; total: number; matched_count: number }>(
        `/papers/${f?.paper_id}/figures`,
      ),
    enabled: !!f?.paper_id && !!feedQuery && showAll,
  });
  const matched = siblingQuery.data?.items || [];
  const siblings =
    feedQuery && showAll ? allQuery.data?.items || matched : matched;
  const matchedIds = new Set(matched.map((item) => item.id));
  const picture = useInspectorImage(f, ui.selectedId);
  const isSwitching = !!ui.selectedId && f?.id !== ui.selectedId;
  useEffect(() => {
    if (!ui.selectedId) setShowAll(false);
  }, [ui.selectedId]);
  const [focus, setFocus] = useState<string | null>(null);
  const [hover, setHover] = useState(false);
  const [picker, setPicker] = useState(false);
  const [serif, setSerif] = useState(false);
  const [format, setFormat] = useState("HEX");
  const [board, setBoard] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [cropping, setCropping] = useState(false);
  const [showLoadingNotice, setShowLoadingNotice] = useState(false);
  useEffect(() => {
    if (!ui.selectedId || cropping || (picture.ready && !isSwitching)) {
      setShowLoadingNotice(false);
      return;
    }
    if (picture.error && !isSwitching) {
      setShowLoadingNotice(true);
      return;
    }
    const timer = setTimeout(() => setShowLoadingNotice(true), 150);
    return () => clearTimeout(timer);
  }, [cropping, picture.ready, picture.error, isSwitching, ui.selectedId]);

  const [codeOpen, setCodeOpen] = useState(false);
  const [isPanning, setIsPanning] = useState(false);
  const {
    zoom,
    zoomRef,
    applyZoom,
    resetZoom,
    scrollRef,
    stageRef,
    attachScroll,
    stageWidthPx,
  } = useInspectorViewport(
    f?.width && f?.height ? f.width / f.height : f?.aspect_ratio || 1.4,
    ui.selectedId,
    !cropping,
  );
  const panStateRef = useRef<{
    startX: number;
    startY: number;
    scrollLeft: number;
    scrollTop: number;
    pointerId: number;
    moved: boolean;
  } | null>(null);
  const img = picture.imageRef;
  const pixelCanvas = useRef<HTMLCanvasElement | null>(null);
  const loupe = useRef<HTMLCanvasElement>(null);
  const [point, setPoint] = useState<{
    x: number;
    y: number;
    hex: string;
    px: number;
    py: number;
  } | null>(null);
  const boards =
    useQuery({
      queryKey: ["boards"],
      queryFn: () => api<Board[]>("/collections"),
      enabled: !!user && !!ui.selectedId,
    }).data || EMPTY_BOARDS;
  useEffect(() => {
    setFocus(ui.selectedContext?.focus || null);
    setNote(ui.selectedContext?.note || "");
    if (ui.selectedContext?.boardId) setBoard(ui.selectedContext.boardId);
    setPicker(false);
    setCropping(false);
    setCodeOpen(false);
    setPoint(null);

    if (ui.selectedId && user)
      void post(`/figures/${ui.selectedId}/view`).catch(() => {});
  }, [ui.selectedId, ui.selectedContext, user?.id]);

  const selectInInspector = useCallback(
    (id: string) => {
      if (id === ui.selectedId) return;
      const next = [...matched, ...(allQuery.data?.items || [])].find(
        (item) => item.id === id,
      );
      if (next) cache.setQueryData(["figure", id], next);
      const context = ui.selectedContext;
      ui.select(
        id,
        context
          ? {
              feedQuery: context.feedQuery,
              feedLabel: context.feedLabel,
              boardId: context.boardId,
            }
          : undefined,
      );
    },
    [matched, allQuery.data, cache, ui.selectedId, ui.selectedContext],
  );
  const navigationIds = showAll ? siblings.map((item) => item.id) : ids;
  const navigate = useCallback(
    (direction: number) => {
      const list = navigationIds.includes(ui.selectedId || "")
        ? navigationIds
        : siblings.map((item) => item.id);
      const index = list.indexOf(ui.selectedId || "");
      const next = list[index + direction];
      if (next) selectInInspector(next);
    },
    [navigationIds, siblings, ui.selectedId, selectInInspector],
  );
  useEffect(() => {
    const index = siblings.findIndex((item) => item.id === f?.id);
    if (!ui.selectedId || !picture.ready) return;
    for (const next of [siblings[index + 1], siblings[index - 1]]) {
      if (next) warmFigureImage(next);
    }
  }, [f?.id, siblings, ui.selectedId, picture.ready]);
  function toggleScope() {
    if (showAll && f && !matchedIds.has(f.id) && matched[0])
      selectInInspector(matched[0].id);
    setShowAll((value) => !value);
  }
  useEffect(() => {
    if (!ui.selectedId) return;
    const key = (e: KeyboardEvent) => {
      if (
        (e.target as HTMLElement).closest(
          "input,textarea,select,[contenteditable]",
        )
      )
        return;
      if (!cropping && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
        e.preventDefault();
        const index = siblings.findIndex((s) => s.id === ui.selectedId);
        const next = siblings[index + (e.key === "ArrowUp" ? -1 : 1)];
        if (next) selectInInspector(next.id);
      }
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        navigate(-1);
      }
      if (e.key === "ArrowRight") {
        e.preventDefault();
        navigate(1);
      }
      if (e.code === "Space") {
        e.preventDefault();
        applyZoom(zoomRef.current === 1 ? 1.85 : 1);
      }
      if (e.key.toLowerCase() === "i" && picture.ready && !cropping)
        setPicker((v) => !v);
      if (e.key.toLowerCase() === "s" && f && !isSwitching) {
        e.preventDefault();
        if (user) void quickSave(f);
        else ui.openLogin();
      }
      if (/^[0-9]$/.test(e.key)) {
        setFocus(
          e.key === "0" ? null : f?.subitems[Number(e.key) - 1]?.id || null,
        );
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [
    ui.selectedId,
    f,
    navigate,
    user,
    siblings,
    cropping,
    selectInInspector,
    picture.ready,
    isSwitching,
  ]);
  function move(e: React.PointerEvent<HTMLDivElement>) {
    if (!img.current || !f || !picture.ready) return;
    const bounds = img.current.getBoundingClientRect();
    const nx = (e.clientX - bounds.left) / bounds.width;
    const ny = (e.clientY - bounds.top) / bounds.height;
    if (nx < 0 || ny < 0 || nx > 1 || ny > 1) {
      setPoint(null);
      return;
    }
    if (hover && !picker) {
      setFocus(
        f.subitems.find(
          (s) =>
            nx >= s.norm_bbox[0] &&
            nx <= s.norm_bbox[2] &&
            ny >= s.norm_bbox[1] &&
            ny <= s.norm_bbox[3],
        )?.id || null,
      );
    }
    if (picker) {
      if (!pixelCanvas.current) {
        pixelCanvas.current = document.createElement("canvas");
        pixelCanvas.current.width = 1;
        pixelCanvas.current.height = 1;
      }
      const c = pixelCanvas.current;
      const px = Math.min(
        img.current.naturalWidth - 1,
        Math.floor(nx * img.current.naturalWidth),
      );
      const py = Math.min(
        img.current.naturalHeight - 1,
        Math.floor(ny * img.current.naturalHeight),
      );
      const ctx = c.getContext("2d", { willReadFrequently: true })!;
      ctx.drawImage(img.current, px, py, 1, 1, 0, 0, 1, 1);
      const data = ctx.getImageData(0, 0, 1, 1).data;
      const hex =
        "#" +
        [...data]
          .slice(0, 3)
          .map((v) => v.toString(16).padStart(2, "0"))
          .join("")
          .toUpperCase();
      const parent = e.currentTarget.getBoundingClientRect();
      setPoint({
        x: e.clientX - parent.left,
        y: e.clientY - parent.top,
        px,
        py,
        hex,
      });
    }
  }
  useEffect(() => {
    if (!point || !loupe.current || !img.current || !picture.ready) return;
    const ctx = loupe.current.getContext("2d")!;
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, 112, 112);
    ctx.drawImage(
      img.current,
      point.px - 7,
      point.py - 7,
      14,
      14,
      0,
      0,
      112,
      112,
    );
    ctx.strokeStyle = "rgba(255,255,255,.35)";
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 112; i += 8) {
      ctx.beginPath();
      ctx.moveTo(i, 0);
      ctx.lineTo(i, 112);
      ctx.moveTo(0, i);
      ctx.lineTo(112, i);
      ctx.stroke();
    }
    ctx.strokeStyle = "#111";
    ctx.lineWidth = 1;
    ctx.strokeRect(56, 56, 8, 8);
  }, [point, picture.ready]);
  async function save() {
    if (!user) {
      ui.openLogin();
      return;
    }
    if (!f) return;
    setSaving(true);
    try {
      let target = board || boards[0]?.id;
      if (!target) {
        const b = await post<Board>("/collections", { name: "我的灵感收藏" });
        target = b.id;
        cache.invalidateQueries({ queryKey: ["boards"] });
      }
      await put(`/collections/${target}/items`, {
        figure_id: f.id,
        focused_subitem_id: focus,
        user_note: note,
      });
      ui.notify("灵感和笔记已保存");
      cache.invalidateQueries({ queryKey: ["board", target] });
    } catch (e) {
      ui.notify((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  async function repair() {
    if (!f) return;
    try {
      await post(`/figures/${f.id}/repair`);
      ui.notify("已加入精修队列，等待 Codex 任务处理");
    } catch (e) {
      ui.notify((e as Error).message);
    }
  }
  const focused = f?.subitems.find((s) => s.id === focus);
  const palette = focused?.palette || f?.palette;
  const colors = palette?.colors.map((c) => c.hex) || [];
  const exportText = paletteCode(colors, format);
  const canPan = !picker && !cropping && zoom > 1.01;
  const sidebar = useMemo(
    () =>
      f ? (
        <aside className="inspector-sidebar" aria-busy={isSwitching}>
          {isSwitching ? (
            <div className="detail-loading" role="status">
              <Spinner />
              <strong>正在加载当前图表详情</strong>
              <div className="detail-skeleton" />
              <div className="detail-skeleton" />
            </div>
          ) : (
            <>
              <div className="paper-heading">
                <div className="eyebrow">
                  THE PAPER{" "}
                  <span className="venue-badge">
                    {f.venue} {f.venue_year}
                  </span>
                  {f.venue_tier && f.venue_tier !== "poster" && (
                    <span className="honor-badge">{f.venue_tier}</span>
                  )}
                </div>
                <div className="inspector-classification">
                  <strong>{figureTypeLabel(f)}</strong>
                  {f.primary_style && (
                    <span className="taxonomy-pill style-pill">
                      {methodStyles.find((x) => x.key === f.primary_style)
                        ?.label || f.primary_style}
                    </span>
                  )}
                  {f.secondary_style && (
                    <span className="taxonomy-pill subtle-pill">
                      {methodStyles.find((x) => x.key === f.secondary_style)
                        ?.short || f.secondary_style}
                    </span>
                  )}
                  {f.layout_topology && (
                    <span className="taxonomy-pill topo-pill">
                      {methodTopologies.find((x) => x.key === f.layout_topology)
                        ?.label || f.layout_topology}
                    </span>
                  )}
                  {f.chart_layout && (
                    <span className="taxonomy-pill layout-pill">
                      {dataChartLayouts.find((x) => x.key === f.chart_layout)
                        ?.label || f.chart_layout}
                    </span>
                  )}
                  {(f.craft_badges || []).map((badge) => (
                    <span key={badge} className="taxonomy-pill craft-pill">
                      {methodCrafts.find((x) => x.key === badge)?.label ||
                        badge}
                    </span>
                  ))}
                  {f.taxonomy_locked === 1 && (
                    <span
                      className="taxonomy-pill locked-pill"
                      title="人工修改分类已锁定，批量刷新自动跳过"
                    >
                      已锁定
                    </span>
                  )}
                  {feedQuery && siblingQuery.data && (
                    <span
                      className={
                        matchedIds.has(f.id) ? "matched" : "outside-filter"
                      }
                    >
                      {matchedIds.has(f.id)
                        ? `命中${feedLabel}`
                        : "未命中当前筛选"}
                    </span>
                  )}
                </div>
                <h2>{f.title}</h2>
                <p className="authors">
                  {f.authors.join(", ") || "作者信息未提取"}
                </p>
                <div className="paper-links">
                  <a
                    href={`/api/papers/${f.paper_id}/pdf#page=${f.page_number}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <ExternalLink size={12} />
                    原文 P.{f.page_number}
                  </a>
                  {Object.entries(f.source_urls)
                    .filter(([k]) => k !== "pdf")
                    .map(([k, v]) => (
                      <a key={k} href={v} target="_blank" rel="noreferrer">
                        {k === "html"
                          ? "arXiv HTML"
                          : k === "hf"
                            ? "HF 讨论"
                            : k === "openreview"
                              ? "OpenReview"
                              : k}
                        <ExternalLink size={11} />
                      </a>
                    ))}
                </div>
              </div>
              <section className="panel-section">
                <div className="section-label">
                  <h3>
                    图注 <span>CAPTION</span>
                  </h3>
                  <button
                    onClick={() => setSerif(!serif)}
                    title="切换衬线阅读字体"
                    className={`icon-button ${serif ? "active" : ""}`}
                  >
                    <Type size={15} />
                  </button>
                </div>
                <p className={`caption-text ${serif ? "serif" : ""}`}>
                  <RichCaption
                    text={focused?.caption || f.caption || "暂无图注"}
                    onFocus={setFocus}
                  />
                </p>
                {f.review_status !== "ok" && (
                  <p className="review-note">
                    <span />
                    自动提取 · 裁切待复核
                  </p>
                )}
              </section>
              <section className="panel-section">
                <div className="section-label">
                  <h3>
                    科研配色{" "}
                    <span>
                      {focus ? `SUBFIGURE ${focus.toUpperCase()}` : "PALETTE"}
                    </span>
                  </h3>
                  <span className="subtle-label">{colors.length} COLORS</span>
                </div>
                {palette && (
                  <>
                    <div className="palette-strip">
                      {palette.colors.map((c) => (
                        <button
                          key={c.hex}
                          title={`复制 ${c.hex}`}
                          onClick={() => copyColor(c.hex, f.id, user)}
                          style={{ background: c.hex }}
                        >
                          <span
                            style={{ color: c.l > 0.65 ? "#334155" : "white" }}
                          >
                            {c.hex}
                          </span>
                        </button>
                      ))}
                    </div>
                    {palette.pairs.length > 0 && (
                      <div className="color-pairs">
                        {palette.pairs.map((p, i) => (
                          <div
                            className="color-pair"
                            key={i}
                            style={{
                              background: p.fill,
                              borderColor: p.stroke,
                            }}
                          >
                            <button
                              onClick={() => copyColor(p.fill, f.id, user)}
                            >
                              <small>FILL</small>
                              <code>{p.fill}</code>
                            </button>
                            <button
                              onClick={() => copyColor(p.stroke, f.id, user)}
                              style={{ color: p.stroke }}
                            >
                              <small>STROKE</small>
                              <code>{p.stroke}</code>
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                    {palette.neutrals.length > 0 && (
                      <div className="neutral-row">
                        <span>坐标轴 / 中性色</span>
                        {palette.neutrals.map((c) => (
                          <button
                            key={c}
                            onClick={() => copyColor(c, f.id, user)}
                          >
                            <i style={{ background: c }} />
                            <code>{c}</code>
                          </button>
                        ))}
                      </div>
                    )}
                    <div className="format-tabs">
                      {["HEX", "RGB", "Matplotlib", "LaTeX", "CSS"].map((t) => (
                        <button
                          key={t}
                          className={format === t ? "active" : ""}
                          onClick={() => setFormat(t)}
                        >
                          {t}
                        </button>
                      ))}
                    </div>
                    <div className="code-box">
                      <pre>{exportText || "暂无彩色像素"}</pre>
                      <button
                        className="icon-button"
                        aria-label="复制整套配色"
                        onClick={async () => {
                          try {
                            await navigator.clipboard.writeText(exportText);
                            ui.notify("整套配色已复制");
                          } catch {
                            ui.notify("无法自动复制，请手动选择代码");
                          }
                        }}
                      >
                        <Copy size={14} />
                      </button>
                    </div>
                  </>
                )}
              </section>
              <section className="panel-section">
                <div className="section-label">
                  <h3>
                    工程透视 <span>DETAILS</span>
                  </h3>
                </div>
                <div className="spec-grid">
                  <div>
                    <span>宽高比</span>
                    <strong className="mono">
                      {f.aspect_ratio.toFixed(2)} : 1
                    </strong>
                  </div>
                  <div>
                    <span>论文版式</span>
                    <strong>
                      {f.layout_type === "double" ? "双栏" : "单栏"} ·{" "}
                      {f.span_type === "full" ? "通栏宽图" : "半栏窄图"}
                    </strong>
                  </div>
                  <div>
                    <span>内嵌字体</span>
                    <strong>{f.fonts.join(", ") || "未检测到"}</strong>
                  </div>
                  <div>
                    <span>提取方式</span>
                    <strong>
                      {f.extract_method === "tex_raw"
                        ? "TeX 原始矢量"
                        : "PDF 矢量切片"}
                    </strong>
                  </div>
                </div>
                <a
                  className="button primary full"
                  href={
                    focused?.has_raw
                      ? `/api/figures/${f.id}/subitems/${focus}/raw`
                      : f.raw_url
                  }
                  download
                >
                  <ArrowDownToLine size={16} />
                  {focused?.has_raw
                    ? `下载子图 (${focus}) 矢量 PDF`
                    : "下载矢量 PDF"}
                  <span className="button-tag">VECTOR</span>
                </a>
                <a
                  className="download-secondary"
                  href={f.hd_url}
                  download={`${f.fig_label}.webp`}
                >
                  下载高清 WebP <ArrowDownToLine size={12} />
                </a>
                {f.tikz_code && (
                  <>
                    <button
                      className="text-button"
                      onClick={() => setCodeOpen(!codeOpen)}
                    >
                      <Code2 size={14} />
                      TikZ / PGFPlots 源码 <ChevronDown size={14} />
                    </button>
                    {codeOpen && (
                      <div className="code-box">
                        <pre>{f.tikz_code}</pre>
                        <button
                          className="icon-button"
                          onClick={() => {
                            navigator.clipboard.writeText(f.tikz_code || "");
                            ui.notify("TikZ 源码已复制");
                          }}
                        >
                          <Copy size={14} />
                        </button>
                      </div>
                    )}
                  </>
                )}
                {user && (
                  <div className="taxonomy-editor">
                    <label className="type-editor">
                      <span>
                        图表分类{" "}
                        {f.taxonomy_locked === 1 ? "（已人工锁定）" : ""}
                      </span>
                      <select
                        aria-label="图表分类"
                        value={f.sub_type || "system_pipeline"}
                        onChange={async (e) => {
                          const nextSub = e.target.value;
                          const nextMacro = methodSubTypes.some(
                            (m) => m.key === nextSub,
                          )
                            ? "method"
                            : dataChartTypes.some((d) => d.key === nextSub)
                              ? "data_chart"
                              : "case_study";
                          try {
                            await api(`/figures/${f.id}`, {
                              method: "PATCH",
                              body: JSON.stringify({
                                macro_category: nextMacro,
                                sub_type: nextSub,
                                sub_tags: f.sub_tags,
                              }),
                            });
                            cache.invalidateQueries({
                              queryKey: ["figure", f.id],
                            });
                            cache.invalidateQueries({ queryKey: ["figures"] });
                            cache.invalidateQueries({ queryKey: ["siblings"] });
                            ui.notify("分类已更新并锁定");
                          } catch (err) {
                            ui.notify((err as Error).message);
                          }
                        }}
                      >
                        <optgroup label="方法架构图">
                          {methodSubTypes.map((m) => (
                            <option key={m.key} value={m.key}>
                              {m.label}
                            </option>
                          ))}
                        </optgroup>
                        <optgroup label="数据实验图">
                          {dataChartTypes.map((d) => (
                            <option key={d.key} value={d.key}>
                              {d.label}
                            </option>
                          ))}
                        </optgroup>
                        <optgroup label="定性展示">
                          <option value="qualitative_case">定性案例</option>
                        </optgroup>
                      </select>
                    </label>
                    {f.macro_category === "method" && (
                      <div className="taxonomy-editor-row">
                        <label className="type-editor compact">
                          <span>画风质感</span>
                          <select
                            aria-label="画风质感"
                            value={f.primary_style || ""}
                            onChange={async (e) => {
                              try {
                                await api(`/figures/${f.id}`, {
                                  method: "PATCH",
                                  body: JSON.stringify({
                                    primary_style: e.target.value || null,
                                  }),
                                });
                                cache.invalidateQueries({
                                  queryKey: ["figure", f.id],
                                });
                                cache.invalidateQueries({
                                  queryKey: ["figures"],
                                });
                                cache.invalidateQueries({
                                  queryKey: ["siblings"],
                                });
                              } catch (err) {
                                ui.notify((err as Error).message);
                              }
                            }}
                          >
                            <option value="">未指定画风</option>
                            {methodStyles.map((s) => (
                              <option key={s.key} value={s.key}>
                                {s.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="type-editor compact">
                          <span>构图骨架</span>
                          <select
                            aria-label="构图骨架"
                            value={f.layout_topology || ""}
                            onChange={async (e) => {
                              try {
                                await api(`/figures/${f.id}`, {
                                  method: "PATCH",
                                  body: JSON.stringify({
                                    layout_topology: e.target.value || null,
                                  }),
                                });
                                cache.invalidateQueries({
                                  queryKey: ["figure", f.id],
                                });
                                cache.invalidateQueries({
                                  queryKey: ["figures"],
                                });
                                cache.invalidateQueries({
                                  queryKey: ["siblings"],
                                });
                              } catch (err) {
                                ui.notify((err as Error).message);
                              }
                            }}
                          >
                            <option value="">未指定骨架</option>
                            {methodTopologies.map((t) => (
                              <option key={t.key} value={t.key}>
                                {t.label}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                    )}
                    {f.macro_category === "data_chart" && (
                      <label className="type-editor compact">
                        <span>实验排版形态</span>
                        <select
                          aria-label="实验排版形态"
                          value={f.chart_layout || ""}
                          onChange={async (e) => {
                            try {
                              await api(`/figures/${f.id}`, {
                                method: "PATCH",
                                body: JSON.stringify({
                                  chart_layout: e.target.value || null,
                                }),
                              });
                              cache.invalidateQueries({
                                queryKey: ["figure", f.id],
                              });
                              cache.invalidateQueries({
                                queryKey: ["figures"],
                              });
                              cache.invalidateQueries({
                                queryKey: ["siblings"],
                              });
                            } catch (err) {
                              ui.notify((err as Error).message);
                            }
                          }}
                        >
                          <option value="">未指定排版</option>
                          {dataChartLayouts.map((l) => (
                            <option key={l.key} value={l.key}>
                              {l.label}
                            </option>
                          ))}
                        </select>
                      </label>
                    )}
                  </div>
                )}
              </section>
              <section className="panel-section save-panel">
                <h3>
                  <Bookmark size={15} />
                  钉入灵感看板
                </h3>
                {user ? (
                  <>
                    <select
                      aria-label="目标看板"
                      value={board}
                      onChange={(e) => setBoard(e.target.value)}
                    >
                      <option value="">
                        {boards[0]?.name || "我的灵感收藏（自动创建）"}
                      </option>
                      {boards.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name}
                        </option>
                      ))}
                    </select>
                    <textarea
                      aria-label="灵感笔记"
                      rows={2}
                      placeholder="记一笔灵感，如：用虚线区分训练与推理流…"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                    />
                    {focus && <small>将同时保存子图 ({focus}) 聚焦状态</small>}
                  </>
                ) : (
                  <p className="muted">
                    登录后，把构图与配色灵感留给未来的自己。
                  </p>
                )}
                <button
                  className="button full"
                  disabled={saving}
                  onClick={save}
                >
                  {saving ? <Spinner /> : <Plus size={15} />}{" "}
                  {user ? "保存至看板" : "登录并收藏"}
                </button>
              </section>
            </>
          )}
        </aside>
      ) : null,
    [
      f,
      isSwitching,
      user,
      focus,
      serif,
      format,
      board,
      note,
      saving,
      codeOpen,
      boards,
      feedQuery,
      feedLabel,
      siblingQuery.data,
      ui,
      cache,
    ],
  );
  return (
    <Modal
      open={!!ui.selectedId}
      onOpenChange={(open) => {
        if (!open) ui.select(null);
      }}
      title={f ? `${f.fig_label} · 图表检视器` : "图表检视器"}
      className="inspector-modal"
    >
      {result.isPending ? (
        <div className="inspector-loading">
          <Spinner />
          正在加载图表
        </div>
      ) : result.error ? (
        <ErrorMessage error={result.error} retry={() => result.refetch()} />
      ) : (
        f && (
          <div className="inspector-body">
            <section className="inspector-canvas">
              <div className="canvas-top">
                <div className="capsule">
                  <button
                    onClick={() => navigate(-1)}
                    aria-label="上一张图表"
                    disabled={navigationIds.indexOf(f.id) <= 0}
                  >
                    <ArrowLeft size={16} />
                  </button>
                  <span>{f.fig_label}</span>
                  <button
                    onClick={() => navigate(1)}
                    aria-label="下一张图表"
                    disabled={
                      navigationIds.indexOf(f.id) >= navigationIds.length - 1
                    }
                  >
                    <ArrowRight size={16} />
                  </button>
                </div>
                <div className="capsule">
                  <button
                    className={picker ? "active" : ""}
                    onClick={() => {
                      setPicker(!picker);
                      setPoint(null);
                    }}
                    title="吸管取色 (I)"
                    aria-label="吸管取色"
                    disabled={!picture.ready || cropping}
                  >
                    <Pipette size={16} />
                  </button>
                  <i />
                  <button
                    onClick={() => applyZoom(zoom - 0.25)}
                    aria-label="缩小"
                  >
                    <Minus size={15} />
                  </button>
                  <span className="mono">{Math.round(zoom * 100)}%</span>
                  <button
                    onClick={() => applyZoom(zoom + 0.25)}
                    aria-label="放大"
                  >
                    <Plus size={15} />
                  </button>
                  <button
                    onClick={resetZoom}
                    title="适应窗口"
                    aria-label="适应窗口"
                  >
                    <Focus size={16} />
                  </button>
                </div>
              </div>
              {!cropping &&
                showLoadingNotice &&
                (!picture.ready || isSwitching) && (
                  <div
                    className="image-load-status"
                    role="status"
                    aria-live="polite"
                  >
                    {(!picture.error || isSwitching) && <Spinner />}
                    <div>
                      <strong>
                        {isSwitching
                          ? "正在读取图表"
                          : picture.error
                            ? "高清图暂时无法加载"
                            : "高清图加载中"}
                      </strong>
                      <span>
                        {isSwitching
                          ? "正在准备下一张图片"
                          : picture.visible?.id === f.id
                            ? `${f.fig_label} · 当前显示预览`
                            : `正在切换到 ${f.fig_label}`}
                      </span>
                    </div>
                    {picture.error && !isSwitching && (
                      <button onClick={picture.retry}>重试</button>
                    )}
                  </div>
                )}
              {cropping ? (
                <CropEditor
                  figure={f}
                  onDone={() => {
                    setCropping(false);
                    cache.invalidateQueries({ queryKey: ["figure", f.id] });
                    cache.invalidateQueries({ queryKey: ["figures"] });
                    cache.invalidateQueries({ queryKey: ["siblings"] });
                  }}
                  onCancel={() => setCropping(false)}
                />
              ) : (
                <>
                  <ZoomRail zoom={zoom} onZoom={applyZoom} onFit={resetZoom} />
                  <div
                    ref={attachScroll}
                    className={`canvas-scroll ${canPan ? "pannable" : ""} ${isPanning ? "panning" : ""}`}
                    onPointerDown={(e) => {
                      if (!canPan || e.button !== 0 || !scrollRef.current)
                        return;
                      if ((e.target as HTMLElement).closest("button")) return;
                      panStateRef.current = {
                        startX: e.clientX,
                        startY: e.clientY,
                        scrollLeft: scrollRef.current.scrollLeft,
                        scrollTop: scrollRef.current.scrollTop,
                        pointerId: e.pointerId,
                        moved: false,
                      };
                    }}
                    onPointerMove={(e) => {
                      const st = panStateRef.current;
                      const el = scrollRef.current;
                      if (!st || !el) return;
                      const dx = e.clientX - st.startX;
                      const dy = e.clientY - st.startY;
                      if (!st.moved && Math.hypot(dx, dy) > 4) {
                        st.moved = true;
                        setIsPanning(true);
                        el.setPointerCapture(st.pointerId);
                      }
                      if (st.moved) {
                        e.preventDefault();
                        el.scrollLeft = st.scrollLeft - dx;
                        el.scrollTop = st.scrollTop - dy;
                      }
                    }}
                    onPointerUp={() => {
                      const st = panStateRef.current;
                      const el = scrollRef.current;
                      if (st && el && el.hasPointerCapture(st.pointerId)) {
                        el.releasePointerCapture(st.pointerId);
                      }
                      panStateRef.current = null;
                      setIsPanning(false);
                    }}
                    onPointerCancel={() => {
                      const st = panStateRef.current;
                      const el = scrollRef.current;
                      if (st && el && el.hasPointerCapture(st.pointerId)) {
                        el.releasePointerCapture(st.pointerId);
                      }
                      panStateRef.current = null;
                      setIsPanning(false);
                    }}
                  >
                    <div
                      ref={stageRef}
                      className={`image-stage ${picker ? "picking" : ""}`}
                      onPointerMove={move}
                      onPointerLeave={() => setPoint(null)}
                      onDoubleClick={(e) => {
                        if (picker || cropping) return;
                        applyZoom(zoom < 1.5 ? 2 : 1, e.clientX, e.clientY);
                      }}
                      onClick={() => {
                        if (picker && point && picture.ready)
                          void copyColor(point.hex, f.id, user);
                      }}
                      style={
                        stageWidthPx
                          ? { width: `${stageWidthPx}px` }
                          : { maxWidth: "100%", maxHeight: "100%" }
                      }
                    >
                      <div
                        className="image-wrap"
                        style={{
                          aspectRatio:
                            f.width && f.height
                              ? f.width / f.height
                              : f.aspect_ratio || 1.4,
                        }}
                      >
                        <img
                          ref={img}
                          className="fig-paper-blend"
                          style={{ height: "100%", objectFit: "contain" }}
                          src={picture.visible?.src || f.thumb_url}
                          alt={picture.visible?.alt || f.title}
                          data-figure-id={picture.visible?.id || f.id}
                          data-resolution={picture.ready ? "hd" : "preview"}
                          onLoad={picture.onLoad}
                          onError={picture.onError}
                          draggable={false}
                        />
                        {focused && picture.visible?.id === f.id && (
                          <div
                            className="spotlight"
                            style={{
                              left: `${focused.norm_bbox[0] * 100}%`,
                              top: `${focused.norm_bbox[1] * 100}%`,
                              width: `${(focused.norm_bbox[2] - focused.norm_bbox[0]) * 100}%`,
                              height: `${(focused.norm_bbox[3] - focused.norm_bbox[1]) * 100}%`,
                            }}
                          />
                        )}
                      </div>
                      {point && picker && picture.ready && (
                        <div
                          className="loupe"
                          style={{
                            left: Math.max(0, point.x - 56),
                            top: point.y - 150,
                          }}
                        >
                          <canvas width={112} height={112} ref={loupe} />
                          <span>{point.hex}</span>
                        </div>
                      )}
                    </div>
                  </div>
                  {f.subitems.length > 1 && (
                    <div className="sub-controls">
                      <div className="capsule">
                        <button
                          className={!focus ? "active" : ""}
                          onClick={() => setFocus(null)}
                        >
                          整图
                        </button>
                        {f.subitems.map((s) => (
                          <button
                            key={s.id}
                            className={focus === s.id ? "active" : ""}
                            onClick={() => setFocus(s.id)}
                          >
                            {s.label}
                          </button>
                        ))}
                        <i />
                        <button
                          onClick={() => setHover(!hover)}
                          className={hover ? "active" : ""}
                          title="悬停热区感应"
                        >
                          <MousePointer2 size={14} />
                        </button>
                      </div>
                    </div>
                  )}
                  <SiblingFigures
                    figures={siblings}
                    currentId={f.id}
                    onSelect={selectInInspector}
                    scopeLabel={feedQuery ? feedLabel : undefined}
                    showAll={showAll}
                    totalCount={siblingQuery.data?.total}
                    matchedIds={feedQuery ? matchedIds : undefined}
                    onToggleScope={toggleScope}
                    loading={
                      siblingQuery.isPending || (showAll && allQuery.isPending)
                    }
                  />
                  <div className="canvas-bottom">
                    <span>
                      <span className="keycap">滚轮</span> 缩放{" "}
                      <span className="keycap">拖拽</span> 平移{" "}
                      <span className="keycap">I</span> 取色{" "}
                      <span className="keycap">← →</span> 切图
                    </span>
                    {user && (
                      <div>
                        <button
                          className="button small"
                          onClick={() => setCropping(true)}
                        >
                          <Scissors size={14} />
                          框选重切
                        </button>
                        <button className="button small" onClick={repair}>
                          <Sparkles size={14} />
                          请求精修
                        </button>
                      </div>
                    )}
                  </div>
                </>
              )}
            </section>
            {sidebar}
          </div>
        )
      )}
    </Modal>
  );
}

function CropEditor({
  figure: f,
  onDone,
  onCancel,
}: {
  figure: Figure;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [page, setPage] = useState(f.page_number);
  const [total, setTotal] = useState(150);
  const [src, setSrc] = useState("");
  const [box, setBox] = useState<number[]>([0.1, 0.1, 0.9, 0.5]);
  const [snap, setSnap] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const image = useRef<HTMLImageElement>(null);
  const drag = useRef<{ start: number[]; box: number[]; mode: string } | null>(
    null,
  );
  const ui = useUI();
  useEffect(() => {
    const abort = new AbortController();
    let url = "";
    setSrc("");
    setError(null);
    fetch(`/api/figures/${f.id}/page?page=${page}`, { signal: abort.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error("无法加载 PDF 原页");
        setTotal(Number(r.headers.get("X-Page-Count") || 1));
        if (page === f.page_number)
          setBox(
            JSON.parse(r.headers.get("X-Crop-Bbox") || "[0.1,0.1,0.9,0.5]"),
          );
        else setBox([0.1, 0.1, 0.9, 0.5]);
        url = URL.createObjectURL(await r.blob());
        setSrc(url);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e);
      });
    return () => {
      abort.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [page, f.id]);
  function coords(e: React.PointerEvent) {
    const r = image.current!.getBoundingClientRect();
    return [
      Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)),
      Math.max(0, Math.min(1, (e.clientY - r.top) / r.height)),
    ];
  }
  function down(e: React.PointerEvent, mode = "new") {
    e.preventDefault();
    e.stopPropagation();
    if (!image.current) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { start: coords(e), box: [...box], mode };
    if (mode === "new") {
      const [x, y] = coords(e);
      setBox([x, y, x, y]);
    }
  }
  function move(e: React.PointerEvent) {
    const d = drag.current;
    if (!d) return;
    const [x, y] = coords(e);
    if (d.mode === "new") {
      setBox([
        Math.min(x, d.start[0]),
        Math.min(y, d.start[1]),
        Math.max(x, d.start[0]),
        Math.max(y, d.start[1]),
      ]);
      return;
    }
    const b = [...d.box];
    if (d.mode === "move") {
      const dx = Math.max(-b[0], Math.min(1 - b[2], x - d.start[0]));
      const dy = Math.max(-b[1], Math.min(1 - b[3], y - d.start[1]));
      setBox([b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy]);
      return;
    }
    if (d.mode.includes("w")) b[0] = Math.min(x, b[2] - 0.01);
    if (d.mode.includes("e")) b[2] = Math.max(x, b[0] + 0.01);
    if (d.mode.includes("n")) b[1] = Math.min(y, b[3] - 0.01);
    if (d.mode.includes("s")) b[3] = Math.max(y, b[1] + 0.01);
    setBox(b);
  }
  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await post(`/figures/${f.id}/recrop`, {
        page,
        bbox: box,
        snap_vector: snap,
      });
      ui.notify("裁切、配色和矢量文件已更新");
      onDone();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="crop-editor">
      <div className="crop-toolbar">
        <button
          className="icon-button"
          disabled={page <= 1}
          onClick={() => setPage(page - 1)}
          aria-label="上一页"
        >
          <ArrowLeft size={15} />
        </button>
        <span>
          第 {page} / {total} 页
        </span>
        <button
          className="icon-button"
          disabled={page >= total}
          onClick={() => setPage(page + 1)}
          aria-label="下一页"
        >
          <ArrowRight size={15} />
        </button>
        <label>
          <input
            type="checkbox"
            checked={snap}
            onChange={(e) => setSnap(e.target.checked)}
          />
          自动矢量吸附
        </label>
      </div>
      <div className="crop-scroll">
        {!src && !error ? (
          <Spinner />
        ) : (
          src && (
            <div
              className="crop-page"
              onPointerDown={(e) => down(e)}
              onPointerMove={move}
              onPointerUp={() => {
                drag.current = null;
              }}
            >
              <img
                ref={image}
                className="fig-paper-blend"
                src={src}
                alt="PDF 原页，拖动框选图表"
                draggable={false}
              />
              <div
                className="crop-box"
                style={{
                  left: `${box[0] * 100}%`,
                  top: `${box[1] * 100}%`,
                  width: `${(box[2] - box[0]) * 100}%`,
                  height: `${(box[3] - box[1]) * 100}%`,
                }}
                onPointerDown={(e) => down(e, "move")}
              >
                {["nw", "n", "ne", "e", "se", "s", "sw", "w"].map((h) => (
                  <span
                    key={h}
                    className={`crop-handle ${h}`}
                    onPointerDown={(e) => down(e, h)}
                  />
                ))}
              </div>
            </div>
          )
        )}
      </div>
      <ErrorMessage error={error} />
      <div className="crop-footer">
        <button className="button" onClick={onCancel}>
          取消
        </button>
        <button
          className="button primary"
          disabled={busy || !src || box[2] - box[0] < 0.01}
          onClick={submit}
        >
          {busy ? <Spinner /> : <Check size={15} />}确认重切并刷新配色
        </button>
      </div>
    </div>
  );
}
