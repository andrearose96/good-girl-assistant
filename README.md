# Good Girl Assistant

An app that pulls your Tumblr posts (especially **Training** style posts), detects commitments, and turns them into reminders, daily schedules, counters, streaks, and punishment triggers. It acts like an AI assistant that tells you what to do each day.

## What it does

- **Pulls Tumblr** – Sync from **any** Tumblr blog (e.g. andrearose96). OAuth keys required.
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

3. **Tumblr (optional)**  
   To sync from Tumblr, create an app at [Tumblr OAuth apps](https://www.tumblr.com/oauth/apps), then copy `.env.example` to `.env` and set:
   - `TUMBLR_CONSUMER_KEY`
   - `TUMBLR_CONSUMER_SECRET`
   - `TUMBLR_OAUTH_TOKEN`
   - `TUMBLR_OAUTH_SECRET`
   - `TUMBLR_BLOG` (optional default; you can also type any blog name on the Sync page, e.g. `andrearose96`)

   You can still use the app **without** Tumblr: use **Import text** to paste a post or rules and it will parse commitments from that.

4. **Run the app:**
   ```bash
   python app.py
   ```
   Open http://localhost:5000

## Usage

- **Today** – Main page: today’s plan, schedule, reminders, counters, streaks, and punishment rules. Use “Done” to mark items and “+1” / “Log today” for counters and streaks.
- **Sync Tumblr** – Enter any Tumblr blog name (e.g. andrearose96), fetch posts, and extract commitments (needs `.env` keys).
- **Import text** – Paste any block of text; the parser will detect commitments and add them to your schedule/reminders/counters/streaks.

Data is stored in `data/commitments.db` (SQLite).

## API (optional)

- `GET /api/today?date=YYYY-MM-DD` – JSON for that day (schedule, reminders, counters, streaks, punishment triggers).
- `GET /api/assistant-message?date=YYYY-MM-DD` – Plain text “what to do today” message.
