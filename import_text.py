"""Import commitments from pasted text (no Tumblr API)."""
from db import get_conn, init_db, now_iso
from parser import extract_commitments
from sync import _ensure_commitment_id, _derive_schedule_and_reminders, _derive_counters, _derive_streaks, _derive_punishment


def import_from_text(text: str, source_label: str = "pasted") -> int:
    """Parse text, insert commitments and derived reminders/counters/streaks. Returns count added."""
    init_db()
    commitments = extract_commitments(text)
    if not commitments:
        return 0
    conn = get_conn()
    cur = conn.cursor()
    post_id = f"import:{source_label}"
    count = 0
    for c in commitments:
        cid = _ensure_commitment_id(cur, c, post_id, status="active")
        if cid:
            count += 1
        _derive_schedule_and_reminders(cur, c, cid or 0)
        _derive_counters(cur, c, cid or 0)
        _derive_streaks(cur, c, cid or 0)
        _derive_punishment(cur, c, cid or 0)
    conn.commit()
    conn.close()
    return count
