import db, { seedStarterHabits } from './db.js';
import { todayStatus, checkIn, evaluateDeadlines, openPenalties, fulfillPenalty, findHabit } from './contracts.js';

const [,, command, ...args] = process.argv;

// Ensure base schema records exist if the physical database file is brand new
seedStarterHabits(db);

// Always catch up missed milestones immediately upon opening the app
evaluateDeadlines(db);

switch (command) {
  case 'init':
    console.log("✅ Habit Tracker database initialized and default habits seeded.");
    break;

  case 'today': {
    console.log(`\n📅 --- Today's Habit Schedule (${new Date().toLocaleDateString('en-CA')}) ---`);
    const habits = todayStatus(db);
    habits.forEach(h => {
      let statusSymbol = "⏳ Pending";
      if (h.status === 'done') statusSymbol = "✅ Done";
      if (h.status === 'failed') statusSymbol = "❌ Overdue / Failed";
      console.log(`  [${h.id}] ${h.title.padEnd(18)} - Status: ${statusSymbol}`);
    });
    console.log("");
    break;
  }

  case 'check-in': {
    const query = args.join(" ");
    if (!query) {
      console.error("❌ Error: Please specify a habit name or ID to check in (e.g., node src/cli.js check-in wake)");
      process.exit(1);
    }
    try {
      const habit = findHabit(db, query);
      const result = checkIn(db, habit.id);
      if (result === 'done') console.log(`🎉 Success! Checked into "${habit.title}" on time.`);
      if (result === 'failed') console.log(`🚨 Late check-in! "${habit.title}" logged as FAILED. Penalty triggered.`);
      if (result === 'already-logged') console.log(`ℹ️ "${habit.title}" has already been processed today.`);
    } catch (e) {
      console.error(`❌ ${e.message}`);
    }
    break;
  }

  case 'contracts': {
    const activePenalties = openPenalties(db);
    console.log(`\n📜 --- Active Penalty Contracts ---`);
    if (activePenalties.length === 0) {
      console.log("  🎉 Clean slate! No pending penalties or unfulfilled contracts.");
    } else {
      activePenalties.forEach(p => {
        console.log(`  [Penalty ID: ${p.id}] Broken Contract on ${p.date} for "${p.title}"`);
        console.log(`  ⚠️ Consequence: ${p.penalty_description}\n`);
      });
    }
    break;
  }

  case 'fulfill': {
    const penaltyId = Number(args[0]);
    if (!penaltyId || isNaN(penaltyId)) {
      console.error("❌ Error: Please specify a numeric Penalty ID to fulfill (e.g., node src/cli.js fulfill 1)");
      process.exit(1);
    }
    try {
      fulfillPenalty(db, penaltyId);
      console.log(`✅ Consequence accepted and penalty #${penaltyId} fulfilled. Back on track!`);
    } catch (e) {
      console.error(`❌ ${e.message}`);
    }
    break;
  }

  default:
    console.log(`
🚀 --- Habit Tracking CLI ---
Usage:
  node src/cli.js today           - View your morning-to-night routine status
  node src/cli.js check-in <name> - Check off a habit window (on-time or late)
  node src/cli.js contracts       - View triggered penalties you owe
  node src/cli.js fulfill <id>    - Resolve an outstanding penalty contract
    `);
}
