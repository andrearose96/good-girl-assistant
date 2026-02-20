"""Quick verification: imports, DB init, parser, import flow, and API data shape."""
import sys
from datetime import date

def test_imports():
    print("1. Imports...", end=" ")
    from config import tumblr_configured, DB_PATH
    from db import init_db, get_conn
    from parser import extract_commitments, Commitment
    from import_text import import_from_text
    from assistant import get_today_brief, build_assistant_message, today_str
    from sync import get_schedule_items_for_date, get_reminders_today, get_counters, get_streaks, get_punishment_triggers
    print("OK")

def test_db():
    print("2. DB init...", end=" ")
    from db import init_db, get_conn
    init_db()
    conn = get_conn()
    conn.execute("SELECT 1")
    conn.close()
    print("OK")

def test_parser():
    print("3. Parser...", end=" ")
    from parser import extract_commitments
    text = "Day 47 rule: no orgasm. Poll winner = 7 days locked. I will edge every day for 30 days. If you break a rule, then add 3 days."
    commitments = extract_commitments(text)
    assert len(commitments) >= 1, "Expected at least one commitment"
    print(f"OK ({len(commitments)} commitment(s))")

def test_import_flow():
    print("4. Import flow...", end=" ")
    from import_text import import_from_text
    n = import_from_text("Daily: morning stretch. Rule: no orgasm every day. Streak: 5 days.", "test_run")
    print(f"OK (imported {n} commitment(s))")

def test_today_brief():
    print("5. Today brief & assistant message...", end=" ")
    from assistant import get_today_brief, build_assistant_message
    today = date.today().isoformat()
    data = get_today_brief(today)
    assert "date" in data and data["date"] == today
    assert "schedule" in data and "reminders" in data and "counters" in data and "streaks" in data and "punishment_triggers" in data
    msg = build_assistant_message(today)
    assert isinstance(msg, str) and len(msg) > 0
    print("OK")

def test_flask_app():
    print("6. Flask app (routes exist)...", end=" ")
    from app import app
    with app.test_client() as c:
        r = c.get("/")
        assert r.status_code == 200, f"GET / => {r.status_code}"
        r = c.get("/api/today")
        assert r.status_code == 200
        j = r.get_json()
        assert "date" in j and "schedule" in j
        r = c.get("/api/assistant-message")
        assert r.status_code == 200
        j = r.get_json()
        assert "message" in j
        r = c.get("/import")
        assert r.status_code == 200
        r = c.get("/sync")
        assert r.status_code == 200
        # API with date param
        r = c.get("/api/today?date=2025-01-15")
        assert r.status_code == 200
        assert r.get_json()["date"] == "2025-01-15"
        r = c.get("/api/assistant-message?date=2025-01-15")
        assert r.status_code == 200
        assert "message" in r.get_json()
        # POST import
        r = c.post("/import", data={"text": "Daily: drink water. If you skip, then no treat."}, follow_redirects=False)
        assert r.status_code in (200, 302)
    print("OK")

def main():
    try:
        test_imports()
        test_db()
        test_parser()
        test_import_flow()
        test_today_brief()
        test_flask_app()
        print("\nAll checks passed.")
        return 0
    except Exception as e:
        print(f"\nFAIL: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
