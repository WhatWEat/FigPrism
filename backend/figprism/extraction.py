import io
import re
from dataclasses import dataclass, field
from functools import lru_cache
import fitz
from PIL import Image
import numpy as np
import blurhash
from .config import get_settings
from .palette import extract_palette


@dataclass
class Crop:
    page: int
    bbox: list[float]
    label: str
    caption: str
    confidence: float = 0.6
    raw: bytes | None = None
    tikz: str | None = None
    subitems: list = field(default_factory=list)


def text_blocks(page):
    return [
        (fitz.Rect(b[:4]), b[4].strip()) for b in page.get_text("blocks") if b[6] == 0
    ]


def ink_rects(page):
    rects = [
        fitz.Rect(d["rect"]) for d in page.get_drawings() if d["rect"].get_area() > 0
    ]
    rects += [fitz.Rect(i["bbox"]) for i in page.get_image_info()]
    return rects


def snap(page, bbox, exclusions=()):
    seed = fitz.Rect(bbox)
    candidates = ink_rects(page)
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                candidates.append(fitz.Rect(span["bbox"]))
    accepted = []
    expanded = seed + (-6, -6, 6, 6)
    for r in candidates:
        if not r.intersects(expanded):
            continue
        if any((r & z).get_area() > r.get_area() * 0.25 for z in exclusions):
            continue
        # Do not absorb a full-width paragraph that merely touches the initial region.
        if (r & expanded).get_area() < r.get_area() * 0.5:
            continue
        accepted.append(r)
    if not accepted:
        return list(seed & page.rect)
    tight = fitz.Rect(accepted[0])
    for r in accepted[1:]:
        tight |= r
    tight = (tight + (-8, -8, 8, 8)) & page.rect
    for z in exclusions:
        if tight.intersects(z) and z.y0 >= seed.y1 - 8:
            tight.y1 = min(tight.y1, z.y0 - 2)
    return list(tight)


@lru_cache(maxsize=1)
def layout_model(path):
    from doclayout_yolo import YOLOv10

    return YOLOv10(path)


def detect(page):
    blocks = text_blocks(page)
    captions = [
        (r, t) for r, t in blocks if re.match(r"^(?:Figure|Fig\.?)[ \n]+\d+", t, re.I)
    ]
    crops = []
    model_path = get_settings().layout_model
    if model_path:
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        if model_path.endswith(".onnx"):
            from .layout import predict

            boxes = predict(image, model_path)
        else:
            result = layout_model(model_path).predict(
                image, device="cpu", verbose=False
            )[0]
            boxes = [
                {
                    "bbox": [float(v) for v in b.xyxy[0]],
                    "label": result.names[int(b.cls)],
                    "confidence": float(b.conf),
                }
                for b in result.boxes
            ]
        exclusions = [
            fitz.Rect(*[v / 1.5 for v in box["bbox"]])
            for box in boxes
            if box["label"]
            in (
                "plain text",
                "table",
                "figure_caption",
                "title",
                "abandon",
                "table_caption",
            )
        ]
        for box in sorted(boxes, key=lambda b: (b["bbox"][1], b["bbox"][0])):
            if box["label"] != "figure":
                continue
            r = fitz.Rect(*[v / 1.5 for v in box["bbox"]])
            # Caption must align horizontally; do not steal a caption from the adjacent column.
            adjacent = [
                (cr, ct) for cr, ct in captions if min(cr.x1, r.x1) > max(cr.x0, r.x0)
            ]
            nearest = min(
                adjacent, key=lambda x: abs(x[0].y0 - r.y1), default=(None, "")
            )
            cap = nearest[1]
            match = re.match(r"^(?:Figure|Fig\.?)\s*(\d+)", cap, re.I)
            if not match and box["confidence"] < 0.8:
                continue
            label = match[1] if match else f"{page.number + 1}.{len(crops) + 1}"
            crops.append(
                Crop(
                    page.number + 1,
                    snap(page, r, exclusions),
                    f"Fig. {label}",
                    cap,
                    box["confidence"],
                )
            )
        # Caption geometry recovers a composite when the detector sees only one panel.
        for geometry in geometry_crops(page):
            matches = [c for c in crops if c.label == geometry.label]
            if not matches:
                crops.append(geometry)
            else:
                first = matches[0]
                union = fitz.Rect(first.bbox)
                for match in matches[1:]:
                    union |= fitz.Rect(match.bbox)
                    crops.remove(match)
                gr = fitz.Rect(geometry.bbox)
                if gr.width > union.width * 1.25 or gr.height > union.height * 1.25:
                    union |= gr
                    first.confidence = min(first.confidence, 0.74)
                first.bbox = list(union & page.rect)
        return crops
    return geometry_crops(page)


