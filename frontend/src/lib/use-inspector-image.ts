"use client";
import { useEffect, useRef, useState } from "react";
import { Figure } from "./types";

type DisplayImage = { id: string; src: string; hd: boolean; alt: string };

// Keep the current DOM image until a replacement is decoded; never blank the stage.
export function useInspectorImage(
  figure: Figure | undefined,
  selectedId: string | null,
) {
  const imageRef = useRef<HTMLImageElement>(null);
  const [displayed, setDisplayed] = useState<DisplayImage | null>(null);
  const [loadedSrc, setLoadedSrc] = useState("");
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!selectedId) {
      setDisplayed(null);
      setLoadedSrc("");
      setError(false);
      return;
    }
    if (!figure || figure.id !== selectedId) return;
    let cancelled = false;
    let fullReady = false;
    const full = new Image();
    const thumb = new Image();
    const id = figure.id;
    const alt = figure.caption || figure.title;
    setError(false);
    full.src = figure.hd_url;
    full
      .decode()
      .then(() => {
        if (!cancelled) {
          fullReady = true;
          setDisplayed({ id, src: figure.hd_url, hd: true, alt });
        }
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    thumb.src = figure.thumb_url;
    thumb
      .decode()
      .then(() => {
        if (!cancelled && !fullReady)
          setDisplayed({ id, src: figure.thumb_url, hd: false, alt });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      full.src = "";
      thumb.src = "";
    };
  }, [selectedId, figure?.id, figure?.hd_url, figure?.thumb_url, attempt]);
  const visible =
    displayed ||
    (figure
      ? {
          id: figure.id,
          src: figure.thumb_url,
          hd: false,
          alt: figure.caption || figure.title,
        }
      : null);
  const ready = !!(
    visible?.hd &&
    visible.id === selectedId &&
    figure?.id === selectedId &&
    visible.src === figure.hd_url &&
    loadedSrc === visible.src
  );
  function loaded() {
    const image = imageRef.current;
    if (
      image &&
      visible &&
      image.currentSrc === new URL(visible.src, window.location.href).href
    )
      setLoadedSrc(visible.src);
  }
  return {
    imageRef,
    visible,
    ready,
    error,
    onLoad: loaded,
    onError: () => setError(true),
    retry: () => setAttempt((a) => a + 1),
  };
}
