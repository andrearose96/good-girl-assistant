"""AI assistant: what to do today, reminders, counters, streaks, punishment triggers."""
from datetime import datetime, date
from typing import Optional

from db import get_conn, now_iso
from sync import (
    get_schedule_items_for_date,
    get_reminders_today,
    get_counters,
    get_streaks,
    get_punishment_triggers,
)


def today_str() -> str:
    return date.today().isoformat()


def get_today_brief(date_str: Optional[str] = None) -> dict:
    """Aggregate everything the assistant should show for a day."""
    date_str = date_str or today_str()
    schedule = get_schedule_items_for_date(date_str)
    reminders = get_reminders_today()
    counters = get_counters()
    streaks = get_streaks()
    punishments = get_punishment_triggers()
    return {
        "date": date_str,
        "schedule": schedule,
        "reminders": reminders,
        "counters": counters,
        "streaks": streaks,
        "punishment_triggers": punishments,
    }


def build_assistant_message(date_str: Optional[str] = None) -> str:
    """Build assistant message: what's due today, overdue, streak on the line, punishments, short instructions."""
    data = get_today_brief(date_str)
    d = data["date"]
    lines = [f"**Your plan for {d}**", ""]

    due = [s for s in data["schedule"] if not s.get("completed")]
    done = [s for s in data["schedule"] if s.get("completed")]
    undone_r = [r for r in data["reminders"]] if data["reminders"] else []
    undone_r = [r for r in undone_r if not r.get("done")]
    if due:
        lines.append("📋 **Due today**")
        for s in due:
            lines.append(f"  • {s['title']}")
        lines.append("")
    if done:
        lines.append("✅ **Done**")
        for s in done:
            lines.append(f"  • {s['title']}")
        lines.append("")

    if undone_r:
        lines.append("🔔 **Reminders**")
        for r in undone_r:
            lines.append(f"  • {r['title']}")
        lines.append("")

    if data["streaks"]:
        lines.append("🔥 **Streak on the line**")
        for s in data["streaks"]:
            cur = s.get("current_streak", 0)
            best = s.get("longest_streak", 0)
            lines.append(f"  • {s['name']}: {cur} days (best: {best}) — keep it going.")
        lines.append("")

    if data["punishment_triggers"]:
        lines.append("⚠️ **If you break a rule**")
        for p in data["punishment_triggers"]:
            lines.append(f"  • If {p['condition_text']} → {p['action_text']}")
        lines.append("")

    if data["counters"]:
        lines.append("📊 **Counters**")
        for c in data["counters"]:
            t = c.get("target_value")
            v = c.get("current_value", 0)
            line = f"  • {c['name']}: {v}"
            if t is not None:
                line += f" / {t}"
            lines.append(line)
        lines.append("")

    if due or undone_r:
        lines.append("_Complete what's due today. One step at a time._")
    elif len(lines) <= 2:
        lines.append("No commitments loaded yet. Sync from Tumblr or Import text, then hit **Generate today**.")
    return "\n".join(lines).strip()


def mark_schedule_done(schedule_item_id: int) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT commitment_id FROM schedule_items WHERE id = ?", (schedule_item_id,))
    row = cur.fetchone()
    commitment_id = row[0] if row else None
    cur.execute("UPDATE schedule_items SET completed = 1 WHERE id = ?", (schedule_item_id,))
    conn.commit()
    ok = cur.rowcount > 0
    if ok and commitment_id is not None:
        _update_commitment_streak_if_done_today(cur, commitment_id)
        conn.commit()
    conn.close()
    return ok


def _update_commitment_streak_if_done_today(cur, commitment_id: int):
    """If all of today's schedule items for this commitment are done, update commitment streak."""
    today = today_str()
    cur.execute(
        """SELECT id FROM schedule_items WHERE commitment_id = ? AND date = ? AND completed = 0""",
        (commitment_id, today),
    )
    if cur.fetchone() is not None:
        return
    cur.execute(
        """SELECT current_streak, best_streak, last_completed_date FROM commitments WHERE id = ?""",
        (commitment_id,),
    )
    row = cur.fetchone()
    if not row:
        return
    current, best, last = row[0] or 0, row[1] or 0, row[2]
    if last == today:
        return
    if last:
        try:
            last_d = datetime.strptime(last[:10], "%Y-%m-%d").date()
            today_d = date.today()
            if (today_d - last_d).days == 1:
                current += 1
            else:
                current = 1
        except Exception:
            current = 1
    else:
        current = 1
    best = max(best, current)
    cur.execute(
        """UPDATE commitments SET current_streak = ?, best_streak = ?, last_completed_date = ? WHERE id = ?""",
        (current, best, today, commitment_id),
    )


def mark_reminder_done(reminder_id: int) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def increment_counter(counter_id: int, by: int = 1) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE counters SET current_value = current_value + ?, last_updated = ? WHERE id = ?",
        (by, now_iso(), counter_id),
    )
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def update_streak(streak_id: int, completed_today: bool = True) -> bool:
    """If completed_today, increment streak and update last_activity_date."""
    today = today_str()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT current_streak, longest_streak, last_activity_date FROM streaks WHERE id = ?",
        (streak_id,),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return False
    current, longest, last = row[0], row[1], row[2]
    if last == today:
        conn.close()
        return True  # already logged today
    if last:
        try:
            last_d = datetime.strptime(last[:10], "%Y-%m-%d").date()
            today_d = date.today()
            if (today_d - last_d).days == 1:
                current += 1
            else:
                current = 1
        except Exception:
            current = 1
    else:
        current = 1
    longest = max(longest or 0, current)
    cur.execute(
        "UPDATE streaks SET current_streak = ?, longest_streak = ?, last_activity_date = ? WHERE id = ?",
        (current, longest, today, streak_id),
    )
    conn.commit()
    conn.close()
    return True
