"""SQLite connection handling and starter data."""
import sqlite3
from pathlib import Path

from flask import current_app, g

import logic

SCHEMA = Path(__file__).with_name("schema.sql")

STARTER_HABITS = [
    dict(title="Wake-up", description="Out of bed, no snooze", window_start=None,
         target_time="06:00", penalty="No phone until noon"),
    dict(title="Morning routine", description="Water, stretch, plan the day", window_start="06:00",
         target_time="07:30", penalty="20 push-ups before dinner"),
    dict(title="Work closure", description="Shut the laptop, write tomorrow's top 3",
         window_start=None, target_time="18:00", penalty="No screens after 8 PM tonight"),
]


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text())
    return conn


def seed_starter_habits(conn, now):
    for h in STARTER_HABITS:
        logic.add_habit(conn, h["title"], h["target_time"], now, description=h["description"],
                        window_start=h["window_start"], penalty=h["penalty"])


# Applied once per database, then remembered in `meta`, so archiving a habit keeps it archived.
# No contract by default: set the penalty yourself once the time is right for you.
ONE_TIME_SEEDS = {
    "daily-devotion-v1": dict(title="Daily devotion", description="Read the Bible and pray",
                              window_start="06:00", target_time="06:45"),
}


def apply_one_time_seeds(conn, now):
    for key, h in ONE_TIME_SEEDS.items():
        if conn.execute("SELECT 1 FROM meta WHERE key = ?", (key,)).fetchone():
            continue
        try:
            logic.add_habit(conn, h["title"], h["target_time"], now,
                            description=h["description"], window_start=h["window_start"])
        except ValueError:
            pass  # you already have a habit with that name; leave it alone
        with conn:
            conn.execute("INSERT INTO meta (key) VALUES (?)", (key,))


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()
