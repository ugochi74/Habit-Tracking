import { DatabaseSync } from 'node:sqlite';
import path from 'node:path';

let dbInstance = null;
let currentDbPath = null;

export function openDb(dbPathStr = '.database.db') {
  const resolvedPath = dbPathStr === ':memory:' ? ':memory:' : path.resolve(dbPathStr);
  
  if (!dbInstance || currentDbPath !== resolvedPath || resolvedPath === ':memory:') {
    const db = new DatabaseSync(resolvedPath);
    
    if (resolvedPath !== ':memory:') {
      dbInstance = db;
      currentDbPath = resolvedPath;
    }
    
    db.exec(`
      CREATE TABLE IF NOT EXISTS habits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        target_time TEXT,
        description TEXT,
        active INTEGER DEFAULT 1
      );

      CREATE TABLE IF NOT EXISTS daily_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        habit_id INTEGER,
        status TEXT DEFAULT 'pending',
        timestamp TEXT,
        UNIQUE(date, habit_id)
      );

      CREATE TABLE IF NOT EXISTS contracts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        habit_id INTEGER,
        penalty_description TEXT,
        forfeit_amount INTEGER,
        active INTEGER DEFAULT 1
      );
    `);

    if (typeof db.transaction !== 'function') {
      db.transaction = function (fn) {
        return (...args) => {
          db.exec('BEGIN TRANSACTION;');
          try {
            const result = fn(...args);
            db.exec('COMMIT;');
            return result;
          } catch (error) {
            db.exec('ROLLBACK;');
            throw error;
          }
        };
      };
    }
    
    return db;
  }
  
  return dbInstance;
}

export function seedStarterHabits(db) {
  const targetDb = db || openDb();
  
  targetDb.exec(`DELETE FROM daily_logs; DELETE FROM habits; DELETE FROM contracts;`);

  // Fixed Query: Ensured exactly 5 explicit column hooks map to 5 bound parameters
  const insertHabit = targetDb.prepare(`
    INSERT INTO habits (id, title, target_time, description, active) 
    VALUES (?, ?, ?, ?, ?)
  `);
  
  insertHabit.run(1, "Wake-up", "07:00", "Morning block tracking", 1);
  insertHabit.run(2, "Morning routine", "08:30", "Planning window", 1);
  insertHabit.run(3, "Work closure", "18:00", "Hard wrap validation", 1);

  const insertContract = targetDb.prepare(`
    INSERT INTO contracts (habit_id, penalty_description, forfeit_amount, active) 
    VALUES (?, ?, ?, 1)
  `);
  insertContract.run(3, "Off screens and out of the office", 10);
}

const dbProxy = {
  prepare(...args) { return openDb().prepare(...args); },
  exec(...args) { return openDb().exec(...args); },
  transaction(...args) { return openDb().transaction(...args); }
};

export default dbProxy;
