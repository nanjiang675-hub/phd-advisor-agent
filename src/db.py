from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone

from .config import DB_PATH, ROOT


DISCOVERY_DATA_VERSION = "2"


class ClosingConnection(sqlite3.Connection):
    """Commit/rollback and close when used by the project's with-blocks."""

    def __exit__(self, exc_type, exc_value, traceback):
        result = super().__exit__(exc_type, exc_value, traceback)
        self.close()
        return result


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata(
 key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS schools(
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, rank INTEGER,
 ranking_source TEXT, ranking_year TEXT, website TEXT, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS departments(
 id INTEGER PRIMARY KEY, school_id INTEGER NOT NULL REFERENCES schools(id),
 name TEXT NOT NULL, url TEXT NOT NULL UNIQUE, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS pages(
 url TEXT PRIMARY KEY, school_id INTEGER REFERENCES schools(id), department_id INTEGER REFERENCES departments(id),
 kind TEXT NOT NULL DEFAULT 'directory', status TEXT DEFAULT 'pending', http_status INTEGER,
 content_hash TEXT, title TEXT, text_content TEXT, changed_at TEXT, fetched_at TEXT,
 next_check_at TEXT, attempts INTEGER DEFAULT 0, error TEXT);
CREATE TABLE IF NOT EXISTS page_versions(
 id INTEGER PRIMARY KEY, url TEXT NOT NULL, content_hash TEXT NOT NULL, title TEXT,
 text_content TEXT, captured_at TEXT NOT NULL, UNIQUE(url,content_hash));
CREATE TABLE IF NOT EXISTS faculty(
 id INTEGER PRIMARY KEY, canonical_key TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 school_id INTEGER REFERENCES schools(id), department_id INTEGER REFERENCES departments(id),
 title TEXT, email TEXT, profile_url TEXT, research_text TEXT,
 admissions_status TEXT DEFAULT 'unknown', admissions_evidence TEXT, evidence_url TEXT,
 evidence_checked_at TEXT, verification_source TEXT DEFAULT 'rules', verification_confidence REAL DEFAULT 0,
 match_score REAL DEFAULT 0, match_reasons TEXT, contact_status TEXT DEFAULT 'not_contacted', updated_at TEXT);
CREATE TABLE IF NOT EXISTS review_queue(
 id INTEGER PRIMARY KEY, faculty_id INTEGER REFERENCES faculty(id), reason TEXT, payload TEXT,
 status TEXT DEFAULT 'pending', created_at TEXT, UNIQUE(faculty_id,reason,status));
CREATE TABLE IF NOT EXISTS runs(
 id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT, status TEXT,
 pages_ok INTEGER DEFAULT 0, pages_failed INTEGER DEFAULT 0, faculty_found INTEGER DEFAULT 0,
 changed_pages INTEGER DEFAULT 0, model_calls INTEGER DEFAULT 0, estimated_cost REAL DEFAULT 0, note TEXT);
CREATE INDEX IF NOT EXISTS idx_pages_due ON pages(status,next_check_at);
CREATE INDEX IF NOT EXISTS idx_faculty_score ON faculty(match_score DESC);
"""


def init_db(load_inputs: bool = False) -> None:
    with connect() as db:
        db.executescript(SCHEMA)
        _migrate_legacy(db)
        _ensure_discovery_data_version(db)
    if load_inputs:
        import_schools()


def _ensure_discovery_data_version(db: sqlite3.Connection) -> None:
    """Discard discovery output created before strict domain validation."""
    row = db.execute(
        "SELECT value FROM metadata WHERE key='discovery_data_version'"
    ).fetchone()
    if row and row[0] == DISCOVERY_DATA_VERSION:
        return
    db.execute("DELETE FROM review_queue")
    db.execute("DELETE FROM faculty")
    db.execute("DELETE FROM page_versions")
    db.execute("DELETE FROM pages")
    db.execute("DELETE FROM departments")
    db.execute("DELETE FROM runs")
    db.execute(
        "INSERT INTO metadata(key,value) VALUES('discovery_data_version',?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (DISCOVERY_DATA_VERSION,),
    )


def _columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}


def _migrate_legacy(db: sqlite3.Connection) -> None:
    """Upgrade the original prototype database in place without deleting records."""
    page_cols=_columns(db,"pages")
    for name,kind in (("school_id","INTEGER"),("department_id","INTEGER"),("kind","TEXT DEFAULT 'directory'"),("changed_at","TEXT")):
        if name not in page_cols: db.execute(f"ALTER TABLE pages ADD COLUMN {name} {kind}")
    faculty_cols=_columns(db,"faculty")
    additions=(("canonical_key","TEXT"),("school_id","INTEGER"),("department_id","INTEGER"),("verification_source","TEXT DEFAULT 'rules'"),("verification_confidence","REAL DEFAULT 0"),("updated_at","TEXT"))
    for name,kind in additions:
        if name not in faculty_cols: db.execute(f"ALTER TABLE faculty ADD COLUMN {name} {kind}")
    run_cols=_columns(db,"runs")
    for name,kind in (("faculty_found","INTEGER DEFAULT 0"),("changed_pages","INTEGER DEFAULT 0"),("model_calls","INTEGER DEFAULT 0"),("estimated_cost","REAL DEFAULT 0")):
        if name not in run_cols: db.execute(f"ALTER TABLE runs ADD COLUMN {name} {kind}")
    # Link prototype text school/department values to normalized records.
    faculty_cols=_columns(db,"faculty")
    if "school" in faculty_cols:
        for r in db.execute("SELECT id,name,school,department,profile_url FROM faculty WHERE school_id IS NULL").fetchall():
            db.execute("INSERT OR IGNORE INTO schools(name,ranking_source,ranking_year) VALUES(?,'US News','unverified')",(r["school"] or "Unknown",))
            sid=db.execute("SELECT id FROM schools WHERE name=?",(r["school"] or "Unknown",)).fetchone()[0]
            dep=r["department"] or "Unknown"
            dep_url=(r["profile_url"] or f"legacy://{sid}/{r['id']}")+"#department"
            db.execute("INSERT OR IGNORE INTO departments(school_id,name,url) VALUES(?,?,?)",(sid,dep,dep_url))
            did=db.execute("SELECT id FROM departments WHERE url=?",(dep_url,)).fetchone()[0]
            key=f"{sid}:"+"".join(c for c in (r["name"] or "").lower() if c.isalpha())
            db.execute("UPDATE faculty SET school_id=?,department_id=?,canonical_key=?,updated_at=COALESCE(updated_at,?) WHERE id=?",(sid,did,key,utcnow(),r["id"]))
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_faculty_canonical ON faculty(canonical_key)")


def import_schools() -> None:
    path = ROOT / "input" / "schools.csv"
    if not path.exists():
        return
    with path.open(encoding="utf-8-sig", newline="") as f, connect() as db:
        for row in csv.DictReader(f):
            school = (row.get("school") or "").strip()
            url = (row.get("department_url") or "").strip()
            if not school or "示例" in school:
                continue
            rank = int(row["rank"]) if (row.get("rank") or "").isdigit() else None
            db.execute("""INSERT INTO schools(name,rank,ranking_source,ranking_year,website) VALUES(?,?,?,?,?)
                ON CONFLICT(name) DO UPDATE SET rank=excluded.rank,ranking_source=excluded.ranking_source,
                ranking_year=excluded.ranking_year,
                website=COALESCE(NULLIF(excluded.website,''),schools.website)""",
                (school, rank, row.get("ranking_source","US News"), row.get("ranking_year"),row.get("website")))
            sid = db.execute("SELECT id FROM schools WHERE name=?", (school,)).fetchone()[0]
            if url:
                db.execute("INSERT OR IGNORE INTO departments(school_id,name,url) VALUES(?,?,?)", (sid, row.get("department",""), url))
                did = db.execute("SELECT id FROM departments WHERE url=?", (url,)).fetchone()[0]
                db.execute("INSERT OR IGNORE INTO pages(url,school_id,department_id,kind) VALUES(?,?,?,'directory')", (url,sid,did))
    domain_path = ROOT / "input" / "official_domains.csv"
    if domain_path.exists():
        with domain_path.open(encoding="utf-8-sig", newline="") as f, connect() as db:
            for row in csv.DictReader(f):
                school = (row.get("school") or "").strip()
                website = (row.get("website") or "").strip()
                if school and website:
                    db.execute(
                        "UPDATE schools SET website=? WHERE name=?",
                        (website, school),
                    )
