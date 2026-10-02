import { test } from 'node:test';
import assert from 'node:assert/strict';
import { openDb, seedStarterHabits } from '../src/db.js';
import {
  checkIn, evaluateDeadlines, findHabit, fulfillPenalty, isPastDeadline,
  openPenalties, todayStatus,
} from '../src/contracts.js';

// Local-time Date helper: at(2026, 10, 2, 17, 59)
const at = (y, mo, d, h, mi) => new Date(y, mo - 1, d, h, mi, 0);

function freshDb() {
  const db = openDb(':memory:');
  seedStarterHabits(db);
  return db;
}

test('isPastDeadline: exact deadline minute is still on time', () => {
  assert.equal(isPastDeadline('2026-10-02', '18:00', at(2026, 10, 2, 18, 0)), false);
  assert.equal(isPastDeadline('2026-10-02', '18:00', at(2026, 10, 2, 18, 1)), true);
  assert.equal(isPastDeadline('2026-10-02', '18:00', at(2026, 10, 2, 17, 59)), false);
});

test('isPastDeadline: past days are always overdue, future days never', () => {
  assert.equal(isPastDeadline('2026-10-01', '23:59', at(2026, 10, 2, 0, 5)), true);
  assert.equal(isPastDeadline('2026-10-03', '00:01', at(2026, 10, 2, 23, 59)), false);
});

test('on-time check-in is done and triggers nothing', () => {
  const db = freshDb();
  const work = findHabit(db, 'work');
  assert.equal(checkIn(db, work.id, at(2026, 10, 2, 17, 30)), 'done');
  assert.equal(evaluateDeadlines(db, at(2026, 10, 2, 19, 0)).filter((p) => p.title === 'Work closure').length, 0);
});

test('Work closure unchecked at 6:01 PM triggers the failure protocol', () => {
  const db = freshDb();
  const before = evaluateDeadlines(db, at(2026, 10, 2, 17, 59)); // wake-up and morning routine already overdue
  assert.ok(!before.some((p) => p.title === 'Work closure'), 'not yet 6:00 PM + 1 min');
  const triggered = evaluateDeadlines(db, at(2026, 10, 2, 18, 1));
  const work = triggered.find((p) => p.title === 'Work closure');
  assert.ok(work, 'work closure penalty should fire');
  assert.match(work.penalty_description, /screens/);
});

test('evaluateDeadlines is idempotent: a failure fires exactly once', () => {
  const db = freshDb();
  const first = evaluateDeadlines(db, at(2026, 10, 2, 18, 5));
  const second = evaluateDeadlines(db, at(2026, 10, 2, 18, 6));
  assert.ok(first.length >= 1);
  assert.equal(second.length, 0);
  assert.equal(openPenalties(db).length, first.length);
});

test('late check-in is recorded as failed and still triggers the penalty', () => {
  const db = freshDb();
  const work = findHabit(db, 'work');
  assert.equal(checkIn(db, work.id, at(2026, 10, 2, 18, 30)), 'failed');
  const triggered = evaluateDeadlines(db, at(2026, 10, 2, 18, 31));
  assert.ok(triggered.some((p) => p.title === 'Work closure'));
});

test('a done habit cannot be changed by checking in again', () => {
  const db = freshDb();
  const wake = findHabit(db, 'wake');
  assert.equal(checkIn(db, wake.id, at(2026, 10, 2, 5, 55)), 'done');
  assert.equal(checkIn(db, wake.id, at(2026, 10, 2, 9, 0)), 'already-logged');
  assert.equal(todayStatus(db, at(2026, 10, 2, 9, 0)).find((r) => r.id === wake.id).status, 'done');
});

test('missed days are caught up when the app is opened later', () => {
  const db = freshDb();
  evaluateDeadlines(db, at(2026, 10, 1, 8, 0));            // day 1 seeded, nothing overdue except wake-up
  const later = evaluateDeadlines(db, at(2026, 10, 2, 9, 0)); // opened next morning
  assert.ok(later.some((p) => p.title === 'Work closure' && p.date === '2026-10-01'));
});

test('habits without a contract fail but trigger no penalty', () => {
  const db = freshDb();
  db.prepare(`INSERT INTO habits (title, target_time) VALUES ('Read', '21:00')`).run();
  const triggered = evaluateDeadlines(db, at(2026, 10, 2, 22, 0));
  assert.ok(!triggered.some((p) => p.title === 'Read'));
  const row = todayStatus(db, at(2026, 10, 2, 22, 0)).find((r) => r.title === 'Read');
  assert.equal(row.status, 'failed');
});

test('fulfilling a penalty removes it from the open list', () => {
  const db = freshDb();
  evaluateDeadlines(db, at(2026, 10, 2, 18, 5));
  const [p] = openPenalties(db);
  fulfillPenalty(db, p.id);
  assert.ok(!openPenalties(db).some((x) => x.id === p.id));
  assert.throws(() => fulfillPenalty(db, p.id));
});

test('findHabit matches by partial name and by id, and rejects unknowns', () => {
  const db = freshDb();
  assert.equal(findHabit(db, 'morning').title, 'Morning routine');
  assert.equal(findHabit(db, String(findHabit(db, 'wake').id)).title, 'Wake-up');
  assert.throws(() => findHabit(db, 'nonsense'));
});
