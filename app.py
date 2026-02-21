"""Flask app: assistant UI, sync from Tumblr, today's plan."""
import os
import re
from datetime import date

from flask import Flask, render_template_string, request, jsonify, redirect, url_for, session
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from config import tumblr_configured, tumblr_consumer_configured
from db import init_db, set_setting
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
    set_commitment_status_bulk,
    get_all_commitments_for_manage,
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
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")
CORS(app)
# So url_for(..., _external=True) uses https when behind Render's proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

init_db()

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Good Girl Assistant</title>
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
    <h1>Good Girl Assistant</h1>
    <p class="sub">Your daily plan from Tumblr commitments</p>
    <nav>
      <a href="{{ url_for('index') }}">Today</a>
      <a href="{{ url_for('sync_page') }}">Sync Tumblr</a>
      <a href="{{ url_for('import_page') }}">Import text</a>
      <a href="{{ url_for('manage_page') }}">Manage</a>
    </nav>

    <div class="card">
      <h2>Today's plan — {{ data.date }}</h2>
      <div class="message">{{ message | safe }}</div>
      {% if generate_error %}
      <p class="sync-result err" style="margin-top:0.75rem;">Could not generate schedule. Add commitments first (Import text or Sync Tumblr), then try again.</p>
      {% endif %}
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
  <title>Sync — Good Girl Assistant</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root { --bg: #0f0e14; --surface: #1a1922; --border: #2d2a3a; --text: #e8e4ef; --muted: #8b8499; --accent: #c49ae8; --success: #7dd3a3; }
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
    <p style="color: var(--muted);">Sync your blog or any Tumblr profile—we pull posts and extract commitments (rules, days, streaks, punishments).</p>
    <div class="card">
      {% if tumblr_connected %}
      <p class="result" style="color: var(--success);">You're signed in. Sync your blog or enter another below.</p>
      {% endif %}
      {% if tumblr_error %}
      <p class="err">Sign-in failed. In your Tumblr app settings, set the <strong>Callback URL</strong> to the URL shown below, then try again.</p>
      {% endif %}
      {% if already_signed_in %}
      <p class="result" style="color: var(--success);">You're already signed in. Use the form below to sync.</p>
      {% endif %}
      {% if tumblr_configured %}
      <p class="sub" style="margin-bottom:0.5rem;">Your Tumblr connection is stored so we don't hit the OAuth limit. To keep it across deploys (e.g. on Render), use a persistent disk for <code>data/</code> or set <code>TUMBLR_OAUTH_TOKEN</code> and <code>TUMBLR_OAUTH_SECRET</code> in the server environment.</p>
      <form method="post" action="{{ url_for('sync_page') }}">
        <label for="blog">Blog to sync (optional)</label>
        <input type="text" id="blog" name="blog" placeholder="Leave blank to sync your blog, or paste a URL (e.g. andrearose96.tumblr.com) or name" value="{{ blog or '' }}">
        <label style="display:flex;align-items:center;gap:0.5rem;margin-top:0.5rem;"><input type="checkbox" name="force_fetch" value="1"> Force full sync (ignore cooldown; uses more of your Tumblr limit)</label>
        <button type="submit" class="btn" style="margin-top:0.75rem;">Sync</button>
      </form>
      {% elif tumblr_consumer_configured %}
      <p><strong>How it works:</strong> You're not opening any link in the Tumblr app. We sync by having you sign in once in a <strong>browser</strong> (on your phone, use Chrome or Safari). Tumblr will send you back here automatically after you allow access.</p>
      <p>1. In your <a href="https://www.tumblr.com/oauth/apps" target="_blank">Tumblr app settings</a> (on the website), set <strong>Default callback URL</strong> to this exact value (copy it, don't open it):</p>
      <p><code style="word-break:break-all; font-size:0.8rem;">{{ tumblr_callback_url }}</code></p>
      <p>2. Click the button below. You'll go to Tumblr to allow access, then come back here. <strong>On phone:</strong> use your browser (not an in-app viewer). If you're not redirected back, open this site again and check Sync—you may already be signed in.</p>
      <p><a href="{{ url_for('tumblr_connect') }}" class="btn">Sign in with Tumblr to sync</a></p>
      <p class="sub" style="margin-top:0.5rem;">Or open this in your browser (handy on phone): <a href="{{ tumblr_connect_url }}">{{ tumblr_connect_url }}</a></p>
      {% else %}
      <p>Tumblr sync isn't available on this server.</p>
      <p><strong>If you're the deployer:</strong> On Render, go to your service → <strong>Environment</strong> → add two variables (separately, not a file): <code>TUMBLR_CONSUMER_KEY</code> and <code>TUMBLR_CONSUMER_SECRET</code>. Save and <strong>redeploy</strong> so the app picks them up.</p>
      <p>You can still use <a href="{{ url_for('import_page') }}">Import text</a> to paste posts or rules and extract commitments.</p>
      {% endif %}
    </div>
    {% if result %}
    <div class="card result">
      {% if result.used_cache %}
      <p class="result" style="color: var(--muted);">Used cached data (no new API call). Processed {{ result.new_commitments }} new commitment(s). Check "Force full sync" to fetch from Tumblr again.</p>
      {% else %}
      Posts fetched: {{ result.posts_fetched }} · New commitments: {{ result.new_commitments }}{% if result.pending_review is defined %} · Pending review: {{ result.pending_review }}{% endif %}
      {% endif %}
      {% for e in result.errors %}
      <p class="err">{{ e }}</p>
      {% endfor %}
    </div>
    {% endif %}
    <p><a href="{{ url_for('index') }}" class="btn secondary">← Back to Today</a> <a href="{{ url_for('manage_page') }}" class="btn secondary">Manage commitments</a></p>
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
  <title>Import — Good Girl Assistant</title>
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
    <p><a href="{{ url_for('index') }}" class="btn secondary">← Back to Today</a> <a href="{{ url_for('manage_page') }}" class="btn secondary">Manage commitments</a></p>
  </div>
</body>
</html>
"""

MANAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Manage — Good Girl Assistant</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root { --bg: #0f0e14; --surface: #1a1922; --border: #2d2a3a; --text: #e8e4ef; --muted: #8b8499; --accent: #c49ae8; --accent-dim: #7b5a9e; --success: #7dd3a3; }
    * { box-sizing: border-box; }
    body { font-family: 'JetBrains Mono', monospace; background: var(--bg); color: var(--text); margin: 0; min-height: 100vh; line-height: 1.5; }
    .container { max-width: 720px; margin: 0 auto; padding: 1.5rem; }
    h1 { font-family: 'DM Serif Display', serif; font-size: 1.75rem; color: var(--accent); margin-bottom: 0.5rem; }
    .sub { color: var(--muted); font-size: 0.85rem; margin-bottom: 1rem; }
    nav { display: flex; gap: 0.75rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
    nav a, .btn { color: var(--accent); text-decoration: none; padding: 0.4rem 0.8rem; border: 1px solid var(--border); border-radius: 6px; font-size: 0.85rem; background: var(--surface); cursor: pointer; font-family: inherit; }
    nav a:hover, .btn:hover { border-color: var(--accent-dim); background: #252330; }
    .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem; margin-bottom: 1rem; }
    .card h2 { font-size: 1rem; color: var(--muted); margin: 0 0 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
    .card ul { margin: 0; padding: 0; list-style: none; }
    .card li { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; padding: 0.6rem 0; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
    .card li:last-child { border-bottom: none; }
    .btn-sm { padding: 0.25rem 0.5rem; font-size: 0.75rem; }
    .commitment-text { flex: 1; min-width: 200px; font-size: 0.9rem; }
    .meta { font-size: 0.75rem; color: var(--muted); }
    .status-active { color: var(--success); }
    .status-rejected { text-decoration: line-through; color: var(--muted); }
    .filters { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap; }
    .filters label { font-size: 0.85rem; color: var(--muted); }
    .filters select { background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 0.35rem 0.5rem; border-radius: 6px; font-family: inherit; }
    .bulk-actions { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem; flex-wrap: wrap; }
    .bulk-actions .select-all { font-size: 0.85rem; cursor: pointer; }
    .row-select { flex-shrink: 0; cursor: pointer; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Manage commitments</h1>
    <p class="sub">Opt in (Include) or out (Exclude). Only included commitments appear in your daily plan.</p>
    <nav>
      <a href="{{ url_for('index') }}">Today</a>
      <a href="{{ url_for('sync_page') }}">Sync Tumblr</a>
      <a href="{{ url_for('import_page') }}">Import text</a>
      <a href="{{ url_for('manage_page') }}">Manage</a>
    </nav>
    <div class="card">
      <h2>All commitments</h2>
      <form method="get" action="{{ url_for('manage_page') }}" class="filters">
        <label>Source:</label>
        <select name="source" onchange="this.form.submit()">
          <option value="all" {{ 'selected' if source == 'all' else '' }}>All</option>
          <option value="tumblr" {{ 'selected' if source == 'tumblr' else '' }}>Tumblr</option>
          <option value="import" {{ 'selected' if source == 'import' else '' }}>Import</option>
        </select>
        <label>Status:</label>
        <select name="status" onchange="this.form.submit()">
          <option value="all" {{ 'selected' if status == 'all' else '' }}>All</option>
          <option value="active" {{ 'selected' if status == 'active' else '' }}>Included</option>
          <option value="rejected" {{ 'selected' if status == 'rejected' else '' }}>Excluded</option>
          <option value="pending" {{ 'selected' if status == 'pending' else '' }}>Pending</option>
        </select>
        {% if source != 'all' or status != 'all' %}
        <a href="{{ url_for('manage_page') }}" class="btn btn-sm">Clear filters</a>
        {% endif %}
      </form>
      {% if commitments %}
      <form method="post" action="{{ url_for('manage_bulk') }}" id="bulk-form">
        <input type="hidden" name="source" value="{{ source }}">
        <input type="hidden" name="status" value="{{ status }}">
        <div class="bulk-actions">
          <label class="select-all"><input type="checkbox" id="select-all"> Select all</label>
          <button type="submit" name="action" value="include" class="btn btn-sm">Include selected</button>
          <button type="submit" name="action" value="exclude" class="btn btn-sm">Exclude selected</button>
        </div>
        <ul>
          {% for c in commitments %}
          <li>
            <label class="row-select">
              <input type="checkbox" name="ids" value="{{ c.id }}" form="bulk-form">
            </label>
            <div class="commitment-text">
              <span class="meta">{{ c.kind or 'commitment' }} · {{ c.source_label }}</span>
              <span class="status-{{ c.status or 'pending' }}">{{ c.raw_text[:200] }}{% if c.raw_text|length > 200 %}…{% endif %}</span>
            </div>
            <div style="display:flex;gap:0.25rem;">
              <form action="{{ url_for('commitment_approve', id=c.id) }}" method="post" style="display:inline;">
                <button type="submit" class="btn btn-sm">Include</button>
              </form>
              <form action="{{ url_for('commitment_reject', id=c.id) }}" method="post" style="display:inline;">
                <button type="submit" class="btn btn-sm">Exclude</button>
              </form>
            </div>
          </li>
          {% endfor %}
        </ul>
      </form>
      {% else %}
      <p class="sub">No commitments found. {% if source != 'all' or status != 'all' %}<a href="{{ url_for('manage_page') }}">Clear filters</a> or {% endif %}<a href="{{ url_for('sync_page') }}">Sync Tumblr</a> / <a href="{{ url_for('import_page') }}">Import text</a> to add some.</p>
      {% endif %}
    </div>
    <p><a href="{{ url_for('index') }}" class="btn secondary">← Back to Today</a></p>
  </div>
  <script>
    document.getElementById('select-all')?.addEventListener('change', function() {
      document.querySelectorAll('input[name="ids"]').forEach(function(cb) { cb.checked = this.checked; }, this);
    });
  </script>
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
    generate_error = request.args.get("generate_error")
    return render_template_string(
        INDEX_HTML,
        data=data,
        message=message_html,
        pending=pending,
        generate_error=generate_error,
    )


@app.route("/tumblr/connect")
def tumblr_connect():
    """Start Tumblr OAuth: redirect user to Tumblr to authorize, then callback saves token."""
    if not tumblr_consumer_configured():
        return redirect(url_for("sync_page"))
    # Reuse stored tokens so we don't burn OAuth request limit
    if tumblr_configured():
        return redirect(url_for("sync_page", already_signed_in="1"))
    try:
        from requests_oauthlib import OAuth1Session
        from config import TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET
        # Use env callback URL if set (e.g. on Render), else build from request so it's https
        callback_uri = os.getenv("TUMBLR_CALLBACK_URL", "").strip()
        if not callback_uri:
            callback_uri = url_for("tumblr_callback", _external=True)
        oauth = OAuth1Session(
            TUMBLR_CONSUMER_KEY,
            client_secret=TUMBLR_CONSUMER_SECRET,
            callback_uri=callback_uri,
        )
        oauth.fetch_request_token("https://www.tumblr.com/oauth/request_token")
        authorization_url = oauth.authorization_url("https://www.tumblr.com/oauth/authorize")
        session["tumblr_request_token"] = (oauth.token, oauth.token_secret)
        return redirect(authorization_url)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return redirect(url_for("sync_page", tumblr_error="1"))


@app.route("/tumblr/callback")
def tumblr_callback():
    """Tumblr redirects here after user authorizes; exchange verifier for access token and save."""
    from requests_oauthlib import OAuth1Session
    from config import TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET
    stored = session.get("tumblr_request_token")
    if not stored:
        return redirect(url_for("sync_page", tumblr_error="1"))
    request_token, request_token_secret = stored
    oauth_verifier = request.args.get("oauth_verifier")
    if not oauth_verifier:
        return redirect(url_for("sync_page", tumblr_error="1"))
    oauth = OAuth1Session(
        TUMBLR_CONSUMER_KEY,
        client_secret=TUMBLR_CONSUMER_SECRET,
        resource_owner_key=request_token,
        resource_owner_secret=request_token_secret,
        verifier=oauth_verifier,
    )
    try:
        oauth.fetch_access_token("https://www.tumblr.com/oauth/access_token")
    except Exception:
        return redirect(url_for("sync_page", tumblr_error="1"))
    session.pop("tumblr_request_token", None)
    set_setting("tumblr_oauth_token", oauth.token)
    set_setting("tumblr_oauth_secret", oauth.token_secret)
    return redirect(url_for("sync_page", tumblr_connected="1"))


def _normalize_blog_input(raw: str) -> str:
    """Extract blog name from URL or plain name. E.g. https://foo.tumblr.com -> foo."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    if "tumblr.com" in raw:
        from urllib.parse import urlparse
        parsed = urlparse(raw if raw.startswith("http") else "https://" + raw)
        host = (parsed.netloc or parsed.path or "").strip()
        return host.replace(".tumblr.com", "").strip() or raw
    return raw


@app.route("/sync", methods=["GET", "POST"])
def sync_page():
    result = None
    blog = None
    if request.method == "POST":
        blog = _normalize_blog_input(request.form.get("blog") or "")
        if not blog and tumblr_configured():
            from tumblr_client import get_authenticated_user_primary_blog
            blog = get_authenticated_user_primary_blog()
        force_fetch = request.form.get("force_fetch") == "1"
        result = sync_tumblr(blog=blog or None, force_fetch=force_fetch)
        if not result.get("errors") and result.get("posts_fetched"):
            return redirect(url_for("index"))
    tumblr_connected = request.args.get("tumblr_connected")
    tumblr_error = request.args.get("tumblr_error")
    already_signed_in = request.args.get("already_signed_in")
    tumblr_callback_url = url_for("tumblr_callback", _external=True) if tumblr_consumer_configured() else ""
    tumblr_connect_url = url_for("tumblr_connect", _external=True) if tumblr_consumer_configured() else ""
    return render_template_string(
        SYNC_HTML,
        tumblr_configured=tumblr_configured(),
        tumblr_consumer_configured=tumblr_consumer_configured(),
        tumblr_connected=tumblr_connected,
        tumblr_error=tumblr_error,
        already_signed_in=already_signed_in,
        tumblr_callback_url=tumblr_callback_url,
        tumblr_connect_url=tumblr_connect_url,
        blog=blog,
        result=result,
    )


@app.route("/manage")
def manage_page():
    source = request.args.get("source") or "all"
    status = request.args.get("status") or "all"
    if source not in ("all", "tumblr", "import"):
        source = "all"
    if status not in ("all", "active", "rejected", "pending"):
        status = "all"
    commitments = get_all_commitments_for_manage(
        source_filter=source if source != "all" else None,
        status_filter=status if status != "all" else None,
    )
    return render_template_string(
        MANAGE_HTML,
        commitments=commitments,
        source=source,
        status=status,
    )


@app.route("/manage/bulk", methods=["POST"])
def manage_bulk():
    action = request.form.get("action")
    ids = request.form.getlist("ids")
    source = request.form.get("source") or "all"
    status = request.form.get("status") or "all"
    if action in ("include", "exclude") and ids:
        id_list = []
        for i in ids:
            try:
                id_list.append(int(i))
            except ValueError:
                pass
        if id_list:
            set_commitment_status_bulk(id_list, "active" if action == "include" else "rejected")
    params = []
    if source != "all":
        params.append(f"source={source}")
    if status != "all":
        params.append(f"status={status}")
    redirect_url = url_for("manage_page") + ("?" + "&".join(params) if params else "")
    return redirect(redirect_url)


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
    try:
        generate_schedule_for_date(date_str)
        return redirect(url_for("index"))
    except Exception as e:
        return redirect(url_for("index", generate_error="1"))


@app.route("/commitment/<int:id>/approve", methods=["POST"])
def commitment_approve(id):
    set_commitment_status(id, "active")
    return redirect(url_for("manage_page") if request.referrer and "/manage" in request.referrer else url_for("index"))


@app.route("/commitment/<int:id>/reject", methods=["POST"])
def commitment_reject(id):
    set_commitment_status(id, "rejected")
    return redirect(url_for("manage_page") if request.referrer and "/manage" in request.referrer else url_for("index"))


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
