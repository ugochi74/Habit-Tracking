CREATE TABLE IF NOT EXISTS habits (
  id           INTEGER PRIMARY KEY,
  title        TEXT NOT NULL UNIQUE,
  description  TEXT,
  window_start TEXT,                 -- 'HH:MM', optional (e.g. start of a morning routine window)
  target_time  TEXT NOT NULL,        -- 'HH:MM' deadline
  sort_order   INTEGER NOT NULL DEFAULT 0,
  active       INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS daily_logs (
  id        INTEGER PRIMARY KEY,
  date      TEXT NOT NULL,           -- 'YYYY-MM-DD' (local date)
  habit_id  INTEGER NOT NULL REFERENCES habits(id),
  status    TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'done', 'failed')),
  timestamp TEXT,                    -- ISO time the status last changed
  UNIQUE (date, habit_id)
);

CREATE TABLE IF NOT EXISTS contracts (
  id                  INTEGER PRIMARY KEY,
  habit_id            INTEGER NOT NULL UNIQUE REFERENCES habits(id),
  penalty_description TEXT NOT NULL,
  forfeit_amount      REAL,          -- optional money stake
  active              INTEGER NOT NULL DEFAULT 1
);

-- One row per triggered penalty, so each failure fires exactly once.
CREATE TABLE IF NOT EXISTS penalty_events (
  id           INTEGER PRIMARY KEY,
  log_id       INTEGER NOT NULL UNIQUE REFERENCES daily_logs(id),
  contract_id  INTEGER NOT NULL REFERENCES contracts(id),
  triggered_at TEXT NOT NULL,
  fulfilled    INTEGER NOT NULL DEFAULT 0
);
