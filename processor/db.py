# -*- coding: utf-8 -*-
"""SQLite 存储层。"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  aweme_id TEXT PRIMARY KEY,
  kind TEXT DEFAULT 'video',
  title TEXT DEFAULT '',
  author_name TEXT DEFAULT '',
  author_id TEXT DEFAULT '',
  url TEXT DEFAULT '',
  share_url TEXT DEFAULT '',
  cover_url TEXT DEFAULT '',
  cover_path TEXT DEFAULT '',
  images_json TEXT DEFAULT '[]',
  published_at TEXT DEFAULT '',
  duration_sec REAL DEFAULT 0,
  first_seen_at TEXT DEFAULT '',
  last_seen_at TEXT DEFAULT '',
  in_favorites INTEGER DEFAULT 0,
  in_watch_later INTEGER DEFAULT 0,
  in_bridge INTEGER DEFAULT 0,
  folders TEXT DEFAULT '[]',
  source TEXT DEFAULT '',
  status TEXT DEFAULT '',
  status_override TEXT,
  category TEXT DEFAULT '',
  category_override TEXT,
  tags TEXT DEFAULT '[]',
  tags_override TEXT,
  starred INTEGER DEFAULT 0,
  starred_override INTEGER,
  deep_state TEXT DEFAULT '',
  transcript_path TEXT DEFAULT '',
  note_path TEXT DEFAULT '',
  last_auto TEXT DEFAULT '{}',
  updated_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  started_at TEXT DEFAULT '',
  ended_at TEXT DEFAULT '',
  mode TEXT DEFAULT '',
  partial INTEGER DEFAULT 0,
  new_count INTEGER DEFAULT 0,
  updated_count INTEGER DEFAULT 0,
  unchanged_count INTEGER DEFAULT 0,
  left_count INTEGER DEFAULT 0,
  uncategorized_count INTEGER DEFAULT 0,
  cover_ok INTEGER DEFAULT 0,
  cover_fail INTEGER DEFAULT 0,
  notes_written INTEGER DEFAULT 0,
  notes_unchanged INTEGER DEFAULT 0,
  raw_dir TEXT DEFAULT '',
  error TEXT DEFAULT ''
);
"""

ITEM_FIELDS = [
    "aweme_id",
    "kind",
    "title",
    "author_name",
    "author_id",
    "url",
    "share_url",
    "cover_url",
    "cover_path",
    "images_json",
    "published_at",
    "duration_sec",
    "first_seen_at",
    "last_seen_at",
    "in_favorites",
    "in_watch_later",
    "in_bridge",
    "folders",
    "source",
    "status",
    "status_override",
    "category",
    "category_override",
    "tags",
    "tags_override",
    "starred",
    "starred_override",
    "deep_state",
    "transcript_path",
    "note_path",
    "last_auto",
    "updated_at",
]


def connect(db_path):
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    cols = {row[1] for row in con.execute("PRAGMA table_info(items)")}
    if "in_watch_later" not in cols:
        con.execute("ALTER TABLE items ADD COLUMN in_watch_later INTEGER DEFAULT 0")
        con.commit()
    return con


def get_item(con, aweme_id):
    return con.execute("SELECT * FROM items WHERE aweme_id = ?", (str(aweme_id),)).fetchone()


def all_items(con):
    return con.execute("SELECT * FROM items ORDER BY first_seen_at DESC, aweme_id DESC").fetchall()


def insert_item(con, rec):
    fields = [f for f in ITEM_FIELDS if f in rec]
    placeholders = ",".join("?" for _ in fields)
    sql = f"INSERT INTO items ({','.join(fields)}) VALUES ({placeholders})"
    con.execute(sql, [rec[f] for f in fields])
    con.commit()


def set_fields(con, aweme_id, **fields):
    allowed = {f: v for f, v in fields.items() if f in ITEM_FIELDS}
    if not allowed:
        return
    cols = ",".join(f"{k}=?" for k in allowed)
    con.execute(f"UPDATE items SET {cols} WHERE aweme_id = ?", [*allowed.values(), str(aweme_id)])
    con.commit()


def tags_of(row):
    try:
        return json.loads(row["tags"] or "[]")
    except Exception:
        return []


def override_tags_of(row):
    if row["tags_override"] is None:
        return None
    try:
        return json.loads(row["tags_override"] or "[]")
    except Exception:
        return None


def folders_of(row):
    try:
        return json.loads(row["folders"] or "[]")
    except Exception:
        return []


def insert_run(con, row):
    cols = [
        "id",
        "started_at",
        "ended_at",
        "mode",
        "partial",
        "new_count",
        "updated_count",
        "unchanged_count",
        "left_count",
        "uncategorized_count",
        "cover_ok",
        "cover_fail",
        "notes_written",
        "notes_unchanged",
        "raw_dir",
        "error",
    ]
    values = [row.get(c) for c in cols]
    con.execute(f"INSERT OR REPLACE INTO runs ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", values)
    con.commit()