def geometry_crops(page):
    blocks = text_blocks(page)
    captions = [
        (r, t) for r, t in blocks if re.match(r"^(?:Figure|Fig\.?)[ \n]+\d+", t, re.I)
    ]
    crops = []
    # Conservative fallback anchored to captions, with explicit low confidence.
    inks = ink_rects(page)
    for cr, caption in captions:
        if layout_type(page.parent) == "single" or cr.width > page.rect.width * 0.55:
            x0 = 16
            x1 = page.rect.width - 16
        else:
            x0 = 16 if cr.x0 < page.rect.width / 2 else page.rect.width / 2
            x1 = (
                page.rect.width / 2
                if cr.x1 < page.rect.width / 2 + 20
                else page.rect.width - 16
            )
        prior = [
            r.y1
            for r, t in blocks
            if r.y1 < cr.y0 - 8
            and r.x0 < x1
            and r.x1 > x0
            and len(t) > 140
            and not re.match(r"^(Figure|Fig\.|\(?[a-i]\))", t)
        ]
        lower = max(prior, default=page.rect.y0 + 24)
        region = fitz.Rect(x0, lower, x1, cr.y0 - 3)
        relevant = [
            r
            for r in inks
            if region.intersects(r)
            and r.y1 <= cr.y0 + 2
            and (r & region).get_area() > r.get_area() * 0.5
        ]
        if not relevant:
            continue
        union = fitz.Rect(relevant[0])
        for r in relevant[1:]:
            union |= r
        if union.height < 25 or union.width < 40:
            continue
        region = fitz.Rect(
            max(12, union.x0 - 18),
            max(lower, union.y0 - 16),
            min(page.rect.width - 12, union.x1 + 18),
            cr.y0 - 3,
        )
        exclusions = [
            r for r, t in blocks if r == cr or (len(t) > 180 and not region.contains(r))
        ]
        bbox = snap(page, region, exclusions)
        label = re.match(r"^(?:Figure|Fig\.?)\s*(\d+)", caption, re.I).group(1)
        if not any(
            fitz.Rect(c.bbox).intersects(fitz.Rect(bbox)) and c.label == f"Fig. {label}"
            for c in crops
        ):
            crops.append(Crop(page.number + 1, bbox, f"Fig. {label}", caption))
    return crops


def layout_type(doc):
    votes = []
    for page in list(doc)[1:4]:
        blocks = [r for r, t in text_blocks(page) if len(t) > 150]
        votes.append(sum(r.width < page.rect.width * 0.48 for r in blocks) >= 2)
    return "double" if any(votes) else "single"


def pdf_title(doc):
    title = (doc.metadata or {}).get("title", "").strip()
    if title and not title.lower().endswith((".tex", ".pdf")):
        return title[:500]
    spans = [
        s
        for b in doc[0].get_text("dict")["blocks"]
        for l in b.get("lines", [])
        for s in l["spans"]
        if len(s["text"].strip()) > 6 and s["bbox"][1] < doc[0].rect.height * 0.5
    ]
    if not spans:
        return "Untitled paper"
    size = max(s["size"] for s in spans)
    return " ".join(s["text"] for s in spans if s["size"] >= size - 0.6)[:500]


