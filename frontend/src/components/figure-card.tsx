"use client";
import { useEffect, useRef, useState } from "react";
import { decode } from "blurhash";
import { warmFigureImage } from "@/lib/decoded-image-cache";
import { Bookmark, Layers, ArrowUpRight } from "lucide-react";
import { Figure, Board } from "@/lib/types";
import { useUI } from "@/lib/store";
import { api, post, put } from "@/lib/api";
import { Swatches, useUser } from "./ui";
const readyThumbnails = new Set<string>();
export function preloadThumbnails(figures: Figure[]) {
  for (const figure of figures) {
    if (readyThumbnails.has(figure.thumb_url)) continue;
    const image = new Image();
    image.src = figure.thumb_url;
    image
      .decode()
      .then(() => readyThumbnails.add(figure.thumb_url))
      .catch(() => {});
  }
}
export function BlurImage({ figure: f }: { figure: Figure }) {
  const focused = f.subitems.find(
    (s) => s.id === f.collection_item?.focused_subitem_id,
  );
  const canvas = useRef<HTMLCanvasElement>(null);
  const [loaded, setLoaded] = useState(() => readyThumbnails.has(f.thumb_url));
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!f.blurhash || !canvas.current) return;
    try {
      const pixels = decode(f.blurhash, 32, 24);
      canvas.current
        .getContext("2d")
        ?.putImageData(
          new ImageData(new Uint8ClampedArray(pixels), 32, 24),
          0,
          0,
        );
    } catch {}
  }, [f.blurhash]);
  return (
    <div className="figure-image" style={{ aspectRatio: f.aspect_ratio }}>
      <canvas
        ref={canvas}
        width={32}
        height={24}
        style={{ opacity: loaded ? 0 : 1 }}
        aria-hidden="true"
      />
      <img
        className="fig-paper-blend"
        draggable={false}
        src={f.thumb_url}
        width={f.width}
        height={f.height}
        alt={`${f.fig_label}: ${f.caption || f.title}`}
        loading="lazy"
        onLoad={() => {
          readyThumbnails.add(f.thumb_url);
          setLoaded(true);
        }}
        onError={() => setFailed(true)}
        style={{ opacity: loaded ? 1 : 0 }}
      />
      {focused && (
        <div
          className="spotlight card-spotlight"
          style={{
            left: `${focused.norm_bbox[0] * 100}%`,
            top: `${focused.norm_bbox[1] * 100}%`,
            width: `${(focused.norm_bbox[2] - focused.norm_bbox[0]) * 100}%`,
            height: `${(focused.norm_bbox[3] - focused.norm_bbox[1]) * 100}%`,
          }}
        />
      )}
      {failed && <span className="image-error">图片暂时无法加载</span>}
    </div>
  );
}
export async function quickSave(f: Figure) {
  try {
    let boards = await api<Board[]>("/collections");
    if (!boards.length)
      boards = [await post<Board>("/collections", { name: "我的灵感收藏" })];
    await put(`/collections/${boards[0].id}/items`, { figure_id: f.id });
    useUI.getState().notify(`已收入「${boards[0].name}」`);
  } catch (e) {
    useUI.getState().notify((e as Error).message);
  }
}
export function FigureCard({
  figure: f,
  children,
  onSelect,
}: {
  figure: Figure;
  children?: React.ReactNode;
  onSelect?: (id: string) => void;
}) {
  const ui = useUI();
  const user = useUser().data?.user;
  return (
    <article className="figure-card">
      <div className="figure-frame">
        <button
          className="figure-open"
          onPointerEnter={() => warmFigureImage(f)}
          onFocus={() => warmFigureImage(f)}
          aria-label={`查看 ${f.fig_label} ${f.title}`}
          onClick={() => (onSelect ? onSelect(f.id) : ui.select(f.id))}
        >
          <BlurImage figure={f} />
        </button>
        {f.subitems.length > 1 && (
          <span className="sub-badge">
            <Layers size={11} />
            {f.subitems.length} 子图
          </span>
        )}
        <div className="card-actions">
          <button
            className="icon-button"
            title="收入看板"
            aria-label="收入看板"
            onClick={() => (user ? quickSave(f) : ui.openLogin())}
          >
            <Bookmark size={16} />
          </button>
          <a
            className="icon-button"
            title="论文原文"
            href={`/api/papers/${f.paper_id}/pdf#page=${f.page_number}`}
            target="_blank"
            rel="noreferrer"
          >
            <ArrowUpRight size={17} />
          </a>
        </div>
        <div className="hover-caption">
          {f.fig_label} <span>{f.caption || f.title}</span>
        </div>
      </div>
      <div className="figure-meta">
        <div>
          <span className="venue-badge">
            {f.venue}
            {f.venue_year ? ` '${String(f.venue_year).slice(-2)}` : ""}
          </span>
          {f.venue_tier === "oral" && (
            <span className="honor-dot" title="Oral" />
          )}
          <span className="layout-label">
            {f.layout_type === "double" ? "双栏" : "单栏"} ·{" "}
            {f.span_type === "full" ? "通栏" : "半栏"}
          </span>
        </div>
        <Swatches figure={f} small />
      </div>
      {children}
    </article>
  );
}
