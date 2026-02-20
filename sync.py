"""Sync Tumblr posts -> DB, parse commitments -> reminders/schedules/counters/streaks."""
from datetime import datetime, timedelta
from typing import Optional

from config import TUMBLR_BLOG
from db import get_conn, init_db, now_iso
from parser import commitments_from_post_body, Commitment
from tumblr_client import fetch_posts


def _insert_post(cur, post: dict):
    cur.execute(
        """INSERT OR IGNORE INTO tumblr_posts (id, blog_name, body_text, created_at, fetched_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            post["id"],
            post.get("blog_name", ""),
            post.get("body_text", ""),
            post.get("created_at", ""),
            now_iso(),
        ),
    )


CONFIDENCE_AUTO_ACTIVATE = 0.8


def _insert_commitment(cur, c: Commitment, source_post_id: str, status: Optional[str] = None, confidence: Optional[float] = None) -> int:
    conf = confidence if confidence is not None else getattr(c, "confidence", 0.9)
    if status is None:
        status = "active" if conf >= CONFIDENCE_AUTO_ACTIVATE else "pending"
    cur.execute(
        """INSERT OR IGNORE INTO commitments
           (source_post_id, raw_text, kind, task_description, duration_days, duration_until,
            condition_text, start_date, end_date, created_at, status, confidence)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            source_post_id or None,
            c.raw_text,
            c.kind,
            c.task_description or "",
            c.duration_days,
            c.duration_until,
            c.condition_text,
            None,
            None,
            now_iso(),
            status,
            conf,
        ),
    )
    cur.execute("SELECT last_insert_rowid()")
    row = cur.fetchone()
    return row[0] if row else 0


def _ensure_commitment_id(cur, c: Commitment, source_post_id: str, status: Optional[str] = "active", confidence: Optional[float] = None) -> Optional[int]:
    cur.execute(
        "SELECT id FROM commitments WHERE source_post_id = ? AND raw_text = ?",
        (source_post_id or "", c.raw_text),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    _insert_commitment(cur, c, source_post_id, status=status, confidence=confidence if confidence is not None else getattr(c, "confidence", 0.9))
    cur.execute(
        "SELECT id FROM commitments WHERE source_post_id = ? AND raw_text = ?",
        (source_post_id or "", c.raw_text),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _derive_schedule_and_reminders(cur, c: Commitment, cid: int):
    """Create schedule_items and reminders from a commitment."""
    title = c.task_description or c.raw_text[:80]
    if c.kind == "reminder" and title:
        cur.execute(
            """INSERT INTO reminders (commitment_id, title, at_time, recurrence, next_due, done, created_at)
               VALUES (?, ?, ?, ?, ?, 0, ?)""",
            (cid, title, None, "daily" if c.duration_days else None, None, now_iso()),
        )
    if c.kind == "schedule" and title:
        # Add as a daily schedule template (assistant will expand per day)
        cur.execute(
            """INSERT OR IGNORE INTO schedule_items (commitment_id, date, title, notes, completed, created_at)
               VALUES (?, ?, ?, ?, 0, ?)""",
            (cid, "", title, c.raw_text, now_iso()),
        )


def _derive_counters(cur, c: Commitment, cid: int):
    if c.kind != "counter" and not (c.kind == "schedule" and c.counter_name):
        return
    name = c.counter_name or "days"
    target = c.counter_target or c.duration_days
    cur.execute(
        """INSERT OR IGNORE INTO counters (commitment_id, name, current_value, target_value, unit, start_date, last_updated, created_at)
           VALUES (?, ?, 0, ?, 'days', ?, ?, ?)""",
        (cid, name, target, None, now_iso(), now_iso()),
    )


def _derive_streaks(cur, c: Commitment, cid: int):
    if c.kind != "streak":
        return
    cur.execute(
        """INSERT OR IGNORE INTO streaks (commitment_id, name, current_streak, longest_streak, last_activity_date, created_at)
           VALUES (?, ?, 0, ?, NULL, ?)""",
        (cid, c.task_description or "streak", c.counter_target or 0, now_iso()),
    )


def _derive_punishment(cur, c: Commitment, cid: int):
    if c.kind != "punishment" or not c.condition_text or not c.punishment_action:
        return
    cur.execute(
        """INSERT INTO punishment_triggers (commitment_id, condition_text, action_text, active, created_at)
           VALUES (?, ?, ?, 1, ?)""",
        (cid, c.condition_text, c.punishment_action, now_iso()),
    )


def sync_tumblr(blog: Optional[str] = None, max_posts: int = 100) -> dict:
    """Fetch posts from Tumblr, store, then process only unprocessed posts. Returns {posts_fetched, new_commitments, pending_review, errors}."""
    init_db()
    blog = (blog or TUMBLR_BLOG or "").strip()
    result = {"posts_fetched": 0, "new_commitments": 0, "pending_review": 0, "errors": []}
    if not blog:
        result["errors"].append("Enter a Tumblr blog name (e.g. andrearose96)—works for any profile.")
        return result
    posts = fetch_posts(blog=blog, max_posts=max_posts)
    if not posts:
        result["errors"].append("No posts returned (check API keys and blog name)")
        return result
    if posts and "error" in posts[0]:
        result["errors"].append(posts[0].get("error", "Tumblr API error"))
        return result
    conn = get_conn()
    cur = conn.cursor()
    for post in posts:
        result["posts_fetched"] += 1
        _insert_post(cur, post)
    conn.commit()
    cur.execute("SELECT id, body_text FROM tumblr_posts WHERE processed = 0")
    unprocessed = cur.fetchall()
    for (pid, body_text) in unprocessed:
        body = body_text or ""
        for c, src_id in commitments_from_post_body(body, pid):
            cid = _ensure_commitment_id(cur, c, src_id, status=None)
            if cid:
                result["new_commitments"] += 1
                cur.execute("SELECT status FROM commitments WHERE id = ?", (cid,))
                r = cur.fetchone()
                if r and r[0] == "pending":
                    result["pending_review"] += 1
            _derive_schedule_and_reminders(cur, c, cid or 0)
            _derive_counters(cur, c, cid or 0)
            _derive_streaks(cur, c, cid or 0)
            _derive_punishment(cur, c, cid or 0)
        cur.execute("UPDATE tumblr_posts SET processed = 1 WHERE id = ?", (pid,))
    conn.commit()
    conn.close()
    return result


def generate_schedule_for_date(date_str: str) -> int:
    """Generate schedule rows for date from active daily commitments. Idempotent (INSERT OR IGNORE). Never touches done rows."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, commitment_id, title, notes FROM schedule_items si
           JOIN commitments c ON c.id = si.commitment_id AND c.status = 'active'
           WHERE si.date = ''"""
    )
    templates = cur.fetchall()
    inserted = 0
    for row in templates:
        cur.execute(
            """INSERT OR IGNORE INTO schedule_items (commitment_id, date, title, notes, completed, created_at)
               VALUES (?, ?, ?, ?, 0, ?)""",
            (row[1], date_str, row[2], row[3] or "", now_iso()),
        )
        if cur.rowcount:
            inserted += 1
    conn.commit()
    conn.close()
    return inserted


def get_schedule_items_for_date(date: str):
    """Get schedule items that apply to a given date (YYYY-MM-DD). Only from active commitments."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT si.id, si.commitment_id, si.date, si.title, si.notes, si.completed
           FROM schedule_items si
           JOIN commitments c ON c.id = si.commitment_id AND c.status = 'active'
           WHERE (si.date = ? OR si.date = '') ORDER BY si.id""",
        (date,),
    )
    return [dict(r) for r in cur.fetchall()]


