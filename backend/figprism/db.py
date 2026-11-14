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
CREATE TABLE IF NOT EXISTS invite_codes (code TEXT PRIMARY KEY, created_by INTEGER REFERENCES users(id), used_by INTEGER REFERENCES users(id), expires_at TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS domains (slug TEXT PRIMARY KEY, config TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS papers (
 id TEXT PRIMARY KEY, doc_uid TEXT UNIQUE NOT NULL, file_sha256 TEXT UNIQUE NOT NULL,
 title TEXT NOT NULL, authors TEXT NOT NULL DEFAULT '[]', abstract TEXT DEFAULT '',
 source_type TEXT DEFAULT 'upload', arxiv_id TEXT, venue TEXT DEFAULT 'Preprint', venue_year INTEGER,
 venue_tier TEXT, hf_upvotes INTEGER DEFAULT 0, layout_type TEXT DEFAULT 'single',
 source_urls TEXT DEFAULT '{}', domains TEXT DEFAULT '[]', webdav_pdf_path TEXT,
 ingest_status TEXT DEFAULT 'completed', uploaded_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS figures (
 id TEXT PRIMARY KEY, paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
 fig_label TEXT NOT NULL, page_number INTEGER NOT NULL, bbox TEXT NOT NULL,
 archetype TEXT DEFAULT 'Pipeline', span_type TEXT DEFAULT 'full', caption TEXT DEFAULT '',
 width INTEGER NOT NULL, height INTEGER NOT NULL, aspect_ratio REAL NOT NULL,
 blurhash TEXT, fonts TEXT DEFAULT '[]', palette TEXT NOT NULL, color_buckets TEXT DEFAULT '[]',
 subitems TEXT DEFAULT '[]', tikz_code TEXT, extract_method TEXT DEFAULT 'pdf_snap_crop',
 sub_tags TEXT DEFAULT '[]', confidence REAL DEFAULT 0, review_status TEXT DEFAULT 'needs_review',
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


def init_db(recover_jobs=False):
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA)
        columns = {r[1] for r in db.execute("PRAGMA table_info(figures)")}
        if "sub_tags" not in columns:
            db.execute("ALTER TABLE figures ADD COLUMN sub_tags TEXT DEFAULT '[]'")
        pcolumns = {r[1] for r in db.execute("PRAGMA table_info(papers)")}
        if "ingest_status" not in pcolumns:
            db.execute(
                "ALTER TABLE papers ADD COLUMN ingest_status TEXT DEFAULT 'completed'"
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
            db.execute(
                "UPDATE jobs SET status='failed', message='服务重启，请重试任务' WHERE status IN ('running','queued') AND user_id IS NOT NULL"
            )


def event(db, kind, payload):
    db.execute(
        "INSERT INTO events(kind,payload) VALUES(?,?)", (kind, json.dumps(payload))
    )
    db.execute(
        "DELETE FROM events WHERE id < (SELECT COALESCE(MAX(id),0)-2000 FROM events)"
    )
