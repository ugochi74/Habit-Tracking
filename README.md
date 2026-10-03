# Habit-Tracking

A small local website for tracking daily habits and holding yourself to a habit contract.
Python 3, Flask, SQLite.

## Run it

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. The database is created on first run with three starter habits
(Wake-up 06:00, Morning routine 06:00–07:30, Work closure 18:00), each with a penalty you can edit.

Run the tests: `python -m unittest discover -s tests -v`

If `python3 -m venv` fails on Ubuntu/Debian: `sudo apt install python3-venv`.

## Pages

| Page | What it does |
|------|--------------|
| Today | Timeline of today's habits with a **Check off** button and time left. Refreshes every minute. |
| Penalties | Penalties triggered by failures. Mark each one served. |
| Habits | Add habits, set or change each habit's penalty and forfeit, archive habits. |
| History | Success rate per habit and a day-by-day grid (7/14/30/90 days). |
| Contract | The contract, filled in from your habits and stakes. Print it or download as Markdown. |

## How the contract works

1. Each day, every active habit gets a `pending` row in `daily_logs`.
2. **Check off** marks it `done` if you're on time (18:00 exactly counts) and `failed` if you're late.
3. Every page view runs `evaluate_deadlines`, which turns overdue `pending` rows into `failed`.
4. Each failed habit with an active contract creates one row in `penalty_events`. It never fires twice.
5. Days you missed while the server was off are caught up the next time you open the site.
6. A habit added after today's deadline has passed starts tomorrow, so it can't fail instantly.

The tracker can't force you to serve a penalty. It records it and keeps nagging until you mark it served.

## Files

```
app.py          Flask routes and validation
logic.py        deadline rules, check-ins, failure protocol, history (no Flask in here)
db.py           SQLite connection + starter habits
schema.sql      tables: habits, daily_logs, contracts, penalty_events
templates/      Jinja pages
static/         stylesheet
contracts/      Markdown contract template
tests/          23 tests (fake clocks, no waiting)
```

Settings (environment variables): `HABIT_DB` (database path), `PORT`, `FLASK_DEBUG=1`.
The server only listens on 127.0.0.1, so it is reachable from your computer only.
