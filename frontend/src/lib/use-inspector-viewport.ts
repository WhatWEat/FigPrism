"use client";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

export const MIN_INSPECTOR_ZOOM = 0.25;
export const MAX_INSPECTOR_ZOOM = 32;

/** Stable viewport geometry and one zoom commit per animation frame. */
export function useInspectorViewport(
  aspectRatio: number,
  resetKey: string | null,
  enabled = true,
) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const observerRef = useRef<ResizeObserver | null>(null);
  const frameRef = useRef<number | null>(null);
  const zoomRef = useRef(1);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;
  const anchorRef = useRef<{
    rx: number;
    ry: number;
    cx: number;
    cy: number;
  } | null>(null);
  const [zoom, setZoom] = useState(1);
  const [stageBox, setStageBox] = useState({ w: 0, h: 0 });
  const measure = useCallback((node: HTMLDivElement) => {
    const style = getComputedStyle(node);
    const w = Math.max(
      120,
      node.clientWidth -
        parseFloat(style.paddingLeft || "0") -
        parseFloat(style.paddingRight || "0"),
    );
    const h = Math.max(
      120,
      node.clientHeight -
        parseFloat(style.paddingTop || "0") -
        parseFloat(style.paddingBottom || "0"),
    );
    setStageBox((old) => (old.w === w && old.h === h ? old : { w, h }));
  }, []);
  const attachScroll = useCallback(
    (node: HTMLDivElement | null) => {
      observerRef.current?.disconnect();
      scrollRef.current = node;
      if (!node) return;
      measure(node);
      const observer = new ResizeObserver(() => measure(node));
      // Scrollbar/content changes must not recursively change the fit scale.
      observer.observe(node, { box: "border-box" });
      observerRef.current = observer;
    },
    [measure],
  );
  const applyZoom = useCallback(
    (requested: number, clientX?: number, clientY?: number) => {
      if (!Number.isFinite(requested)) return;
      const next = Math.min(
        MAX_INSPECTOR_ZOOM,
        Math.max(MIN_INSPECTOR_ZOOM, Math.round(requested * 100) / 100),
      );
      if (Math.abs(next - zoomRef.current) < 0.005) return;
      const scroll = scrollRef.current;
      const stage = stageRef.current;
      if (scroll && stage) {
        const box = scroll.getBoundingClientRect();
        const image = stage.getBoundingClientRect();
        const x = clientX ?? box.left + box.width / 2;
        const y = clientY ?? box.top + box.height / 2;
        if (image.width > 0 && image.height > 0)
          anchorRef.current = {
            rx: Math.min(1, Math.max(0, (x - image.left) / image.width)),
            ry: Math.min(1, Math.max(0, (y - image.top) / image.height)),
            cx: x - box.left,
            cy: y - box.top,
          };
      }
      zoomRef.current = next;
      if (frameRef.current === null)
        frameRef.current = requestAnimationFrame(() => {
          frameRef.current = null;
          setZoom(zoomRef.current);
        });
    },
    [],
  );
  const resetZoom = useCallback(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
    zoomRef.current = 1;
    anchorRef.current = null;
    setZoom(1);
    scrollRef.current?.scrollTo({ left: 0, top: 0 });
  }, []);
  useEffect(() => {
    resetZoom();
  }, [resetKey, resetZoom]);
  useEffect(
    () => () => {
      observerRef.current?.disconnect();
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    },
    [],
  );
  useLayoutEffect(() => {
    const anchor = anchorRef.current;
    const scroll = scrollRef.current;
    const stage = stageRef.current;
    if (!anchor || !scroll || !stage) return;
    anchorRef.current = null;
    if (zoom <= 1) {
      scroll.scrollLeft = 0;
      scroll.scrollTop = 0;
      return;
    }
    const box = scroll.getBoundingClientRect();
    const image = stage.getBoundingClientRect();
    scroll.scrollLeft = Math.max(
      0,
      image.left -
        box.left +
        scroll.scrollLeft +
        anchor.rx * image.width -
        anchor.cx,
    );
    scroll.scrollTop = Math.max(
      0,
      image.top -
        box.top +
        scroll.scrollTop +
        anchor.ry * image.height -
        anchor.cy,
    );
  }, [zoom]);
  useEffect(() => {
    const node = scrollRef.current;
    if (!node || !enabled) return;
    const wheel = (event: WheelEvent) => {
      if (!enabledRef.current) return;
      event.preventDefault();
      applyZoom(
        zoomRef.current *
          Math.exp(-event.deltaY * (event.ctrlKey ? 0.0085 : 0.0022)),
        event.clientX,
        event.clientY,
      );
    };
    node.addEventListener("wheel", wheel, { passive: false });
    return () => node.removeEventListener("wheel", wheel);
  }, [enabled, resetKey, stageBox.w, applyZoom]);
  const ratio = Math.max(0.05, aspectRatio || 1.4);
  const fitWidth =
    stageBox.w > 0 && stageBox.h > 0
      ? Math.min(stageBox.w, stageBox.h * ratio)
      : 0;
  return {
    zoom,
    zoomRef,
    applyZoom,
    resetZoom,
    scrollRef,
    stageRef,
    attachScroll,
    stageBox,
    fitWidth,
    stageWidthPx: fitWidth > 0 ? Math.round(fitWidth * zoom) : undefined,
  };
}
