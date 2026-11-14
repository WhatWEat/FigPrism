"use client";
import { Plus, Minus, Focus } from "lucide-react";
import {
  MAX_INSPECTOR_ZOOM,
  MIN_INSPECTOR_ZOOM,
} from "@/lib/use-inspector-viewport";
export function ZoomRail({
  zoom,
  onZoom,
  onFit,
}: {
  zoom: number;
  onZoom: (value: number) => void;
  onFit: () => void;
}) {
  const percent = Math.round(zoom * 100);
  return (
    <div className="zoom-rail" aria-label="画布缩放控制">
      <button
        className="icon-button"
        onClick={() => onZoom(zoom * 1.25)}
        disabled={zoom >= MAX_INSPECTOR_ZOOM}
        aria-label="滑条放大"
      >
        <Plus size={15} />
      </button>
      <output className="mono" aria-live="off">
        {percent}%
      </output>
      <input
        aria-label="缩放倍率"
        aria-orientation="vertical"
        aria-valuetext={`${percent}%`}
        type="range"
        min={Math.log2(MIN_INSPECTOR_ZOOM)}
        max={Math.log2(MAX_INSPECTOR_ZOOM)}
        step="0.01"
        value={Math.log2(zoom)}
        onChange={(event) => onZoom(2 ** Number(event.target.value))}
      />
      <button
        className="icon-button"
        onClick={() => onZoom(zoom / 1.25)}
        disabled={zoom <= MIN_INSPECTOR_ZOOM}
        aria-label="滑条缩小"
      >
        <Minus size={15} />
      </button>
      <button
        className="icon-button"
        onClick={onFit}
        aria-label="重置缩放"
        title="适应窗口"
      >
        <Focus size={15} />
      </button>
    </div>
  );
}
