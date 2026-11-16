from contextlib import contextmanager
import json
import sqlite3
import yaml
from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','user')), is_active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS sessions (jti TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id), expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS invite_codes (code TEXT PRIMARY KEY, created_by INTEGER REFERENCES users(id), used_by INTEGER REFERENCES users(id), expires_at TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, max_uses INTEGER NOT NULL DEFAULT 1, used_count INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS domains (slug TEXT PRIMARY KEY, config TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS papers (
 id TEXT PRIMARY KEY, doc_uid TEXT UNIQUE NOT NULL, file_sha256 TEXT UNIQUE NOT NULL,
 title TEXT NOT NULL, authors TEXT NOT NULL DEFAULT '[]', abstract TEXT DEFAULT '',
 source_type TEXT DEFAULT 'upload', arxiv_id TEXT, venue TEXT DEFAULT 'Preprint', venue_year INTEGER,
 venue_tier TEXT, hf_upvotes INTEGER DEFAULT 0, layout_type TEXT DEFAULT 'single',
 source_urls TEXT DEFAULT '{}', domains TEXT DEFAULT '[]', webdav_pdf_path TEXT,
 ingest_status TEXT DEFAULT 'completed', pdf_uploaded INTEGER NOT NULL DEFAULT 1, uploaded_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS figures (
 id TEXT PRIMARY KEY, paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
 fig_label TEXT NOT NULL, page_number INTEGER NOT NULL, bbox TEXT NOT NULL,
 archetype TEXT DEFAULT 'Pipeline', span_type TEXT DEFAULT 'full', caption TEXT DEFAULT '',
 width INTEGER NOT NULL, height INTEGER NOT NULL, aspect_ratio REAL NOT NULL,
 blurhash TEXT, fonts TEXT DEFAULT '[]', palette TEXT NOT NULL, color_buckets TEXT DEFAULT '[]',
 subitems TEXT DEFAULT '[]', tikz_code TEXT, extract_method TEXT DEFAULT 'pdf_snap_crop',
 sub_tags TEXT DEFAULT '[]', confidence REAL DEFAULT 0, review_status TEXT DEFAULT 'needs_review',
 macro_category TEXT, sub_type TEXT, primary_style TEXT, secondary_style TEXT,
 layout_topology TEXT, craft_badges_json TEXT DEFAULT '[]', chart_layout TEXT,
 style_confidence REAL, style_reason TEXT, taxonomy_locked INTEGER DEFAULT 0,
 asset_base TEXT NOT NULL, version_hash TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS figures_paper_idx ON figures(paper_id);
CREATE VIRTUAL TABLE IF NOT EXISTS figures_fts USING fts5(figure_id UNINDEXED, title, caption, fonts);
CREATE TRIGGER IF NOT EXISTS figure_delete_fts AFTER DELETE ON figures BEGIN DELETE FROM figures_fts WHERE figure_id=old.id; END;
CREATE TABLE IF NOT EXISTS collections (id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), name TEXT NOT NULL, description TEXT DEFAULT '', updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS collection_items (
 id TEXT PRIMARY KEY, collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
 figure_id TEXT NOT NULL REFERENCES figures(id) ON DELETE CASCADE, focused_subitem_id TEXT,
 user_note TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(collection_id, figure_id));
CREATE TABLE IF NOT EXISTS view_history (user_id INTEGER NOT NULL REFERENCES users(id), figure_id TEXT NOT NULL REFERENCES figures(id) ON DELETE CASCADE, viewed_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id,figure_id));
CREATE TABLE IF NOT EXISTS palette_history (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), figure_id TEXT NOT NULL REFERENCES figures(id) ON DELETE CASCADE, hex_code TEXT NOT NULL, copied_format TEXT DEFAULT 'HEX', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id), kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', progress INTEGER DEFAULT 0, message TEXT DEFAULT '', payload TEXT DEFAULT '{}', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS repair_queue (id TEXT PRIMARY KEY, figure_id TEXT NOT NULL REFERENCES figures(id), requested_by INTEGER REFERENCES users(id), status TEXT DEFAULT 'pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS asset_transfers (
 key TEXT PRIMARY KEY, digest TEXT NOT NULL, size INTEGER NOT NULL,
 content_type TEXT NOT NULL, synced INTEGER NOT NULL DEFAULT 0,
 attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0,
 last_error TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS asset_transfers_pending ON asset_transfers(synced,next_attempt);
CREATE TABLE IF NOT EXISTS cache_metrics (
 id INTEGER PRIMARY KEY CHECK(id=1), hits INTEGER NOT NULL DEFAULT 0,
 misses INTEGER NOT NULL DEFAULT 0, coalesced INTEGER NOT NULL DEFAULT 0,
 started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
INSERT OR IGNORE INTO cache_metrics(id) VALUES(1);
CREATE TABLE IF NOT EXISTS remote_assets (key TEXT PRIMARY KEY, size INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS resource_scan (
 id INTEGER PRIMARY KEY CHECK(id=1), status TEXT NOT NULL DEFAULT 'idle',
 started_at TEXT, completed_at TEXT, error TEXT NOT NULL DEFAULT '',
 directories INTEGER NOT NULL DEFAULT 0, files INTEGER NOT NULL DEFAULT 0);
INSERT OR IGNORE INTO resource_scan(id) VALUES(1);

"""

TAXONOMY_COLUMNS = (
    ("sub_tags", "TEXT DEFAULT '[]'"),
    ("macro_category", "TEXT"),
    ("sub_type", "TEXT"),
    ("primary_style", "TEXT"),
    ("secondary_style", "TEXT"),
    ("layout_topology", "TEXT"),
    ("craft_badges_json", "TEXT DEFAULT '[]'"),
    ("chart_layout", "TEXT"),
    ("style_confidence", "REAL"),
    ("style_reason", "TEXT"),
    ("taxonomy_locked", "INTEGER DEFAULT 0"),
)

TAXONOMY_POST_MIGRATION = """
CREATE INDEX IF NOT EXISTS idx_figures_macro_subtype ON figures(macro_category, sub_type);
CREATE INDEX IF NOT EXISTS idx_figures_method_style ON figures(macro_category, primary_style, layout_topology);
CREATE INDEX IF NOT EXISTS idx_figures_chart_layout ON figures(macro_category, chart_layout);
UPDATE figures SET
 macro_category = CASE
  WHEN archetype IN ('Teaser','Motivation','Pipeline','Framework','Micro-Mechanism') THEN 'method'
  WHEN archetype IN ('Curve','Bar','Scatter/Radar','Heatmap') THEN 'data_chart'
  WHEN archetype = 'Case Study' THEN 'case_study'
  ELSE 'method' END,
 sub_type = CASE
  WHEN archetype IN ('Teaser','Motivation') THEN 'concept_teaser'
  WHEN archetype IN ('Pipeline','Framework') THEN 'system_pipeline'
  WHEN archetype = 'Micro-Mechanism' THEN 'micro_mechanism'
  WHEN archetype = 'Curve' THEN 'line_scaling'
  WHEN archetype = 'Bar' THEN 'bar_ablation'
  WHEN archetype = 'Scatter/Radar' THEN 'scatter_pareto'
  WHEN archetype = 'Heatmap' THEN 'heatmap_matrix'
  WHEN archetype = 'Case Study' THEN 'qualitative_case'
  ELSE 'system_pipeline' END,
 craft_badges_json = COALESCE(craft_badges_json, '[]'),
 taxonomy_locked = COALESCE(taxonomy_locked, 0)
WHERE macro_category IS NULL OR sub_type IS NULL;
CREATE TRIGGER IF NOT EXISTS figure_taxonomy_defaults
AFTER INSERT ON figures
WHEN NEW.macro_category IS NULL OR NEW.sub_type IS NULL
BEGIN
 UPDATE figures SET
  macro_category = COALESCE(NEW.macro_category, CASE
   WHEN NEW.archetype IN ('Teaser','Motivation','Pipeline','Framework','Micro-Mechanism') THEN 'method'
   WHEN NEW.archetype IN ('Curve','Bar','Scatter/Radar','Heatmap') THEN 'data_chart'
   WHEN NEW.archetype = 'Case Study' THEN 'case_study'
   ELSE 'method' END),
  sub_type = COALESCE(NEW.sub_type, CASE
   WHEN NEW.archetype IN ('Teaser','Motivation') THEN 'concept_teaser'
   WHEN NEW.archetype IN ('Pipeline','Framework') THEN 'system_pipeline'
   WHEN NEW.archetype = 'Micro-Mechanism' THEN 'micro_mechanism'
   WHEN NEW.archetype = 'Curve' THEN 'line_scaling'
   WHEN NEW.archetype = 'Bar' THEN 'bar_ablation'
   WHEN NEW.archetype = 'Scatter/Radar' THEN 'scatter_pareto'
   WHEN NEW.archetype = 'Heatmap' THEN 'heatmap_matrix'
   WHEN NEW.archetype = 'Case Study' THEN 'qualitative_case'
   ELSE 'system_pipeline' END),
  craft_badges_json = COALESCE(NEW.craft_badges_json, '[]'),
  taxonomy_locked = COALESCE(NEW.taxonomy_locked, 0)
 WHERE id = NEW.id;
END;
"""


@contextmanager
def connect():
    db = sqlite3.connect(get_settings().data_dir / "figprism.db", timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=30000")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db(recover_jobs=False, preserve_job_ids=()):
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA)
        invite_columns = {r[1] for r in db.execute("PRAGMA table_info(invite_codes)")}
        if "max_uses" not in invite_columns:
            db.execute("ALTER TABLE invite_codes ADD COLUMN max_uses INTEGER NOT NULL DEFAULT 1")
        if "used_count" not in invite_columns:
            db.execute("ALTER TABLE invite_codes ADD COLUMN used_count INTEGER NOT NULL DEFAULT 0")
            db.execute("UPDATE invite_codes SET used_count=1 WHERE used_by IS NOT NULL")
        columns = {r[1] for r in db.execute("PRAGMA table_info(figures)")}
        for col_name, col_def in TAXONOMY_COLUMNS:
            if col_name not in columns:
                db.execute(f"ALTER TABLE figures ADD COLUMN {col_name} {col_def}")
        db.executescript(TAXONOMY_POST_MIGRATION)
        pcolumns = {r[1] for r in db.execute("PRAGMA table_info(papers)")}
        if "ingest_status" not in pcolumns:
            db.execute(
                "ALTER TABLE papers ADD COLUMN ingest_status TEXT DEFAULT 'completed'"
            )
        if "pdf_uploaded" not in pcolumns:
            db.execute(
                "ALTER TABLE papers ADD COLUMN pdf_uploaded INTEGER NOT NULL DEFAULT 1"
            )
        path = get_settings().domains_file
        if path.exists():
            for domain in yaml.safe_load(path.read_text()) or []:
                db.execute(
                    "INSERT INTO domains(slug,config,is_active) VALUES(?,?,?) ON CONFLICT(slug) DO UPDATE SET config=excluded.config,is_active=excluded.is_active",
                    (
                        domain["slug"],
                        json.dumps(domain, ensure_ascii=False),
                        int(domain.get("is_active", True)),
                    ),
                )
        # A process restart cannot leave uploads permanently marked as running.
        if recover_jobs:
            preserved = set(preserve_job_ids)
            for job in db.execute(
                "SELECT id,payload FROM jobs WHERE status IN ('running','queued') AND user_id IS NOT NULL"
            ).fetchall():
                parent = json.loads(job["payload"]).get("batch_id")
                if job["id"] not in preserved and parent not in preserved:
                    db.execute(
                        "UPDATE jobs SET status='failed',message='服务重启，请重试任务' WHERE id=?",
                        (job["id"],),
                    )


def event(db, kind, payload):
    db.execute(
        "INSERT INTO events(kind,payload) VALUES(?,?)", (kind, json.dumps(payload))
    )
    db.execute(
        "DELETE FROM events WHERE id < (SELECT COALESCE(MAX(id),0)-2000 FROM events)"
    )
