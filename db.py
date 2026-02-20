"""SQLite schema and access for commitments, tasks, counters, streaks."""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

from config import DB_PATH


def _add_column_if_missing(cur, table: str, column: str, col_type: str):
    cur.execute(f"PRAGMA table_info({table})")
    existing = [row[1] for row in cur.fetchall()]
    if column not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def get_conn():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Raw Tumblr posts we've seen (to avoid re-processing)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tumblr_posts (
            id TEXT PRIMARY KEY,
            blog_name TEXT,
            body_text TEXT,
            created_at TEXT,
            fetched_at TEXT,
            processed INTEGER DEFAULT 0
        )
    """)
    _add_column_if_missing(cur, "tumblr_posts", "processed", "INTEGER DEFAULT 0")

    # Parsed commitments from posts
    cur.execute("""
        CREATE TABLE IF NOT EXISTS commitments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_post_id TEXT,
            raw_text TEXT NOT NULL,
            kind TEXT NOT NULL,
            task_description TEXT,
            duration_days INTEGER,
            duration_until TEXT,
            condition_text TEXT,
            start_date TEXT,
            end_date TEXT,
            created_at TEXT,
            status TEXT DEFAULT 'active',
            confidence REAL,
            current_streak INTEGER DEFAULT 0,
            best_streak INTEGER DEFAULT 0,
            last_completed_date TEXT,
            UNIQUE(source_post_id, raw_text)
        )
    """)
    # Migrations for existing DBs (new DBs get columns from CREATE TABLE above if we add them there)
    _add_column_if_missing(cur, "commitments", "status", "TEXT DEFAULT 'active'")
    _add_column_if_missing(cur, "commitments", "confidence", "REAL")
    _add_column_if_missing(cur, "commitments", "current_streak", "INTEGER DEFAULT 0")
    _add_column_if_missing(cur, "commitments", "best_streak", "INTEGER DEFAULT 0")
    _add_column_if_missing(cur, "commitments", "last_completed_date", "TEXT")

    # Reminders (one-off or recurring)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            commitment_id INTEGER,
            title TEXT NOT NULL,
            at_time TEXT,
            recurrence TEXT,
            next_due TEXT,
            done INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY (commitment_id) REFERENCES commitments(id)
        )
    """)

    # Daily schedule items (what to do on a given day)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schedule_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            commitment_id INTEGER,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            notes TEXT,
            completed INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY (commitment_id) REFERENCES commitments(id)
        )
    """)
    # Remove duplicate (date, title) rows so unique index can be created
    cur.execute(
        """DELETE FROM schedule_items WHERE id NOT IN (
            SELECT MIN(id) FROM schedule_items GROUP BY date, title
        )"""
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_items_date_title ON schedule_items(date, title)"
    )

    # Ongoing counters (e.g. "Day 47", "7 days locked")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS counters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            commitment_id INTEGER,
            name TEXT NOT NULL,
            current_value INTEGER DEFAULT 0,
            target_value INTEGER,
            unit TEXT,
            start_date TEXT,
            last_updated TEXT,
            created_at TEXT,
            FOREIGN KEY (commitment_id) REFERENCES commitments(id)
        )
    """)

    # Streaks (consecutive days done)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS streaks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            commitment_id INTEGER,
            name TEXT NOT NULL,
            current_streak INTEGER DEFAULT 0,
            longest_streak INTEGER DEFAULT 0,
            last_activity_date TEXT,
            created_at TEXT,
            FOREIGN KEY (commitment_id) REFERENCES commitments(id)
        )
    """)

    # Log of completed actions (for streak and counter updates)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            commitment_id INTEGER,
            action_type TEXT,
            date TEXT NOT NULL,
            notes TEXT,
            created_at TEXT,
            FOREIGN KEY (commitment_id) REFERENCES commitments(id)
        )
    """)

    # Punishment triggers (conditions that trigger a "punishment" reminder)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS punishment_triggers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            commitment_id INTEGER,
            condition_text TEXT,
            action_text TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT,
            FOREIGN KEY (commitment_id) REFERENCES commitments(id)
        )
    """)

    conn.commit()
    conn.close()


def now_iso():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
