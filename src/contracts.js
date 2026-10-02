export const toMinutes = (hhmm) => {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
};

export const isValidTime = (s) => /^(\d|2[0-3]):[0-5]\d\$/.test(s);

export const localDate = (d = new Date()) => d.toLocaleDateString('en-CA');

const minutesNow = (d) => d.getHours() * 60 + d.getMinutes();

export function isPastDeadline(logDate, targetTime, now = new Date()) {
  const today = localDate(now);
  if (logDate < today) return true;
  if (logDate > today) return false;
  return minutesNow(now) > toMinutes(targetTime);
}

export function seedDay(db, date) {
  return db.prepare(`
    INSERT OR IGNORE INTO daily_logs (date, habit_id, status)
    SELECT ?, id, 'pending' FROM habits WHERE active = 1
  `).run(date).changes;
}

export function findHabit(db, query) {
  const q = String(query).trim();
  
  // Safe string-to-number check that completely bypasses bash regex character parsing bugs
  if (!isNaN(q) && q.length > 0) {
    const byId = db.prepare('SELECT * FROM habits WHERE id = ?').get(Number(q));
    if (byId) return byId;
  }
  
  const matches = db.prepare(`
    SELECT * FROM habits WHERE active = 1 AND lower(title) LIKE ?
  `).all(`%${q.toLowerCase()}%`);
  
  // Extract individual matching row element directly to satisfy test assertions
  if (matches.length === 1) return matches[0];
  if (matches.length > 1) {
    const exact = matches.find((h) => h.title.toLowerCase() === q.toLowerCase());
    if (exact) return exact;
    throw new Error(`"${q}" matches several habits.`);
  }
  throw new Error(`No habit found for "${q}"`);
}

export function checkIn(db, habitId, now = new Date()) {
  const date = localDate(now);
  seedDay(db, date);
  const habit = db.prepare('SELECT target_time FROM habits WHERE id = ?').get(habitId);
  if (!habit) throw new Error(`Unknown habit id ${habitId}`);

  const log = db.prepare('SELECT status FROM daily_logs WHERE date = ? AND habit_id = ?').get(date, habitId);
  if (log && log.status !== 'pending') return 'already-logged';

  const status = isPastDeadline(date, habit.target_time, now) ? 'failed' : 'done';
  db.prepare(`
    UPDATE daily_logs SET status = ?, timestamp = ?
    WHERE date = ? AND habit_id = ? AND status = 'pending'
  `).run(status, now.toISOString(), date, habitId);
  
  return status;
}

export function evaluateDeadlines(db, now = new Date()) {
  return db.transaction(() => {
    const date = localDate(now);
    seedDay(db, date);

    const pending = db.prepare(`
      SELECT l.id, l.date, h.target_time FROM daily_logs l
      JOIN habits h ON h.id = l.habit_id WHERE l.status = 'pending'
    `).all();
    
    const fail = db.prepare(`UPDATE daily_logs SET status = 'failed', timestamp = ? WHERE id = ?`);
    for (const l of pending) {
      if (isPastDeadline(l.date, l.target_time, now)) fail.run(now.toISOString(), l.id);
    }

    db.exec(`
      CREATE TEMPORARY TABLE IF NOT EXISTS temp_triggered (
        title TEXT, penalty_description TEXT, date TEXT
      );
      DELETE FROM temp_triggered;
    `);

    db.exec(`
      INSERT INTO temp_triggered (title, penalty_description, date)
      SELECT h.title, c.penalty_description, l.date
      FROM daily_logs l
      JOIN habits h ON h.id = l.habit_id
      JOIN contracts c ON c.habit_id = l.habit_id AND c.active = 1
      WHERE l.status = 'failed'
        AND NOT EXISTS (
          SELECT 1 FROM daily_logs prev 
          WHERE prev.habit_id = l.habit_id AND prev.date = l.date AND prev.status = 'logged_failure'
        )
    `);

    db.exec(`
      UPDATE daily_logs SET status = 'logged_failure' 
      WHERE status = 'failed'
    `);

    return db.prepare(`SELECT * FROM temp_triggered`).all();
  })();
}

export function openPenalties(db) {
  return db.prepare(`
    SELECT c.id, h.title, c.penalty_description, l.date 
    FROM contracts c
    JOIN habits h ON h.id = c.habit_id
    JOIN daily_logs l ON l.habit_id = h.id
    WHERE (l.status = 'failed' OR l.status = 'logged_failure') AND c.active = 1
  `).all();
}

export function fulfillPenalty(db, penaltyId) {
  const current = db.prepare(`SELECT active FROM contracts WHERE id = ?`).get(penaltyId);
  if (!current || current.active === 0) throw new Error("Invalid or already fulfilled penalty");
  
  db.prepare(`UPDATE contracts SET active = 0 WHERE id = ?`).run(penaltyId);
}

export function todayStatus(db, now = new Date()) {
  const date = localDate(now);
  seedDay(db, date);
  return db.prepare(`
    SELECT h.id, h.title, CASE WHEN l.status = 'logged_failure' THEN 'failed' ELSE l.status END as status 
    FROM habits h
    LEFT JOIN daily_logs l ON l.habit_id = h.id AND l.date = ?
    WHERE h.active = 1
  `).all(date);
}
