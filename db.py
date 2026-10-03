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


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()
