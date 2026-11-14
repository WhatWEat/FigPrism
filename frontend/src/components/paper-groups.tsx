"use client";
import { useEffect, useRef, useState } from "react";
import {
  Bookmark,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Layers,
  Plus,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { api, post, put } from "@/lib/api";
import { Figure, PaperGroup, Domain, Board, archetypeNames } from "@/lib/types";
import { useUI } from "@/lib/store";
import { BlurImage, quickSave, preloadThumbnails } from "./figure-card";
import { Swatches, useUser } from "./ui";

// Keep grouped thumbnails warm only when their paper reaches the viewport.
function usePreload(figures: Figure[]) {
  const ref = useRef<HTMLElement>(null);
  const urls = figures.map((f) => f.thumb_url).join("|");
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          preloadThumbnails(figures);
          observer.disconnect();
        }
      },
      { rootMargin: "120px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [urls]);
  return ref;
}

export function useHorizontalTrack(count: number, dragEnabled = false) {
  const ref = useRef<HTMLDivElement>(null);
  const [remaining, setRemaining] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const update = () => {
      const edge = element.getBoundingClientRect().right;
      setRemaining(
        [...element.children].filter(
          (child) => child.getBoundingClientRect().right > edge + 2,
        ).length,
      );
    };
    const wheel = (event: WheelEvent) => {
      if (event.ctrlKey) return;
      const delta =
        Math.abs(event.deltaX) > Math.abs(event.deltaY)
          ? event.deltaX
          : event.deltaY;
      const next = Math.max(
        0,
        Math.min(
          element.scrollWidth - element.clientWidth,
          element.scrollLeft + delta,
        ),
      );
      if (Math.abs(next - element.scrollLeft) > 0.5) {
        event.preventDefault();
        element.scrollBy({
          left: delta,
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)")
            .matches
            ? "auto"
            : "smooth",
        });
      }
    };
    let start: { x: number; left: number; pointer: number } | null = null;
    let dragged = false;
    const down = (event: PointerEvent) => {
      if (!dragEnabled || event.pointerType !== "mouse" || event.button !== 0)
        return;
      start = {
        x: event.clientX,
        left: element.scrollLeft,
        pointer: event.pointerId,
      };
      dragged = false;
    };
    const move = (event: PointerEvent) => {
      if (!start) return;
      const delta = event.clientX - start.x;
      if (Math.abs(delta) > 6) {
        dragged = true;
        element.setPointerCapture(event.pointerId);
      }
      if (dragged) {
        event.preventDefault();
        element.scrollLeft = start.left - delta;
      }
    };
    const up = () => {
      if (start && element.hasPointerCapture(start.pointer))
        element.releasePointerCapture(start.pointer);
      start = null;
    };
    const click = (event: MouseEvent) => {
      if (dragged) {
        event.preventDefault();
        event.stopPropagation();
        dragged = false;
      }
    };
    element.addEventListener("wheel", wheel, { passive: false });
    element.addEventListener("scroll", update);
    element.addEventListener("pointerdown", down);
    element.addEventListener("pointermove", move);
    element.addEventListener("pointerup", up);
    element.addEventListener("pointercancel", up);
    element.addEventListener("click", click, true);
    const observer = new ResizeObserver(update);
    observer.observe(element);
    const mutations = new MutationObserver(update);
    mutations.observe(element, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["style"],
    });
    update();
    return () => {
      observer.disconnect();
      mutations.disconnect();
      element.removeEventListener("wheel", wheel);
      element.removeEventListener("scroll", update);
      element.removeEventListener("pointerdown", down);
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerup", up);
      element.removeEventListener("pointercancel", up);
      element.removeEventListener("click", click, true);
    };
  }, [count, dragEnabled]);
  return { ref, remaining };
}

