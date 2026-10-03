"""Habit-Tracking: a small local website for habits, deadlines, and contracts."""
import os
from contextlib import closing
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, flash, redirect, render_template, request, url_for

import db as database
import logic

BASE = Path(__file__).parent


def parse_forfeit(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        raise ValueError("The forfeit must be a number (or leave it blank).")
    if value < 0:
        raise ValueError("The forfeit can't be negative.")
    return value


def create_app(db_path=None, clock=None):
    app = Flask(__name__)
    app.config.update(
        DATABASE=db_path or os.environ.get("HABIT_DB", str(BASE / "data" / "habits.db")),
        SECRET_KEY=os.environ.get("SECRET_KEY", "local-dev-only"),
        CLOCK=clock or datetime.now,
    )
    if app.config["DATABASE"] != ":memory:":
        Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    def now():
        return app.config["CLOCK"]()

    # First run: create the database and the three starter habits.
    with closing(database.connect(app.config["DATABASE"])) as conn:
        if conn.execute("SELECT COUNT(*) FROM habits").fetchone()[0] == 0:
            database.seed_starter_habits(conn, now())

    app.teardown_appcontext(database.close_db)

    @app.before_request
    def run_failure_protocol():
        """Every page view checks deadlines and announces any newly triggered penalty."""
        if request.endpoint == "static":
            return
        for p in logic.evaluate_deadlines(database.get_db(), now()):
            stake = f" (forfeit {p['forfeit_amount']:g})" if p["forfeit_amount"] is not None else ""
            flash(f"Contract triggered: \"{p['title']}\" failed on {p['date']}. "
                  f"Penalty: {p['penalty_description']}{stake}", "penalty")

    @app.context_processor
    def inject_globals():
        count = database.get_db().execute(
            "SELECT COUNT(*) FROM penalty_events WHERE fulfilled = 0").fetchone()[0]
        return {"open_penalty_count": count}

    # ---------- Today ----------

    @app.get("/")
    def index():
        items = logic.today_status(database.get_db(), now())
        return render_template(
            "today.html", items=items,
            done_count=sum(1 for i in items if i["status"] == "done"),
            today_label=now().strftime("%A, %d %B %Y"))

    @app.post("/habits/<int:habit_id>/done")
    def check_off(habit_id):
        try:
            result = logic.check_in(database.get_db(), habit_id, now())
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("index"))
        messages = {
            "done": ("Checked off, on time.", "ok"),
            "failed": ("That was after the deadline, so it counts as failed.", "error"),
            "already-logged": ("Already logged for today.", "error"),
            "not-scheduled": ("That habit isn't scheduled for today.", "error"),
        }
        text, kind = messages[result]
        flash(text, kind)
        return redirect(url_for("index"))

    # ---------- Penalties ----------

    @app.get("/penalties")
    def penalties():
        return render_template("penalties.html", rows=logic.open_penalties(database.get_db()))

    @app.post("/penalties/<int:penalty_id>/fulfill")
    def fulfill(penalty_id):
        try:
            logic.fulfill_penalty(database.get_db(), penalty_id)
            flash("Penalty marked as served.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("penalties"))

    # ---------- Manage habits and contracts ----------

    @app.get("/habits")
    def habits():
        rows = database.get_db().execute(
            """SELECT h.id, h.title, h.description, h.window_start, h.target_time,
                      c.penalty_description, c.forfeit_amount
               FROM habits h LEFT JOIN contracts c ON c.habit_id = h.id AND c.active = 1
               WHERE h.active = 1 ORDER BY h.sort_order""").fetchall()
        return render_template("habits.html", rows=rows)

    @app.post("/habits")
    def habits_add():
        f = request.form
        try:
            logic.add_habit(
                database.get_db(), f.get("title"), f.get("target_time"), now(),
                description=(f.get("description") or "").strip() or None,
                window_start=f.get("window_start") or None,
                penalty=f.get("penalty"), forfeit=parse_forfeit(f.get("forfeit")))
            flash("Habit added.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("habits"))

    @app.post("/habits/<int:habit_id>/contract")
    def habits_contract(habit_id):
        db = database.get_db()
        try:
            with db:
                logic.set_contract(db, habit_id, request.form.get("penalty"),
                                   parse_forfeit(request.form.get("forfeit")))
            flash("Contract updated.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("habits"))

    @app.post("/habits/<int:habit_id>/archive")
    def habits_archive(habit_id):
        logic.archive_habit(database.get_db(), habit_id)
        flash("Habit archived. Past results are kept in History.", "ok")
        return redirect(url_for("habits"))

    # ---------- History ----------

    @app.get("/history")
    def history():
        days = min(max(request.args.get("days", 14, type=int), 1), 90)
        return render_template("history.html", days=days,
                               **logic.history(database.get_db(), days, now()))

    # ---------- The contract document ----------

    @app.get("/contract")
    def contract():
        name, partner = request.args.get("name", ""), request.args.get("partner", "")
        return render_template("contract.html", rows=logic.contract_rows(database.get_db()),
                               name=name, partner=partner, start_date=logic.local_date(now()))

    @app.get("/contract.md")
    def contract_md():
        template = (BASE / "contracts" / "habit-contract.md").read_text()
        text = logic.render_contract_markdown(
            template, logic.contract_rows(database.get_db()),
            request.args.get("name", ""), request.args.get("partner", ""), now())
        return Response(text, mimetype="text/markdown", headers={
            "Content-Disposition": "attachment; filename=habit-contract.md"})

    return app


if __name__ == "__main__":
    # 127.0.0.1 = reachable only from your own computer
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)),
                     debug=os.environ.get("FLASK_DEBUG") == "1")
