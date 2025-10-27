from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from typing import Optional, Tuple


def normalize_label(label: str) -> str:
    return (label or "").strip().lower()


def open_registry(path: str, enable_fts: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    init_schema(conn, enable_fts=enable_fts)
    return conn


def init_schema(conn: sqlite3.Connection, enable_fts: bool = False) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS entities (
            canonical_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            normalized_label TEXT NOT NULL,
            primary_name TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_type_label ON entities(type, normalized_label);

        CREATE TABLE IF NOT EXISTS aliases (
            canonical_id TEXT NOT NULL,
            alias TEXT NOT NULL,
            UNIQUE(canonical_id, alias)
        );

        CREATE TABLE IF NOT EXISTS external_ids (
            canonical_id TEXT NOT NULL,
            source TEXT NOT NULL,
            external_id TEXT NOT NULL,
            UNIQUE(source, external_id)
        );
        """
    )
    if enable_fts:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(primary_name, content='entities', content_rowid='rowid')")
        # Populate if empty
        conn.execute("INSERT INTO entities_fts(rowid, primary_name) SELECT rowid, COALESCE(primary_name,'') FROM entities WHERE rowid NOT IN (SELECT rowid FROM entities_fts)")
    conn.commit()


def deterministic_id(ent_type: str, normalized_label: str) -> str:
    # Deterministic UUIDv5 based on type|normalized_label
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"combo://entity/{(ent_type or '').upper()}|{normalize_label(normalized_label)}"))


def get_or_create_canonical(conn: sqlite3.Connection, ent_type: str, normalized_label: str, primary_name: Optional[str] = None) -> str:
    ent_type_u = (ent_type or "").upper()
    norm = normalize_label(normalized_label)
    cur = conn.execute(
        "SELECT canonical_id FROM entities WHERE type=? AND normalized_label=?",
        (ent_type_u, norm),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    can_id = deterministic_id(ent_type_u, norm)
    conn.execute(
        "INSERT OR IGNORE INTO entities(canonical_id, type, normalized_label, primary_name) VALUES (?,?,?,?)",
        (can_id, ent_type_u, norm, primary_name),
    )
    if primary_name:
        try:
            conn.execute("INSERT OR IGNORE INTO aliases(canonical_id, alias) VALUES (?,?)", (can_id, primary_name))
        except Exception:
            pass
    conn.commit()
    return can_id


def add_alias(conn: sqlite3.Connection, canonical_id: str, alias: str) -> None:
    if not alias:
        return
    conn.execute("INSERT OR IGNORE INTO aliases(canonical_id, alias) VALUES (?,?)", (canonical_id, alias))
    conn.commit()


def add_external_id(conn: sqlite3.Connection, canonical_id: str, source: str, external_id: str) -> None:
    if not external_id:
        return
    conn.execute(
        "INSERT OR IGNORE INTO external_ids(canonical_id, source, external_id) VALUES (?,?,?)",
        (canonical_id, source, external_id),
    )
    conn.commit()