def render(doc, crop):
    page = doc[crop.page - 1]
    rect = fitz.Rect(crop.bbox) & page.rect
    if rect.width < 5 or rect.height < 5:
        raise ValueError("裁切区域过小")
    scale = min(450 / 72, (24_000_000 / max(rect.get_area(), 1)) ** 0.5)
    pix = page.get_pixmap(
        matrix=fitz.Matrix(scale, scale), clip=rect, colorspace=fitz.csRGB, alpha=False
    )
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    if crop.raw:
        try:
            rawdoc = fitz.open(stream=crop.raw, filetype="pdf")
            rawpage = rawdoc[0]
            rawscale = min(
                450 / 72, (24_000_000 / max(rawpage.rect.get_area(), 1)) ** 0.5
            )
            rp = rawpage.get_pixmap(
                matrix=fitz.Matrix(rawscale, rawscale),
                colorspace=fitz.csRGB,
                alpha=False,
            )
            image = Image.frombytes("RGB", (rp.width, rp.height), rp.samples)
            rawdoc.close()
        except Exception:
            crop.raw = None
    out = io.BytesIO()
    image.save(out, "WEBP", quality=93, method=4)
    hd = out.getvalue()
    thumb = image.copy()
    thumb.thumbnail((480, 4800))
    out = io.BytesIO()
    thumb.save(out, "WEBP", quality=83)
    thumb_bytes = out.getvalue()
    small = image.copy()
    small.thumbnail((32, 32))
    bh = blurhash.encode(np.asarray(small), components_x=4, components_y=3)
    sliced = fitz.open()
    target = sliced.new_page(width=rect.width, height=rect.height)
    target.show_pdf_page(target.rect, doc, crop.page - 1, clip=rect)
    raw = crop.raw or sliced.tobytes(garbage=4, deflate=True)
    sliced.close()
    fonts = sorted(
        set(
            re.sub(r"^[A-Z]{6}\+", "", s["font"])
            for b in page.get_text("dict", clip=rect)["blocks"]
            for l in b.get("lines", [])
            for s in l["spans"]
        )
    )
    subs = crop.subitems or locate_subitems(page, rect, image)
    for sub in subs:
        x0, y0, x1, y1 = sub["norm_bbox"]
        sub["palette"] = extract_palette(
            image.crop(
                (
                    int(x0 * image.width),
                    int(y0 * image.height),
                    int(x1 * image.width),
                    int(y1 * image.height),
                )
            )
        )
    return {
        "hd": hd,
        "thumb": thumb_bytes,
        "raw": raw,
        "width": image.width,
        "height": image.height,
        "aspect_ratio": image.width / image.height,
        "palette": extract_palette(image),
        "fonts": fonts,
        "blurhash": bh,
        "subitems": subs,
    }


def locate_subitems(page, rect, image):
    anchors = []
    for r, t in text_blocks(page):
        if not rect.intersects(r):
            continue
        for label in re.findall(r"(?:^|\s)\(([a-i])\)", t):
            anchors.append((label, r))
    anchors = sorted({a[0]: a for a in anchors}.values())
    if len(anchors) < 2:
        return []
    # Anchor labels at each panel's baseline. Midpoints split columns and rows.
    rows = []
    for label, r in sorted(anchors, key=lambda a: a[1].y0):
        row = next((row for row in rows if abs(row[0][1].y0 - r.y0) < 25), None)
        if row is None:
            rows.append([(label, r)])
        else:
            row.append((label, r))
    subs = []
    top = rect.y0
    for row in rows:
        row.sort(key=lambda a: a[1].x0)
        bottom = min(rect.y1, max(r.y1 for _, r in row) + 5)
        for i, (label, r) in enumerate(row):
            centers = [(v.x0 + v.x1) / 2 for _, v in row]
            left = rect.x0 if i == 0 else (centers[i - 1] + centers[i]) / 2
            right = rect.x1 if i == len(row) - 1 else (centers[i] + centers[i + 1]) / 2
            box = [
                max(0, (left - rect.x0) / rect.width),
                max(0, (top - rect.y0) / rect.height),
                min(1, (right - rect.x0) / rect.width),
                min(1, (bottom - rect.y0) / rect.height),
            ]
            if box[2] > box[0] and box[3] > box[1]:
                subs.append(
                    {
                        "id": label,
                        "label": f"({label})",
                        "caption": "",
                        "norm_bbox": box,
                    }
                )
        top = bottom
    return subs
