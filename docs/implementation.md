# Implementation notes

## Architecture

Browser → Nginx/Let's Encrypt → Next.js frontend + FastAPI backend → SQLite WAL and WebDAV. Cloudflare publishes a DNS-only A record. All service and image processing compute stays on this Linux host.

Public figure responses contain only public paper metadata. Sessions use signed JWT cookies plus server-side revocation records, Argon2 password hashing and role checks. All private resources are checked against their owner. State-changing browser requests verify Origin/Sec-Fetch-Site, authentication is rate limited, and private endpoints use `Cache-Control: private, no-store`. Nginx overwrites client forwarding headers before passing traffic to the loopback-bound backend.

Downloads accept a fixed scholarly host allowlist and check redirects individually. TeX archives are inspected in memory with file-count and decompressed-size bounds; paths and symlinks are never extracted, and no TeX code is executed. PDFs are capped at 50MB, 150 pages and 24MP render surfaces. WebDAV paths reject traversal. Stage budgets use shared kernel file locks across HTTP, CLI and scheduler processes. Duplicate document identities and figure edits use separate resource locks; library rebuilds use an exclusive maintenance lock. CPU work runs in isolated short-lived subprocesses.

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

## Short hostname migration — 2026-11-14

Primary URL changed to `https://fig.zhcanfly.com`. The new Cloudflare A record points to the same local server with `proxied=false`; a dedicated Let's Encrypt certificate is installed. Both HTTP and HTTPS requests to `figprsim.zhcanfly.com` return 308 to the new host while preserving the path and query string. The old hostname and its certificate remain available for these redirects (`deploy/nginx.legacy.conf`).

The backend public origin, private local configuration, administrator access file, Compose environment and deployment documentation now use the short hostname. The backend was recreated successfully without changing the database. Live checks passed for public pages, health, authenticated login, Secure/HttpOnly cookies, cross-origin write rejection, and path/query-preserving redirects. A browser smoke check verified the old-to-new navigation and gallery image loading.


## Staged concurrency — 2026-11-14

Limits: metadata 4, downloads 3, papers 2, CPU processes 2 with one inference thread each, vision requests 3, WebDAV writes 4, rendered/in-flight figures 6 (3 per paper). Waiting duplicate papers do not occupy admission slots. Original PDF transfer overlaps source parsing/layout computation; per-figure downstream work proceeds independently with bounded workers and backpressure. File uploads finish before publication; per-paper manifest locks prevent stale snapshots from overwriting newer figures. Stable figure asset IDs make retries idempotent.

Transient HTTP statuses and transport failures retry within configured bounds. Interrupted/failed ingestion marks both job and paper failed and preserves published figures. The next submission resumes them; sync only skips completed papers. Native child cancellation is awaited before releasing CPU capacity, and parent death terminates child processes. Job admission is atomic, with a global pending cap and per-user cap excluding internal batch children.

Added regression coverage for cross-process limits, cancellation and process reaping, independent slow/fast paper progress, out-of-order figure completion, manifest completeness, concurrent duplicate submissions, partial failure/resume, HTTP retries and atomic admission. Pipeline status is exposed to admins via `/api/admin/pipeline`, the admin UI and CLI.

Concurrency rollout verification: 25 backend tests passed, TypeScript and Docker builds passed, and all four existing browser workflows passed on the production hostname. The admin stage monitor and shared budgets were checked live. Recovery of the interrupted real-paper import was started separately; live progress remains visible in the jobs UI.


## figprism.ai4any.com TLS deployment (2026-11-14)

The primary public URL is now `https://figprism.ai4any.com`. DNS resolves directly to this server. A dedicated Nginx virtual host proxies the existing production frontend (3100) and API (8100), with unbuffered SSE and the existing upload limit. Let's Encrypt issued a certificate expiring 2027-02-12; the existing enabled `certbot.timer` handles renewal through the Nginx plugin. Both previous domains redirect HTTP/HTTPS requests to the new host, preserving paths and query strings.

The running backend has active ingestion/backfill jobs. To avoid restarting it, the new virtual host maps only the exact new HTTPS Origin to the existing backend CSRF origin (`https://fig.zhcanfly.com`); all other origins pass through unchanged. Keep this mapping paired with the existing Compose origin. No application source or in-flight job was changed for the domain cutover.

Verified with TLS validation enabled: homepage and workspace routes, API health and figure listing, HTTP-to-HTTPS redirects, both legacy HTTPS redirects, real QA-account login, Secure/HttpOnly session cookies, logout, and rejection of a foreign Origin. A Chromium browser also rendered the homepage and completed login without page errors. Thumbnail, HD WebP and vector PDF requests returned 200, and SSE delivered an event through Nginx.

`certbot renew --cert-name figprism.ai4any.com --dry-run --non-interactive` passed the HTTP-01 challenge and reported no renewal failures.


## Paper grouping and warm-paper UI — PRD v2.1

The grouped feed filters figures before SQL aggregation/pagination. A page contains at most 16 paper groups by default, each with all matched figures, a priority-selected hero, natural figure-number ordering, dimensions/BlurHash/palette data. Flat mode remains available. Sibling navigation fetches all figures for the current paper independently of the feed filter. Bulk collection inserts verify ownership, validate all IDs before writing, deduplicate IDs and retain existing notes/focus.

The default Deck view preloads thumbnails as a paper enters the viewport and switches the hero, figure label and palette on hover/focus. It provides an inline two-column expansion. Swimlane uses equal-height horizontally scrolling/draggable paper rows with atomic whole-group save. Inspector thumbnails and up/down shortcuts navigate siblings. View and paper-blend preferences persist locally.

Warm semantic tokens replace cold canvas/surface values and pale readable text. Paper blending is applied only to displayed images; original asset bytes and offscreen canvas RGB reads remain untouched. Tests compare raw canvas samples with the loupe before and after toggling blend.

Verified in an isolated copy of the index: 30 backend tests, TypeScript, production build and eight Playwright workflows passed, including filter-before-group pagination, hero priority/natural order, inline expansion, hover/color linkage, sibling keys, view persistence, bulk ownership, mobile overflow and raw-color fidelity.

The v2.1 rollout uses a parallel Compose project, `figprism-v2` (loopback API 8101 and web 3111). Nginx still serves the current canonical `figprism.ai4any.com` hostname and retains the established exact Origin mapping. Old containers and accepted background jobs keep running. A startup exemption list protects legacy batch IDs and their children; unrelated abandoned web jobs are still recovered as failed. An identity-checked systemd drain task stops only the recorded old containers after jobs and attached CLI processes are idle, without removing data or logs.

Final production acceptance: all eight Playwright workflows passed on `https://figprism.ai4any.com` after the switch, including color-fidelity assertions with blending on/off. Live grouped feed, canonical-origin login, CSRF rejection, stage monitoring and continued legacy-job progress were verified. Temporary QA accounts were removed and isolated preview processes stopped. The recovered Absolute Zero import completed with 39 figures; figures whose vision checks were unavailable remain flagged for review.
