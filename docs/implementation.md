# Implementation notes

## Architecture

Browser → Nginx/Let's Encrypt → Next.js frontend + FastAPI backend → SQLite WAL and WebDAV. Cloudflare publishes a DNS-only A record. All service and image processing compute stays on this Linux host.

Public figure responses contain only public paper metadata. Sessions use signed JWT cookies plus server-side revocation records, Argon2 password hashing and role checks. All private resources are checked against their owner. State-changing browser requests verify Origin/Sec-Fetch-Site, authentication is rate limited, and private endpoints use `Cache-Control: private, no-store`. Nginx overwrites client forwarding headers before passing traffic to the loopback-bound backend.

Downloads accept a fixed scholarly host allowlist and check redirects individually. TeX archives are inspected in memory with file-count and decompressed-size bounds; paths and symlinks are never extracted, and no TeX code is executed. PDFs are capped at 50MB, 150 pages and 24MP render surfaces. WebDAV paths reject traversal. Shared ingestion uses an advisory process lock to coordinate HTTP jobs, CLI ingestion and the daily scheduler.

Assets use content-versioned paths on WebDAV. New crop assets are uploaded before publishing a SQLite row and SSE event. The source PDF and metadata.json remain remotely recoverable. A stale version request returns 404 instead of caching new bytes under an old URL. Thumbnails are mirrored locally; HD and PDF cache eviction uses least-recently-touched order. Slow WebDAV writes stream in 32KB chunks, retry transport failures twice, and have bounded per-attempt durations.

## Figure processing

TeX source figures preserve original vector PDFs when a single includegraphics represents the whole figure. Composite figures retain their paper layout. DocLayout-YOLO provides initial regions; actual PDF drawing, image and text geometry refines boundaries while excluding body text, captions and tables. Caption-based geometry supplements missed panels. OpenCV matches native sub-assets to complete figures; PDF label anchors provide a fallback. Low-confidence results remain reviewable.

Colors are clustered in OKLab and paired by OKLCH hue/lightness. Near-white backgrounds and neutral axes are separated. Pale chromatic fills are deliberately retained below the usual chroma cutoff; dominant stroke colors take precedence over rare anti-aliasing transition colors.

## Primary references

- [Next.js standalone output](https://nextjs.org/docs/app/api-reference/config/next-config-js/output): traced deployment artifacts and server.js; frontend keeps framework-generated agent guidance and reads bundled version-matched documentation.
- [PyMuPDF page API](https://pymupdf.readthedocs.io/en/latest/page.html): get_drawings, get_pixmap and show_pdf_page for geometry and vector clipping.
- [DocLayout-YOLO upstream](https://github.com/opendatalab/DocLayout-YOLO) and [ONNX conversion repository](https://huggingface.co/wybxc/DocLayout-YOLO-DocStructBench-onnx): CPU inference artifact, pinned revision `ee7c3d744e5c47c58e267044ac825f95abe69653`, SHA-256 `fece9af02f618b603ff7921ccec6861d13e7e1f9830e091dfb7e8ad9311e5b21`. Model metadata declares AGPL-3.0; downloaded weights remain outside Git.
- [arXiv API manual](https://info.arxiv.org/help/api/user-manual.html): Atom metadata, query syntax and request pacing.
- [OpenReview data retrieval](https://docs.openreview.net/how-to-guides/data-retrieval-and-modification/how-to-get-all-notes-for-submissions-reviews-rebuttals-etc): accepted conference venue IDs. Submitted/rejected/workshop records are excluded.
- [DBLP publication search API](https://dblp.org/faq/How+to+use+the+dblp+search+API.html): exact normalized-title verification against main-conference records.

## Verification coverage

Backend tests exercise revoked sessions, invitation single use, cross-origin rejection, domain token boundaries, archive/path safety, vector/text retention, pale-fill/dark-stroke pairing, whole-composite retention, partial-ingest retry, duplicate detection, FTS search, immutable version isolation, collection ownership, export and private history. Browser tests exercise mobile overflow, keyboard search, filters, login, invalid uploads, board CRUD, protected administration, real image loading, palette code and real vector downloads.

## Deployment acceptance — 2026-11-14

- 15 backend tests passed; TypeScript checks and production builds passed.
- 4 Playwright scenarios passed against `https://figprsim.zhcanfly.com`, including mobile layout, real vector downloads, pixel picking, crop controls, saved notes and subfigure focus restoration.
- Nginx configuration validated; Let's Encrypt certificate issued through 2027-02-12. Existing certbot renewal handles renewal.
- Public pages and `/api/health` return 200; anonymous private resources return 401 and `private, no-store`; cross-origin writes return 403.
- Asset responses are versioned and immutable; SSE immediately yields an event-stream preamble without buffering; production session cookies include Secure and HttpOnly.
- Cloudflare record is DNS-only (`proxied=false`), A → `45.153.246.194`, TTL 300.
- Both containers start successfully; API health check passes. Daily sync timer is enabled. The initial real-paper import runs as `figprism-bootstrap.service` and continues independently of the development session.
- Temporary QA account and its private records were removed after verification; connectivity probe files were removed from WebDAV.

Runtime test reports and screenshots are in ignored `data/qa/`; private credentials are never part of deployment source or image layers.