export function PaperDeckCard({ group }: { group: PaperGroup }) {
  const ui = useUI();
  const user = useUser().data?.user;
  const [selected, setSelected] = useState(group.hero_figure_id);
  const [expanded, setExpanded] = useState(false);
  const active =
    group.matched_figures.find((f) => f.id === selected) ||
    group.matched_figures.find((f) => f.id === group.hero_figure_id) ||
    group.matched_figures[0];
  const hero =
    group.matched_figures.find((f) => f.id === group.hero_figure_id) || active;
  const ref = usePreload(group.matched_figures);
  const track = useHorizontalTrack(
    group.matched_figures.length + (expanded ? 10000 : 0),
  );
  return (
    <article
      ref={ref}
      className={`paper-deck ${expanded ? "expanded" : ""}`}
      data-paper-id={group.paper.id}
      data-active-figure={active.id}
    >
      <header className="deck-brow">
        <div>
          <span className="venue-badge">
            {group.paper.venue}
            {group.paper.venue_year
              ? ` '${String(group.paper.venue_year).slice(-2)}`
              : ""}
            {group.paper.venue_tier && group.paper.venue_tier !== "poster"
              ? ` ${group.paper.venue_tier}`
              : ""}
          </span>
          <span className="deck-layout">
            {group.paper.layout_type === "double" ? "双栏" : "单栏"}
          </span>
        </div>
        <button
          className="deck-expand"
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
          aria-label={`${expanded ? "收起" : "展开平铺"} ${group.paper.title}`}
        >
          共 {group.matched_figures.length} 张图 ·{" "}
          {expanded ? "收起" : "展开平铺"}
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      </header>
      {expanded ? (
        <div className="deck-expanded">
          {group.matched_figures.map((f) => (
            <div
              className="deck-tile"
              key={f.id}
              onMouseEnter={() => setSelected(f.id)}
            >
              <button
                className="figure-open"
                aria-label={`查看 ${f.fig_label} ${f.title}`}
                onClick={() => ui.select(f.id)}
              >
                <BlurImage figure={f} />
              </button>
              <div>
                <span>{f.fig_label}</span>
                <Swatches figure={f} small />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <>
          <button
            className="figure-open deck-hero"
            aria-label={`查看 ${active.fig_label} ${active.title}`}
            style={{
              aspectRatio: Math.min(2.4, Math.max(1.25, hero.aspect_ratio)),
            }}
            onClick={() => ui.select(active.id)}
          >
            <BlurImage key={active.id} figure={active} />
            <span className="deck-hero-label">
              {active.fig_label} ·{" "}
              {archetypeNames[active.archetype] || active.archetype}
            </span>
            {active.subitems.length > 1 && (
              <span className="sub-badge">
                <Layers size={11} />
                {active.subitems.length} 子图
              </span>
            )}
          </button>
          {group.matched_figures.length >= 2 && (
            <div className="filmstrip-wrap">
              <div
                className="filmstrip"
                ref={track.ref}
                aria-label={`${group.paper.title} 图表胶片条`}
              >
                {group.matched_figures.map((f) => (
                  <button
                    key={f.id}
                    className={active.id === f.id ? "active" : ""}
                    style={{ width: Math.max(34, 50 * f.aspect_ratio) }}
                    onPointerEnter={(e) => {
                      if (e.pointerType === "mouse") setSelected(f.id);
                    }}
                    onFocus={() => setSelected(f.id)}
                    onClick={() => ui.select(f.id)}
                    aria-label={`打开 ${f.fig_label} ${f.title}`}
                    aria-pressed={active.id === f.id}
                    data-figure-id={f.id}
                  >
                    <img
                      className={ui.paperBlend ? "fig-paper-blend" : ""}
                      src={f.thumb_url}
                      alt={f.fig_label}
                      loading="lazy"
                      draggable={false}
                    />
                  </button>
                ))}
              </div>
              {track.remaining > 0 && (
                <div className="strip-fade" aria-hidden="true">
                  <span>+{track.remaining}</span>
                </div>
              )}
            </div>
          )}
        </>
      )}
      <footer className="deck-footer">
        <span className="deck-title" title={group.paper.title}>
          {group.paper.title}
        </span>
        <Swatches figure={active} small />
        <button
          className="icon-button"
          aria-label={`收藏当前图 ${active.fig_label}`}
          title="收藏当前图"
          onClick={() => (user ? quickSave(active) : ui.openLogin())}
        >
          <Bookmark size={14} />
        </button>
      </footer>
    </article>
  );
}

export function PaperSwimlane({
  group,
  domains,
}: {
  group: PaperGroup;
  domains: Domain[];
}) {
  const ui = useUI();
  const user = useUser().data?.user;
  const cache = useQueryClient();
  const [saving, setSaving] = useState(false);
  const ref = usePreload(group.matched_figures);
  const track = useHorizontalTrack(group.matched_figures.length, true);
  async function save() {
    if (!user) {
      ui.openLogin();
      return;
    }
    setSaving(true);
    try {
      let boards = await api<Board[]>("/collections");
      if (!boards.length)
        boards = [await post<Board>("/collections", { name: "我的灵感收藏" })];
      await put(`/collections/${boards[0].id}/items/bulk`, {
        figure_ids: group.matched_figures.map((f) => f.id),
      });
      cache.invalidateQueries({ queryKey: ["boards"] });
      cache.invalidateQueries({ queryKey: ["board", boards[0].id] });
      ui.notify(
        `已收藏 ${group.matched_figures.length} 张图到「${boards[0].name}」`,
      );
    } catch (e) {
      ui.notify((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <article
      ref={ref}
      className="paper-swimlane"
      data-paper-id={group.paper.id}
    >
      <header className="swimlane-heading">
        <div>
          <h2>{group.paper.title}</h2>
          <div className="swimlane-tags">
            <span className="venue-badge">
              {group.paper.venue} {group.paper.venue_year}
            </span>
            {group.paper.domains.map((slug) => (
              <span className="chip tiny" key={slug}>
                {domains.find((d) => d.slug === slug)?.name || slug}
              </span>
            ))}
            <span>{group.matched_figures.length} 张命中图表</span>
          </div>
        </div>
        <div className="swimlane-actions">
          <a
            className="button small"
            target="_blank"
            rel="noreferrer"
            href={`/api/papers/${group.paper.id}/pdf`}
          >
            <ExternalLink size={13} />
            原文 PDF
          </a>
          <button className="button small" disabled={saving} onClick={save}>
            <Bookmark size={13} />
            {saving ? "正在收藏…" : "收藏整篇好图"}
          </button>
        </div>
      </header>
      <div className="swimlane-track-wrap">
        <div
          ref={track.ref}
          className="swimlane-track"
          aria-label={`${group.paper.title} 横排图表`}
        >
          {group.matched_figures.map((f) => (
            <div
              className="swimlane-figure"
              key={f.id}
              style={{ width: Math.max(140, 210 * f.aspect_ratio) }}
            >
              <button
                className="figure-open"
                onClick={() => ui.select(f.id)}
                aria-label={`查看 ${f.fig_label} ${f.title}`}
              >
                <BlurImage figure={f} />
              </button>
              <div className="swimlane-caption">
                <span title={f.caption}>
                  <strong>{f.fig_label}</strong>{" "}
                  {f.caption || archetypeNames[f.archetype]}
                </span>
                <Swatches figure={f} small />
              </div>
            </div>
          ))}
        </div>
        {track.remaining > 0 && (
          <div className="strip-fade" aria-hidden="true">
            <span>+{track.remaining}</span>
          </div>
        )}
      </div>
    </article>
  );
}

export function SiblingFigures({
  figures,
  currentId,
  onSelect,
}: {
  figures: Figure[];
  currentId: string;
  onSelect: (id: string) => void;
}) {
  const blend = useUI((s) => s.paperBlend);
  const track = useHorizontalTrack(figures.length);
  useEffect(() => {
    const active = track.ref.current?.querySelector<HTMLElement>(
      '[aria-current="true"]',
    );
    if (active) {
      const container = track.ref.current!;
      if (
        active.offsetLeft < container.scrollLeft ||
        active.offsetLeft + active.offsetWidth >
          container.scrollLeft + container.clientWidth
      )
        container.scrollTo({
          left: Math.max(
            0,
            active.offsetLeft -
              container.clientWidth / 2 +
              active.offsetWidth / 2,
          ),
          behavior: "smooth",
        });
    }
  }, [currentId]);
  if (figures.length < 2) return null;
  return (
    <div className="sibling-navigation">
      <div className="sibling-label">
        <strong>同篇图表</strong>
        <span>
          ↑ ↓ 切换 ·{" "}
          {Math.max(
            0,
            figures.findIndex((f) => f.id === currentId),
          ) + 1}{" "}
          / {figures.length}
        </span>
      </div>
      <div className="filmstrip-wrap">
        <div
          ref={track.ref}
          className="sibling-track"
          aria-label="同篇论文图表导航"
        >
          {figures.map((f) => (
            <button
              key={f.id}
              aria-label={`同文 ${f.fig_label}`}
              aria-current={f.id === currentId ? "true" : undefined}
              className={f.id === currentId ? "active" : ""}
              onClick={() => onSelect(f.id)}
            >
              <img
                className={blend ? "fig-paper-blend" : ""}
                src={f.thumb_url}
                alt=""
                loading="lazy"
                draggable={false}
              />
              <span>{f.fig_label}</span>
            </button>
          ))}
        </div>
        {track.remaining > 0 && (
          <div className="strip-fade" aria-hidden="true">
            <span>+{track.remaining}</span>
          </div>
        )}
      </div>
    </div>
  );
}

export function PaperDeckFeed({ groups }: { groups: PaperGroup[] }) {
  const [columns, setColumns] = useState(3);
  useEffect(() => {
    const update = () =>
      setColumns(
        window.innerWidth < 768
          ? 1
          : window.innerWidth < 1100
            ? 2
            : window.innerWidth < 1536
              ? 3
              : 4,
      );
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);
  return (
    <div
      className="paper-decks"
      style={{ gridTemplateColumns: `repeat(${columns},minmax(0,1fr))` }}
    >
      {Array.from({ length: columns }, (_, column) => (
        <div className="paper-deck-column" key={column}>
          {groups
            .filter((_, index) => index % columns === column)
            .map((group) => (
              <PaperDeckCard key={group.paper.id} group={group} />
            ))}
        </div>
      ))}
    </div>
  );
}
