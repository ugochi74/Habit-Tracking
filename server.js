import express from 'express';
import db, { seedStarterHabits } from './src/db.js';
import { todayStatus, checkIn, evaluateDeadlines, openPenalties, fulfillPenalty } from './src/contracts.js';

const app = express();
const PORT = 3000;

app.use(express.urlencoded({ extended: true }));

seedStarterHabits(db);

app.get('/', (req, res) => {
  evaluateDeadlines(db);

  const habits = todayStatus(db);
  const penalties = openPenalties(db);
  const todayDate = new Date().toLocaleDateString('en-CA');

  const historyLogs = db.prepare(`
    SELECT date, 
           COUNT(CASE WHEN status = 'done' THEN 1 END) as completed,
           COUNT(CASE WHEN status IN ('failed', 'logged_failure') THEN 1 END) as failed,
           COUNT(*) as total
    FROM daily_logs
    GROUP BY date
    ORDER BY date DESC
    LIMIT 7
  `).all();

  let html = `
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Habit Tracker Pro Dashboard</title>
      <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f4f6f8; color: #333; max-width: 900px; margin: 40px auto; padding: 0 20px; }
        h1, h2, h3 { color: #111; margin-top: 0; }
        .grid { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; }
        @media(max-width: 768px) { .grid { grid-template-columns: 1fr; } }
        .card { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.02), 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 20px; }
        .habit-item { display: flex; justify-content: space-between; align-items: center; padding: 14px 0; border-bottom: 1px solid #f0f0f0; }
        .habit-item:last-child { border-bottom: none; }
        .status { font-weight: bold; padding: 5px 10px; border-radius: 6px; font-size: 0.85em; text-transform: uppercase; letter-spacing: 0.5px; }
        .status.pending { background: #eef2f7; color: #5f6368; }
        .status.done { background: #e6f4ea; color: #137333; }
        .status.failed { background: #fce8e6; color: #c5221f; }
        .btn { background: #1a73e8; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 500; font-size: 0.9em; transition: background 0.2s; }
        .btn:hover { background: #1557b0; }
        .btn-secondary { background: #5f6368; }
        .btn-secondary:hover { background: #45494e; }
        .penalty-card { background: #fff8f7; border-left: 4px solid #c5221f; }
        .form-group { margin-bottom: 15px; }
        label { display: block; font-weight: 500; margin-bottom: 6px; font-size: 0.9em; color: #444; }
        input[type="text"], input[type="time"], input[type="number"], textarea { width: 100%; padding: 10px; border: 1px solid #dadce0; border-radius: 6px; box-sizing: border-box; font-family: inherit; font-size: 0.95em; }
        input:focus, textarea:focus { outline: none; border-color: #1a73e8; box-shadow: 0 0 0 2px rgba(26,115,232,0.2); }
        .history-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f0f0f0; font-size: 0.95em; }
        .history-row:last-child { border-bottom: none; }
        .completed-count { color: #137333; font-weight: 600; }
        .failed-count { color: #c5221f; font-weight: 600; }
      </style>
    </head>
    <body>
      <div style="margin-bottom: 30px;">
        <h1 style="margin-bottom: 5px;">🎯 Habit Contract Pro</h1>
        <p style="color: #666; margin: 0;">Accountability System &bull; Active Windows Engine For: <strong>${todayDate}</strong></p>
      </div>

      <div class="grid">
        <div>
          <div class="card">
            <h2>⏱️ Today's Routine Timeline</h2>
  `;

  habits.forEach(h => {
    let statusClass = h.status;
    let statusLabel = h.status === 'pending' ? '⏳ Pending' : h.status === 'done' ? '✅ Done' : '❌ Failed';
    
    html += '<div class="habit-item">';
    html += '  <div>';
    html += '    <strong style="font-size: 1.1em; color: #111;">' + h.title + '</strong>';
    html += '  </div>';
    html += '  <div>';
    html += '    <span class="status ' + statusClass + '">' + statusLabel + '</span>';
    
    if (h.status === 'pending') {
      html += '  <form action="/check-in" method="POST" style="display:inline; margin-left:12px;">';
      html += '    <input type="hidden" name="habitId" value="' + h.id + '">';
      html += '    <button type="submit" class="btn">Check In</button>';
      html += '  </form>';
    }
    
    html += '  </div>';
    html += '</div>';
  });

  html += `
          </div>

          <h2>📜 Outstanding Accountability Penalties</h2>
  `;

  if (penalties.length === 0) {
    html += `
      <div class="card" style="background:#e6f4ea; color:#137333; border: 1px solid #c4eed0; font-weight: 500;">
        🎉 Integrity intact! No broken contracts or outstanding penalties to resolve right now.
      </div>
    `;
  } else {
    penalties.forEach(p => {
      html += '<div class="card penalty-card habit-item">';
      html += '  <div style="padding-right: 15px;">';
      html += '    <strong style="color: #c5221f; font-size: 1.05em;">Broken Rule: ' + p.title + '</strong> <span style="font-size:0.85em; color:#666;">(' + p.date + ')</span><br>';
      html += '    <p style="margin: 6px 0 0 0; color:#444; font-size: 0.95em;">⚠️ <strong>Consequence:</strong> ' + p.penalty_description + '</p>';
      if (p.forfeit_amount) {
        html += '  <p style="margin: 4px 0 0 0; color: #b06000; font-size: 0.9em;">💸 <strong>Stakes:</strong> ₦' + p.forfeit_amount + ' Contract Forfeiture</p>';
      }
      html += '  </div>';
      html += '  <form action="/fulfill" method="POST">';
      html += '    <input type="hidden" name="penaltyId" value="' + p.id + '">';
      html += '    <button type="submit" class="btn btn-secondary" style="white-space: nowrap;">I Fulfilled My Penalty</button>';
      html += '  </form>';
      html += '</div>';
    });
  }

  html += `
        </div>

        <div>
          <div class="card">
            <h3 style="border-bottom: 1px solid #eee; padding-bottom: 10px;">➕ Add Habit & Contract</h3>
            <form action="/add-habit" method="POST">
              <div class="form-group">
                <label for="title">Habit Objective Name</label>
                <input type="text" id="title" name="title" placeholder="e.g., Morning Out of Bed" required>
              </div>
              <div class="form-group">
                <label for="target_time">Daily Deadline Time (HH:MM)</label>
                <input type="time" id="target_time" name="target_time" required>
              </div>
              <div class="form-group">
                <label for="penalty_desc">Contract Consequence / Penalty</label>
                <textarea id="penalty_desc" name="penalty_description" rows="2" placeholder="e.g., No screens for 2 hours" required></textarea>
              </div>
              <div class="form-group">
                <label for="forfeit_amount">Financial Stake (Optional ₦)</label>
                <input type="number" id="forfeit_amount" name="forfeit_amount" placeholder="0" min="0">
              </div>
              <button type="submit" class="btn" style="width: 100%; margin-top: 5px;">Lock In Contract</button>
            </form>
          </div>

          <div class="card">
            <h3 style="border-bottom: 1px solid #eee; padding-bottom: 10px;">📊 Historical Performance</h3>
  `;

  if (historyLogs.length === 0) {
    html += `<p style="color: #777; font-size: 0.9em; margin: 0;">Logs will populate here as days pass.</p>`;
  } else {
    historyLogs.forEach(row => {
      html += `
        <div class="history-row">
          <span style="font-weight: 500; color:#555;">${row.date}</span>
          <span>
            <span class="completed-count">✓ ${row.completed}</span> / 
            <span class="failed-count">✗ ${row.failed}</span>
          </span>
        </div>
      `;
    });
  }

  html += `
          </div>
        </div>
      </div>
    </body>
    </html>
  `;
  res.send(html);
});

app.post('/check-in', (req, res) => {
  const { habitId } = req.body;
  checkIn(db, Number(habitId));
  res.redirect('/');
});

app.post('/fulfill', (req, res) => {
  const { penaltyId } = req.body;
  try {
    fulfillPenalty(db, Number(penaltyId));
  } catch (e) {}
  res.redirect('/');
});

app.post('/add-habit', (req, res) => {
  const { title, target_time, penalty_description, forfeit_amount } = req.body;
  
  try {
    db.transaction(() => {
      const habitRes = db.prepare(`
        INSERT INTO habits (title, target_time, description, active)
        VALUES (?, ?, 'User custom timing window block', 1)
      `).run(title, target_time);
      
      const newHabitId = habitRes.lastInsertRowid;

      db.prepare(`
        INSERT INTO contracts (habit_id, penalty_description, forfeit_amount, active)
        VALUES (?, ?, ?, 1)
      `).run(newHabitId, penalty_description, Number(forfeit_amount) || 0);
    })();
  } catch (e) {
    console.error("Failed to append customized contract:", e);
  }

  res.redirect('/');
});

app.listen(PORT, () => {
  console.log(`\n🚀 Web Dashboard Fixed! Open your browser to: http://localhost:${PORT}\n`);
});
