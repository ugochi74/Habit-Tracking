# Habit-Tracking

A local habit tracking and accountability system with habit contracts. Node.js 22, ES modules, SQLite.

## Setup

```bash
npm install
node src/cli.js init     # creates data/habits.db with 3 starter habits + contracts
npm test                 # 11 tests
```

## Daily use

```bash
node src/cli.js today              # timeline for today
node src/cli.js done wake          # check a habit off (partial name or id)
node src/cli.js watch              # leave running: checks deadlines every 60s
node src/cli.js penalties          # what you owe
node src/cli.js fulfill 3          # mark penalty #3 as served
node src/cli.js report 7           # last 7 days
```

## Customising

```bash
node src/cli.js add "Read 20 pages" 21:30 --desc "Before bed"
node src/cli.js contract "Read" "Donate to a cause I dislike" --forfeit 5
node src/cli.js contract-doc --name "Your Name" --partner "Friend's Name"
```

`contract-doc` fills `contracts/habit-contract.md` with your current habits and stakes and
writes `contracts/habit-contract.generated.md` for you to sign.

Use `HABIT_DB=/path/to/other.db` to point at a different database.

## How the contract works

1. Each day, every active habit gets a `pending` row in `daily_logs`.
2. `done <habit>` marks it `done` if you're on time, `failed` if you're late (18:00 exactly is on time).
3. `evaluateDeadlines` (run by `watch`, `check`, `today`, and `done`) turns overdue `pending` rows into `failed`.
4. Every failed log whose habit has an active contract gets one row in `penalty_events`. It never fires twice.
5. Missed days are caught up the next time the app runs.

## Layout

```
src/schema.sql     tables: habits, daily_logs, contracts, penalty_events
src/db.js          open database, run schema, seed starter habits
src/contracts.js   deadline logic, check-ins, failure protocol, reports
src/cli.js         command-line interface
test/              node:test suite (fake clocks, no waiting)
contracts/         markdown contract template
```

## Ideas for later

- Express + a small HTML page on top of `contracts.js` (the logic is already separate from the CLI)
- Excused days declared before a deadline
- Desktop notifications when a penalty triggers
