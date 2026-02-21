# Good Girl Assistant

An app that pulls your Tumblr posts (especially **Training** style posts), detects commitments, and turns them into reminders, daily schedules, counters, streaks, and punishment triggers. It acts like an AI assistant that tells you what to do each day.

## What it does

- **Pulls Tumblr** – Sync your blog or any Tumblr profile. Users sign in with Tumblr (no API keys needed for them).
- **Detects commitments** – Parses patterns like:
  - “I will [task] for N days” / “until X”
  - “Day 47 rule: …”
  - “Poll winner = 7 days locked”
  - “N days locked/denial/edging”
  - “Streak: N days”
  - “If [condition], then [punishment]”
  - “Daily: …” / “Rule: … every day”
- **Converts to**:
  - **Reminders** – e.g. daily tasks
  - **Schedule** – what to do today
  - **Counters** – e.g. days locked, current day number
  - **Streaks** – consecutive days completed
  - **Punishment triggers** – if-then rules
- **Assistant view** – One page showing “your plan for today” with check-offs and counter/streak tracking.

## Setup

1. **Clone or copy** this folder.

2. **Create a virtualenv and install deps:**
   ```bash
   cd Good-Girl-Assistant
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   ```

3. **Tumblr sync (optional, for deployers)**  
   To let *your users* sync from Tumblr, set **once** in your environment (e.g. on Render or in `.env`):
   - `TUMBLR_CONSUMER_KEY` and `TUMBLR_CONSUMER_SECRET` from a [Tumblr OAuth app](https://www.tumblr.com/oauth/apps) you create.  
   Then in that app, set the callback URL to `https://your-domain.com/tumblr/callback`.  
   After that, **users never touch keys**—they just click “Sign in with Tumblr” on the Sync page.

   Without these, the Sync page shows “Tumblr sync isn’t available” and users can use **Import text** instead.

4. **Run the app:**
   ```bash
   python app.py
   ```
   Open http://localhost:5000

## Usage

- **Today** – Main page: today’s plan, schedule, reminders, counters, streaks, and punishment rules. Use “Done” to mark items and “+1” / “Log today” for counters and streaks.
- **Sync Tumblr** – Sign in with Tumblr, then sync your blog or any profile by URL/name.
- **Import text** – Paste any block of text; the parser will detect commitments and add them to your schedule/reminders/counters/streaks.

Data is stored in `data/commitments.db` (SQLite).

## API (optional)

- `GET /api/today?date=YYYY-MM-DD` – JSON for that day (schedule, reminders, counters, streaks, punishment triggers).
- `GET /api/assistant-message?date=YYYY-MM-DD` – Plain text “what to do today” message.
