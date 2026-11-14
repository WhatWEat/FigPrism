import json
import re
import os
import yaml
from .db import connect
from .config import get_settings

def all_domains(active=True):
    with connect() as db:
        rows = db.execute('SELECT config,is_active FROM domains' + (' WHERE is_active=1' if active else '')).fetchall()
    return [dict(json.loads(r['config']), is_active=bool(r['is_active'])) for r in rows]

def match_domains(text, configs=None):
    found = []
    for domain in configs if configs is not None else all_domains():
        strong = any(re.search(r'(?<!\w)' + re.escape(p) + r'(?!\w)', text, re.I) for p in domain.get('phrases', []))
        acronym = any(re.search(r'(?<!\w)' + re.escape(a) + r'(?!\w)', text) for a in domain.get('acronyms', []))
        excluded = any(p.lower() in text.lower() for p in domain.get('exclude_terms', []))
        if strong or (acronym and not excluded):
            found.append(domain['slug'])
    return found

def save_domains(configs):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        slugs = [c['slug'] for c in configs]
        for c in configs:
            db.execute('INSERT INTO domains VALUES(?,?,?) ON CONFLICT(slug) DO UPDATE SET config=excluded.config,is_active=excluded.is_active', (c['slug'], json.dumps(c, ensure_ascii=False), int(c.get('is_active', True))))
        for row in db.execute('SELECT slug FROM domains').fetchall():
            if row['slug'] not in slugs:
                db.execute('UPDATE domains SET is_active=0 WHERE slug=?', (row['slug'],))
        path = get_settings().domains_file
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(yaml.safe_dump(configs, allow_unicode=True, sort_keys=False))
        os.replace(tmp, path)
