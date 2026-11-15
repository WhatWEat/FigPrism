import type { Figure } from "./types";

type Entry = { image: HTMLImageElement; bytes: number };
const decoded = new Map<string, Entry>();
const loading = new Map<string, Promise<HTMLImageElement>>();
const MAX_BYTES = 128 * 1024 * 1024;
const MAX_ENTRIES = 24;
const MAX_PREFETCH_PIXELS = 8_000_000;
let activeUrl = "";
let usedBytes = 0;

function trim() {
  for (const [url, entry] of decoded) {
    if (usedBytes <= MAX_BYTES && decoded.size <= MAX_ENTRIES) break;
    if (url === activeUrl) continue;
    decoded.delete(url);
    usedBytes -= entry.bytes;
  }
}

export function setActiveImage(url: string) {
  activeUrl = url;
  trim();
}

export function cachedImage(url: string) {
  const entry = decoded.get(url);
  if (!entry) return undefined;
  decoded.delete(url);
  decoded.set(url, entry);
  return entry.image;
}

export function loadDecodedImage(url: string, priority: "high" | "low" = "high") {
  if (priority === "high") setActiveImage(url);
  const cached = cachedImage(url);
  if (cached) return Promise.resolve(cached);
  const pending = loading.get(url);
  if (pending) return pending;
  const image = new Image();
  image.decoding = "async";
  image.fetchPriority = priority;
  image.src = url;
  const promise = image.decode().then(() => {
    const bytes = image.naturalWidth * image.naturalHeight * 4;
    if (bytes <= MAX_BYTES) {
      decoded.set(url, { image, bytes });
      usedBytes += bytes;
      trim();
    }
    return image;
  }).finally(() => loading.delete(url));
  loading.set(url, promise);
  return promise;
}

export function warmFigureImage(figure: Figure) {
  // Adjacent giant figures must not compete with the image being opened.
  if (loading.size >= 2 || figure.width * figure.height > MAX_PREFETCH_PIXELS) return;
  void loadDecodedImage(figure.hd_url, "low").catch(() => {});
}