def get_reminders_today():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT r.id, r.commitment_id, r.title, r.at_time, r.recurrence, r.next_due, r.done
           FROM reminders r JOIN commitments c ON c.id = r.commitment_id AND c.status = 'active'
           WHERE r.done = 0 ORDER BY r.id"""
    )
    return [dict(r) for r in cur.fetchall()]


def get_counters():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT co.id, co.commitment_id, co.name, co.current_value, co.target_value, co.unit, co.start_date, co.last_updated
           FROM counters co JOIN commitments c ON c.id = co.commitment_id AND c.status = 'active'
           ORDER BY co.id"""
    )
    return [dict(r) for r in cur.fetchall()]


def get_streaks():
    """Streaks from streaks table (legacy) plus commitment-based (current_streak on commitments). Legacy rows have streak_id for 'Log today' button."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT s.id, s.commitment_id, s.name, s.current_streak, s.longest_streak, s.last_activity_date
           FROM streaks s JOIN commitments c ON c.id = s.commitment_id AND c.status = 'active'
           ORDER BY s.id"""
    )
    legacy = [dict(r) for r in cur.fetchall()]
    for row in legacy:
        row["streak_id"] = row["id"]
    cur.execute(
        """SELECT id AS commitment_id, task_description AS name, current_streak, best_streak AS longest_streak, last_completed_date AS last_activity_date
           FROM commitments WHERE status = 'active' AND (current_streak > 0 OR last_completed_date IS NOT NULL)"""
    )
    from_commitments = [dict(r) for r in cur.fetchall()]
    seen_cid = {row["commitment_id"] for row in from_commitments}
    for row in legacy:
        if row["commitment_id"] not in seen_cid:
            from_commitments.append(row)
    for row in from_commitments:
        if "streak_id" not in row:
            row["id"] = row["commitment_id"]
            row["streak_id"] = None
    conn.close()
    return from_commitments


def get_punishment_triggers():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT pt.id, pt.commitment_id, pt.condition_text, pt.action_text, pt.active
           FROM punishment_triggers pt JOIN commitments c ON c.id = pt.commitment_id AND c.status = 'active'
           WHERE pt.active = 1"""
    )
    return [dict(r) for r in cur.fetchall()]


def get_pending_commitments():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, source_post_id, raw_text, kind, task_description, confidence, created_at
           FROM commitments WHERE status = 'pending' ORDER BY id"""
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_commitment_status(commitment_id: int, status: str) -> bool:
    if status not in ("active", "rejected"):
        return False
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE commitments SET status = ? WHERE id = ?", (status, commitment_id))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok
