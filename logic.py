"""Business logic: deadlines, check-ins, and the habit-contract failure protocol.

Every function takes `now` (a datetime) so it can be tested with fake times.
Functions take an open sqlite3 connection and manage their own transactions.
"""
import re
import sqlite3
from datetime import timedelta


def to_minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def is_valid_time(value):
    return bool(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value or ""))


def local_date(now):
    return now.date().isoformat()


def is_past_deadline(log_date, target_time, now):
    """18:00 exactly is still on time; 18:01 is overdue."""
    today = local_date(now)
    if log_date < today:
        return True
    if log_date > today:
        return False
    return now.hour * 60 + now.minute > to_minutes(target_time)


def time_left(target_time, now):
    mins = to_minutes(target_time) - (now.hour * 60 + now.minute)
    if mins < 0:
        return "overdue"
    h, m = divmod(mins, 60)
    return f"{h}h {m}m left" if h else f"{m}m left"


# ---------- habits and contracts ----------

def set_contract(db, habit_id, penalty, forfeit=None):
    """Create/replace a habit's contract. A blank penalty switches the contract off."""
    penalty = (penalty or "").strip()
    if not penalty:
        db.execute("UPDATE contracts SET active = 0 WHERE habit_id = ?", (habit_id,))
        return
    db.execute(
        """INSERT INTO contracts (habit_id, penalty_description, forfeit_amount) VALUES (?, ?, ?)
           ON CONFLICT(habit_id) DO UPDATE SET penalty_description = excluded.penalty_description,
             forfeit_amount = excluded.forfeit_amount, active = 1""",
        (habit_id, penalty, forfeit))


def add_habit(db, title, target_time, now, description=None, window_start=None,
              penalty=None, forfeit=None):
    title = (title or "").strip()
    if not title:
        raise ValueError("Give the habit a title.")
    if not is_valid_time(target_time):
        raise ValueError("The deadline must be a time like 07:30.")
    if window_start and not is_valid_time(window_start):
        raise ValueError("The window start must be a time like 06:00.")
    if db.execute("SELECT 1 FROM habits WHERE active = 1 AND lower(title) = lower(?)",
                  (title,)).fetchone():
        raise ValueError(f'You already have a habit called "{title}".')

    # A habit whose deadline has already passed today starts tomorrow,
    # so adding it late in the day doesn't instantly fail it.
    today = local_date(now)
    start = today if not is_past_deadline(today, target_time, now) else \
        (now.date() + timedelta(days=1)).isoformat()
    with db:
        cur = db.execute(
            """INSERT INTO habits (title, description, window_start, target_time, start_date, sort_order)
               VALUES (?, ?, ?, ?, ?, (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM habits))""",
            (title, description, window_start or None, target_time, start))
        set_contract(db, cur.lastrowid, penalty, forfeit)
    return cur.lastrowid


def archive_habit(db, habit_id):
    with db:
        db.execute("UPDATE habits SET active = 0 WHERE id = ?", (habit_id,))
        db.execute("DELETE FROM daily_logs WHERE habit_id = ? AND status = 'pending'", (habit_id,))


# ---------- daily tracking ----------

def seed_day(db, day):
    """Create the day's pending rows. Safe to call repeatedly."""
    db.execute(
        """INSERT OR IGNORE INTO daily_logs (date, habit_id)
           SELECT ?, id FROM habits WHERE active = 1 AND start_date <= ?""", (day, day))


def check_in(db, habit_id, now):
    """Check a habit off. A check-in after the deadline is recorded as a failure.
    Returns 'done' | 'failed' | 'already-logged' | 'not-scheduled'."""
    day = local_date(now)
    with db:
        seed_day(db, day)
        habit = db.execute("SELECT target_time FROM habits WHERE id = ? AND active = 1",
                           (habit_id,)).fetchone()
        if habit is None:
            raise ValueError("That habit doesn't exist.")
        status = "failed" if is_past_deadline(day, habit["target_time"], now) else "done"
        changed = db.execute(
            """UPDATE daily_logs SET status = ?, timestamp = ?
               WHERE date = ? AND habit_id = ? AND status = 'pending'""",
            (status, now.isoformat(timespec="seconds"), day, habit_id)).rowcount
        if changed:
            return status
        exists = db.execute("SELECT 1 FROM daily_logs WHERE date = ? AND habit_id = ?",
                            (day, habit_id)).fetchone()
    return "already-logged" if exists else "not-scheduled"


def evaluate_deadlines(db, now):
    """The failure protocol. Idempotent: run it as often as you like.
    Returns the penalties triggered by this call."""
    with db:
        seed_day(db, local_date(now))

        # Step 1: pending logs past their deadline become failed
        pending = db.execute(
            """SELECT l.id, l.date, h.target_time FROM daily_logs l
               JOIN habits h ON h.id = l.habit_id
               WHERE l.status = 'pending' AND h.active = 1""").fetchall()
        for l in pending:
            if is_past_deadline(l["date"], l["target_time"], now):
                db.execute("UPDATE daily_logs SET status = 'failed', timestamp = ? WHERE id = ?",
                           (now.isoformat(timespec="seconds"), l["id"]))

        # Step 2: each failed log with an active contract and no penalty yet gets one
        fresh = db.execute(
            """SELECT l.id AS log_id, l.date, h.title, c.id AS contract_id,
                      c.penalty_description, c.forfeit_amount
               FROM daily_logs l
               JOIN habits h ON h.id = l.habit_id
               JOIN contracts c ON c.habit_id = l.habit_id AND c.active = 1
               WHERE l.status = 'failed'
                 AND NOT EXISTS (SELECT 1 FROM penalty_events p WHERE p.log_id = l.id)
               ORDER BY l.date, h.sort_order""").fetchall()
        for f in fresh:
            db.execute("INSERT INTO penalty_events (log_id, contract_id, triggered_at) VALUES (?, ?, ?)",
                       (f["log_id"], f["contract_id"], now.isoformat(timespec="seconds")))
    return fresh


# ---------- reading data for the pages ----------

def today_status(db, now):
    day = local_date(now)
    with db:
        seed_day(db, day)
    rows = db.execute(
        """SELECT h.id, h.title, h.description, h.window_start, h.target_time,
                  l.status, l.timestamp, c.penalty_description, c.forfeit_amount
           FROM habits h
           JOIN daily_logs l ON l.habit_id = h.id AND l.date = ?
           LEFT JOIN contracts c ON c.habit_id = h.id AND c.active = 1
           WHERE h.active = 1
           ORDER BY h.sort_order, h.target_time""", (day,)).fetchall()
    items = []
    for r in rows:
        item = dict(r)
        item["time_left"] = time_left(r["target_time"], now) if r["status"] == "pending" else None
        items.append(item)
    return items


def open_penalties(db):
    return db.execute(
        """SELECT p.id, l.date, h.title, c.penalty_description, c.forfeit_amount, p.triggered_at
           FROM penalty_events p
           JOIN daily_logs l ON l.id = p.log_id
           JOIN habits h ON h.id = l.habit_id
           JOIN contracts c ON c.id = p.contract_id
           WHERE p.fulfilled = 0 ORDER BY p.triggered_at, p.id""").fetchall()


def fulfill_penalty(db, penalty_id):
    with db:
        changed = db.execute("UPDATE penalty_events SET fulfilled = 1 WHERE id = ? AND fulfilled = 0",
                             (penalty_id,)).rowcount
    if not changed:
        raise ValueError("That penalty is already served or doesn't exist.")


def history(db, days, now):
    """Grid of statuses (newest day first) plus a per-habit summary."""
    dates = [(now.date() - timedelta(days=i)).isoformat() for i in range(days)]
    since = dates[-1]
    grid = {(r["date"], r["habit_id"]): r["status"]
            for r in db.execute("SELECT date, habit_id, status FROM daily_logs WHERE date >= ?", (since,))}
    habits = db.execute(
        """SELECT id, title FROM habits
           WHERE active = 1 OR id IN (SELECT habit_id FROM daily_logs WHERE date >= ?)
           ORDER BY sort_order""", (since,)).fetchall()
    summary = []
    for h in habits:
        statuses = [grid.get((d, h["id"])) for d in dates]
        done, failed = statuses.count("done"), statuses.count("failed")
        summary.append({"title": h["title"], "done": done, "failed": failed,
                        "pending": statuses.count("pending"),
                        "rate": round(100 * done / (done + failed)) if done + failed else None})
    return {"dates": dates, "habits": habits, "grid": grid, "summary": summary}


def contract_rows(db):
    return db.execute(
        """SELECT h.title, h.window_start, h.target_time,
                  c.penalty_description, c.forfeit_amount
           FROM habits h LEFT JOIN contracts c ON c.habit_id = h.id AND c.active = 1
           WHERE h.active = 1 ORDER BY h.sort_order""").fetchall()


def render_contract_markdown(template_text, rows, name, partner, now):
    commitments = ["| Habit | Window | Deadline |", "|-------|--------|----------|"] + [
        f"| {r['title']} | {('from ' + r['window_start']) if r['window_start'] else '-'} | {r['target_time']} |"
        for r in rows]
    stakes = ["| Habit | Penalty on failure | Forfeit |", "|-------|--------------------|---------|"] + [
        f"| {r['title']} | {r['penalty_description'] or '(no contract)'} | "
        f"{r['forfeit_amount'] if r['forfeit_amount'] is not None else 'none'} |" for r in rows]
    return (template_text
            .replace("{{name}}", name or "________")
            .replace("{{partner}}", partner or "the Habit-Tracking system")
            .replace("{{start_date}}", local_date(now))
            .replace("{{commitments_table}}", "\n".join(commitments))
            .replace("{{stakes_table}}", "\n".join(stakes)))
