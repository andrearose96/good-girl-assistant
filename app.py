"""Flask app: assistant UI, sync from Tumblr, today's plan."""
import re
from datetime import date

from flask import Flask, render_template_string, request, jsonify, redirect, url_for
from flask_cors import CORS

from config import tumblr_configured
from db import init_db
from sync import (
    sync_tumblr,
    get_schedule_items_for_date,
    get_reminders_today,
    get_counters,
    get_streaks,
    get_punishment_triggers,
    generate_schedule_for_date,
    get_pending_commitments,
    set_commitment_status,
)
from import_text import import_from_text
from assistant import (
    get_today_brief,
    build_assistant_message,
    mark_schedule_done,
    mark_reminder_done,
    increment_counter,
    update_streak,
    today_str,
)

app = Flask(__name__)
CORS(app)

init_db()

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Doll Training Assistant</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0f0e14;
      --surface: #1a1922;
      --border: #2d2a3a;
      --text: #e8e4ef;
      --muted: #8b8499;
      --accent: #c49ae8;
      --accent-dim: #7b5a9e;
      --success: #7dd3a3;
      --warn: #e8b86d;
    }
    * { box-sizing: border-box; }
    body {
      font-family: 'JetBrains Mono', monospace;
      background: var(--bg);
      color: var(--text);
      margin: 0;
      min-height: 100vh;
      line-height: 1.5;
    }
    .container { max-width: 640px; margin: 0 auto; padding: 1.5rem; }
    h1 {
      font-family: 'DM Serif Display', serif;
      font-size: 1.75rem;
      color: var(--accent);
      margin-bottom: 0.5rem;
    }
    .sub { color: var(--muted); font-size: 0.85rem; margin-bottom: 1.5rem; }
    nav {
      display: flex;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
      flex-wrap: wrap;
    }
    nav a, .btn {
      color: var(--accent);
      text-decoration: none;
      padding: 0.4rem 0.8rem;
      border: 1px solid var(--border);
      border-radius: 6px;
      font-size: 0.85rem;
      background: var(--surface);
      cursor: pointer;
      font-family: inherit;
    }
    nav a:hover, .btn:hover { border-color: var(--accent-dim); background: #252330; }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1.25rem;
      margin-bottom: 1rem;
    }
    .card h2 { font-size: 1rem; color: var(--muted); margin: 0 0 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
    .card ul { margin: 0; padding: 0; list-style: none; }
    .card li {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.5rem 0;
      border-bottom: 1px solid var(--border);
    }
    .card li:last-child { border-bottom: none; }
    .done { text-decoration: line-through; color: var(--muted); }
    .btn-sm { padding: 0.25rem 0.5rem; font-size: 0.75rem; }
    .message {
      white-space: pre-wrap;
      font-size: 0.9rem;
      color: var(--text);
    }
    .message strong { color: var(--accent); }
    .sync-result { font-size: 0.85rem; color: var(--muted); margin-top: 1rem; }
    .sync-result .err { color: #e07a7a; }
    .counter-row { display: flex; align-items: center; gap: 0.5rem; }
    .counter-row span { flex: 1; }
    input[type="text"] {
      background: var(--bg);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 0.5rem;
      border-radius: 6px;
      font-family: inherit;
      width: 100%;
      max-width: 280px;
    }
    label { display: block; margin-bottom: 0.25rem; color: var(--muted); font-size: 0.85rem; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Doll Training Assistant</h1>
    <p class="sub">Your daily plan from Tumblr commitments</p>
    <nav>
      <a href="{{ url_for('index') }}">Today</a>
      <a href="{{ url_for('sync_page') }}">Sync Tumblr</a>
      <a href="{{ url_for('import_page') }}">Import text</a>
    </nav>

    <div class="card">
      <h2>Today's plan — {{ data.date }}</h2>
      <div class="message">{{ message }}</div>
      <form action="{{ url_for('generate_route') }}" method="post" style="margin-top:0.75rem;">
        <input type="hidden" name="date" value="{{ data.date }}">
        <button type="submit" class="btn">Generate today</button>
      </form>
    </div>

    {% if pending %}
    <div class="card">
      <h2>Needs review</h2>
      <p class="sub" style="margin-bottom:0.5rem;">Approve or reject parsed commitments</p>
      <ul>
        {% for c in pending %}
        <li style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
          <span style="flex:1;min-width:200px;">{{ c.raw_text[:80] }}{% if c.raw_text|length > 80 %}…{% endif %} <small>({{ c.kind }}, {{ (c.confidence or 0)|round(2) }})</small></span>
          <form action="{{ url_for('commitment_approve', id=c.id) }}" method="post" style="display:inline;">
            <button type="submit" class="btn btn-sm">Approve</button>
          </form>
          <form action="{{ url_for('commitment_reject', id=c.id) }}" method="post" style="display:inline;">
            <button type="submit" class="btn btn-sm">Reject</button>
          </form>
        </li>
        {% endfor %}
      </ul>
    </div>
    {% endif %}

    {% if data.schedule %}
    <div class="card">
      <h2>Schedule</h2>
      <ul>
        {% for s in data.schedule %}
        <li>
          <span class="{{ 'done' if s.completed else '' }}">{{ s.title }}</span>
          {% if not s.completed %}
          <form action="{{ url_for('mark_schedule_done_route', id=s.id) }}" method="post" style="display:inline;">
            <button type="submit" class="btn btn-sm">Done</button>
          </form>
          {% endif %}
        </li>
        {% endfor %}
      </ul>
    </div>
    {% endif %}

    {% if data.reminders %}
    <div class="card">
      <h2>Reminders</h2>
      <ul>
        {% for r in data.reminders %}
        <li>
          <span class="{{ 'done' if r.done else '' }}">{{ r.title }}</span>
          {% if not r.done %}
          <form action="{{ url_for('mark_reminder_done_route', id=r.id) }}" method="post" style="display:inline;">
            <button type="submit" class="btn btn-sm">Done</button>
          </form>
          {% endif %}
        </li>
        {% endfor %}
      </ul>
    </div>
    {% endif %}

    {% if data.counters %}
    <div class="card">
      <h2>Counters</h2>
      <ul>
        {% for c in data.counters %}
        <li>
          <div class="counter-row">
            <span>{{ c.name }}: {{ c.current_value }}{% if c.target_value is not none %} / {{ c.target_value }}{% endif %}</span>
            <form action="{{ url_for('increment_counter_route', id=c.id) }}" method="post" style="display:inline;">
              <button type="submit" class="btn btn-sm">+1</button>
            </form>
          </div>
        </li>
        {% endfor %}
      </ul>
    </div>
    {% endif %}

    {% if data.streaks %}
    <div class="card">
      <h2>Streaks</h2>
      <ul>
        {% for s in data.streaks %}
        <li>
          <span>{{ s.name }}: {{ s.current_streak }} days (best {{ s.longest_streak }})</span>
          {% if s.streak_id %}
          <form action="{{ url_for('log_streak', id=s.streak_id) }}" method="post" style="display:inline;">
            <button type="submit" class="btn btn-sm">Log today</button>
          </form>
          {% endif %}
        </li>
        {% endfor %}
      </ul>
    </div>
    {% endif %}

    {% if data.punishment_triggers %}
    <div class="card">
      <h2>If you break a rule</h2>
      <ul>
        {% for p in data.punishment_triggers %}
        <li>If {{ p.condition_text }} → {{ p.action_text }}</li>
        {% endfor %}
      </ul>
    </div>
    {% endif %}
  </div>
</body>
</html>
"""

SYNC_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sync — Doll Training Assistant</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root { --bg: #0f0e14; --surface: #1a1922; --border: #2d2a3a; --text: #e8e4ef; --muted: #8b8499; --accent: #c49ae8; }
    * { box-sizing: border-box; }
    body { font-family: 'JetBrains Mono', monospace; background: var(--bg); color: var(--text); margin: 0; min-height: 100vh; padding: 1.5rem; }
    .container { max-width: 520px; margin: 0 auto; }
    h1 { font-family: 'DM Serif Display', serif; color: var(--accent); font-size: 1.5rem; }
    a { color: var(--accent); }
    .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem; margin: 1rem 0; }
    .btn { display: inline-block; padding: 0.5rem 1rem; background: var(--accent); color: var(--bg); border: none; border-radius: 6px; cursor: pointer; font-family: inherit; font-size: 0.9rem; text-decoration: none; }
    .btn:hover { opacity: 0.9; }
    .btn.secondary { background: transparent; color: var(--accent); border: 1px solid var(--border); }
    label { display: block; margin-bottom: 0.25rem; color: var(--muted); font-size: 0.85rem; }
    input { background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 0.5rem; border-radius: 6px; font-family: inherit; width: 100%; margin-bottom: 1rem; }
    .result { font-size: 0.9rem; margin-top: 1rem; }
    .err { color: #e07a7a; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Sync from Tumblr</h1>
    <p style="color: var(--muted);">Sync from <strong>any</strong> Tumblr blog and extract commitments (rules, days, streaks, punishments).</p>
    <div class="card">
      {% if tumblr_configured %}
      <form method="post" action="{{ url_for('sync_page') }}">
        <label for="blog">Tumblr blog (any profile)</label>
        <input type="text" id="blog" name="blog" placeholder="e.g. andrearose96" value="{{ blog or '' }}">
        <button type="submit" class="btn">Sync posts</button>
      </form>
      {% else %}
      <p>Add your Tumblr API keys to <code>.env</code> (see <code>.env.example</code>).</p>
      <p>Get keys from <a href="https://www.tumblr.com/oauth/apps" target="_blank">Tumblr OAuth apps</a>.</p>
      {% endif %}
    </div>
    {% if result %}
    <div class="card result">
      Posts fetched: {{ result.posts_fetched }} · New commitments: {{ result.new_commitments }}{% if result.pending_review is defined %} · Pending review: {{ result.pending_review }}{% endif %}
      {% for e in result.errors %}
      <p class="err">{{ e }}</p>
      {% endfor %}
    </div>
    {% endif %}
    <p><a href="{{ url_for('index') }}" class="btn secondary">← Back to Today</a></p>
  </div>
</body>
</html>
"""

IMPORT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Import — Doll Training Assistant</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root { --bg: #0f0e14; --surface: #1a1922; --border: #2d2a3a; --text: #e8e4ef; --muted: #8b8499; --accent: #c49ae8; }
    * { box-sizing: border-box; }
    body { font-family: 'JetBrains Mono', monospace; background: var(--bg); color: var(--text); margin: 0; min-height: 100vh; padding: 1.5rem; }
    .container { max-width: 640px; margin: 0 auto; }
    h1 { font-family: 'DM Serif Display', serif; color: var(--accent); font-size: 1.5rem; }
    a { color: var(--accent); }
    .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem; margin: 1rem 0; }
    .btn { display: inline-block; padding: 0.5rem 1rem; background: var(--accent); color: var(--bg); border: none; border-radius: 6px; cursor: pointer; font-family: inherit; font-size: 0.9rem; text-decoration: none; }
    .btn:hover { opacity: 0.9; }
    .btn.secondary { background: transparent; color: var(--accent); border: 1px solid var(--border); margin-top: 0.5rem; }
    label { display: block; margin-bottom: 0.25rem; color: var(--muted); font-size: 0.85rem; }
    textarea { background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 0.5rem; border-radius: 6px; font-family: inherit; width: 100%; min-height: 160px; margin-bottom: 1rem; resize: vertical; }
    .result { font-size: 0.9rem; margin-top: 1rem; color: var(--muted); }
  </style>
</head>
<body>
  <div class="container">
    <h1>Import from text</h1>
    <p style="color: var(--muted);">Paste a Tumblr post (or any text) and we'll detect commitments like "I will…", "Day 47 rule…", "Poll winner = 7 days locked", etc.</p>
    <div class="card">
      <form method="post" action="{{ url_for('import_page') }}">
        <label for="text">Paste post or rules</label>
        <textarea id="text" name="text" placeholder="e.g. Day 47 rule: no orgasm. Poll winner = 7 days locked. I will edge every day for 30 days.">{{ text or '' }}</textarea>
        <button type="submit" class="btn">Import</button>
      </form>
      {% if imported is not none %}
      <p class="result">Imported {{ imported }} commitment(s). <a href="{{ url_for('index') }}">View today →</a></p>
      {% endif %}
    </div>
    <p><a href="{{ url_for('index') }}" class="btn secondary">← Back to Today</a></p>
  </div>
</body>
</html>
"""


def _markdown_to_html(text: str) -> str:
    """Minimal: **bold** -> <strong>."""
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)


@app.route("/")
def index():
    data = get_today_brief()
    message = build_assistant_message()
    message_html = _markdown_to_html(message)
    pending = get_pending_commitments()
    return render_template_string(
        INDEX_HTML,
        data=data,
        message=message_html,
        pending=pending,
    )


@app.route("/sync", methods=["GET", "POST"])
def sync_page():
    result = None
    blog = None
    if request.method == "POST":
        blog = (request.form.get("blog") or "").strip()
        result = sync_tumblr(blog=blog or None)
        if not result.get("errors") and result.get("posts_fetched"):
            return redirect(url_for("index"))
    return render_template_string(
        SYNC_HTML,
        tumblr_configured=tumblr_configured(),
        blog=blog,
        result=result,
    )


@app.route("/import", methods=["GET", "POST"])
def import_page():
    text = None
    imported = None
    if request.method == "POST":
        text = (request.form.get("text") or "").strip()
        if text:
            imported = import_from_text(text, "pasted")
    return render_template_string(
        IMPORT_HTML,
        text=text,
        imported=imported,
    )


@app.route("/api/today")
def api_today():
    return jsonify(get_today_brief(request.args.get("date")))


@app.route("/api/generate", methods=["POST"])
def api_generate():
    date_str = request.args.get("date") or request.form.get("date") or today_str()
    inserted = generate_schedule_for_date(date_str)
    return jsonify({"date": date_str, "inserted": inserted})


@app.route("/generate", methods=["POST"])
def generate_route():
    date_str = request.form.get("date") or today_str()
    generate_schedule_for_date(date_str)
    return redirect(url_for("index"))


@app.route("/commitment/<int:id>/approve", methods=["POST"])
def commitment_approve(id):
    set_commitment_status(id, "active")
    return redirect(url_for("index"))


@app.route("/commitment/<int:id>/reject", methods=["POST"])
def commitment_reject(id):
    set_commitment_status(id, "rejected")
    return redirect(url_for("index"))


@app.route("/api/assistant-message")
def api_message():
    return jsonify({"message": build_assistant_message(request.args.get("date"))})


@app.route("/api/sync", methods=["POST"])
def api_sync():
    blog = request.args.get("blog") or request.form.get("blog") or None
    result = sync_tumblr(blog=blog)
    return jsonify(result)


@app.route("/schedule/<int:id>/done", methods=["POST"])
def mark_schedule_done_route(id):
    mark_schedule_done(id)
    return redirect(url_for("index"))


@app.route("/reminder/<int:id>/done", methods=["POST"])
def mark_reminder_done_route(id):
    mark_reminder_done(id)
    return redirect(url_for("index"))


@app.route("/counter/<int:id>/increment", methods=["POST"])
def increment_counter_route(id):
    increment_counter(id)
    return redirect(url_for("index"))


@app.route("/streak/<int:id>/log", methods=["POST"])
def log_streak(id):
    update_streak(id)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
