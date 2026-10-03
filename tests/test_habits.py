import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import db as database
import logic
from app import create_app


def at(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi)


def fresh_db(seed_at=at(2026, 10, 2, 5, 0)):
    """In-memory db with the 3 starter habits, all scheduled from the seed day."""
    conn = database.connect(":memory:")
    database.seed_starter_habits(conn, seed_at)
    return conn


def habit_id(conn, title):
    return conn.execute("SELECT id FROM habits WHERE title = ?", (title,)).fetchone()["id"]


class DeadlineLogic(unittest.TestCase):
    def test_exact_deadline_minute_is_on_time(self):
        self.assertFalse(logic.is_past_deadline("2026-10-02", "18:00", at(2026, 10, 2, 18, 0)))
        self.assertTrue(logic.is_past_deadline("2026-10-02", "18:00", at(2026, 10, 2, 18, 1)))
        self.assertFalse(logic.is_past_deadline("2026-10-02", "18:00", at(2026, 10, 2, 17, 59)))

    def test_past_days_overdue_future_days_not(self):
        self.assertTrue(logic.is_past_deadline("2026-10-01", "23:59", at(2026, 10, 2, 0, 5)))
        self.assertFalse(logic.is_past_deadline("2026-10-03", "00:01", at(2026, 10, 2, 23, 59)))

    def test_time_validation(self):
        self.assertTrue(logic.is_valid_time("07:30"))
        for bad in ("7:30", "24:00", "12:60", "", None, "noon"):
            self.assertFalse(logic.is_valid_time(bad))


class ContractProtocol(unittest.TestCase):
    def test_on_time_check_in_is_done_and_triggers_nothing(self):
        db = fresh_db()
        self.assertEqual(logic.check_in(db, habit_id(db, "Work closure"), at(2026, 10, 2, 17, 30)), "done")
        fired = logic.evaluate_deadlines(db, at(2026, 10, 2, 19, 0))
        self.assertFalse(any(p["title"] == "Work closure" for p in fired))

    def test_work_closure_unchecked_at_6_01_pm_triggers_penalty(self):
        db = fresh_db()
        before = logic.evaluate_deadlines(db, at(2026, 10, 2, 17, 59))
        self.assertFalse(any(p["title"] == "Work closure" for p in before))
        fired = logic.evaluate_deadlines(db, at(2026, 10, 2, 18, 1))
        work = [p for p in fired if p["title"] == "Work closure"]
        self.assertEqual(len(work), 1)
        self.assertIn("screens", work[0]["penalty_description"])

    def test_failure_fires_exactly_once(self):
        db = fresh_db()
        first = logic.evaluate_deadlines(db, at(2026, 10, 2, 18, 5))
        second = logic.evaluate_deadlines(db, at(2026, 10, 2, 18, 6))
        self.assertEqual(len(first), 3)
        self.assertEqual(len(second), 0)
        self.assertEqual(len(logic.open_penalties(db)), 3)

    def test_late_check_in_is_failed_and_still_penalised(self):
        db = fresh_db()
        self.assertEqual(logic.check_in(db, habit_id(db, "Work closure"), at(2026, 10, 2, 18, 30)), "failed")
        fired = logic.evaluate_deadlines(db, at(2026, 10, 2, 18, 31))
        self.assertTrue(any(p["title"] == "Work closure" for p in fired))

    def test_second_check_in_is_ignored(self):
        db = fresh_db()
        wake = habit_id(db, "Wake-up")
        self.assertEqual(logic.check_in(db, wake, at(2026, 10, 2, 5, 55)), "done")
        self.assertEqual(logic.check_in(db, wake, at(2026, 10, 2, 9, 0)), "already-logged")

    def test_missed_days_are_caught_up(self):
        db = fresh_db(at(2026, 10, 1, 5, 0))
        logic.evaluate_deadlines(db, at(2026, 10, 1, 8, 0))
        later = logic.evaluate_deadlines(db, at(2026, 10, 2, 9, 0))
        self.assertTrue(any(p["title"] == "Work closure" and p["date"] == "2026-10-01" for p in later))

    def test_habit_without_contract_fails_without_penalty(self):
        db = fresh_db()
        logic.add_habit(db, "Read", "21:00", at(2026, 10, 2, 5, 0))
        fired = logic.evaluate_deadlines(db, at(2026, 10, 2, 22, 0))
        self.assertFalse(any(p["title"] == "Read" for p in fired))
        read = [i for i in logic.today_status(db, at(2026, 10, 2, 22, 0)) if i["title"] == "Read"][0]
        self.assertEqual(read["status"], "failed")

    def test_habit_added_after_its_deadline_starts_tomorrow(self):
        db = fresh_db()
        logic.add_habit(db, "Stretch", "08:00", at(2026, 10, 2, 22, 0), penalty="Cold shower")
        self.assertFalse(any(p["title"] == "Stretch" for p in logic.evaluate_deadlines(db, at(2026, 10, 2, 22, 5))))
        tomorrow = [i["title"] for i in logic.today_status(db, at(2026, 10, 3, 6, 0))]
        self.assertIn("Stretch", tomorrow)

    def test_archiving_removes_pending_and_prevents_penalty(self):
        db = fresh_db()
        logic.archive_habit(db, habit_id(db, "Work closure"))
        fired = logic.evaluate_deadlines(db, at(2026, 10, 2, 19, 0))
        self.assertFalse(any(p["title"] == "Work closure" for p in fired))

    def test_blank_penalty_switches_contract_off(self):
        db = fresh_db()
        wid = habit_id(db, "Work closure")
        with db:
            logic.set_contract(db, wid, "")
        fired = logic.evaluate_deadlines(db, at(2026, 10, 2, 19, 0))
        self.assertFalse(any(p["title"] == "Work closure" for p in fired))

    def test_fulfilling_a_penalty(self):
        db = fresh_db()
        logic.evaluate_deadlines(db, at(2026, 10, 2, 18, 5))
        first = logic.open_penalties(db)[0]["id"]
        logic.fulfill_penalty(db, first)
        self.assertNotIn(first, [p["id"] for p in logic.open_penalties(db)])
        with self.assertRaises(ValueError):
            logic.fulfill_penalty(db, first)

    def test_add_habit_validation(self):
        db = fresh_db()
        for kwargs in (dict(title="", target_time="09:00"), dict(title="X", target_time="9am"),
                       dict(title="wake-up", target_time="09:00")):
            with self.assertRaises(ValueError):
                logic.add_habit(db, now=at(2026, 10, 2, 5, 0), **kwargs)

    def test_update_habit_rejects_duplicates_but_allows_keeping_own_name(self):
        db = fresh_db()
        wid = habit_id(db, "Wake-up")
        logic.update_habit(db, wid, "Wake-up", "05:30", at(2026, 10, 2, 5, 0))   # same name is fine
        self.assertEqual(db.execute("SELECT target_time FROM habits WHERE id = ?", (wid,)).fetchone()[0], "05:30")
        with self.assertRaises(ValueError):
            logic.update_habit(db, wid, "work closure", "05:30", at(2026, 10, 2, 5, 0))

    def test_history_summary(self):
        db = fresh_db()
        logic.check_in(db, habit_id(db, "Wake-up"), at(2026, 10, 2, 5, 50))
        logic.evaluate_deadlines(db, at(2026, 10, 2, 19, 0))
        h = logic.history(db, 7, at(2026, 10, 2, 19, 0))
        by = {s["title"]: s for s in h["summary"]}
        self.assertEqual((by["Wake-up"]["done"], by["Wake-up"]["rate"]), (1, 100))
        self.assertEqual((by["Work closure"]["failed"], by["Work closure"]["rate"]), (1, 0))


class WebApp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = [at(2026, 10, 2, 5, 30)]
        self.app = create_app(os.path.join(self.tmp.name, "t.db"), clock=lambda: self.clock[0])
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_today_page_lists_starter_habits(self):
        page = self.client.get("/").get_data(as_text=True)
        for title in ("Wake-up", "Daily devotion", "Morning routine", "Work closure"):
            self.assertIn(title, page)
        # timeline is chronological: devotion (06:45) sits between wake-up and morning routine
        self.assertLess(page.index("Wake-up"), page.index("Daily devotion"))
        self.assertLess(page.index("Daily devotion"), page.index("Morning routine"))

    def test_all_pages_render(self):
        for path in ("/", "/penalties", "/habits", "/history", "/history?days=7", "/contract"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_check_off_then_page_shows_done(self):
        wake = habit_id(database.connect(self.app.config["DATABASE"]), "Wake-up")
        r = self.client.post(f"/habits/{wake}/done", follow_redirects=True)
        text = r.get_data(as_text=True)
        self.assertIn("Checked off, on time", text)
        self.assertIn("1 of 4 done", text)

    def test_missed_deadline_shows_penalty_banner_then_can_be_served(self):
        self.clock[0] = at(2026, 10, 2, 18, 5)
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn("Contract triggered", page)
        self.assertIn("No screens after 8 PM", page)
        pen = self.client.get("/penalties").get_data(as_text=True)
        self.assertIn("No phone until noon", pen)
        pid = logic.open_penalties(database.connect(self.app.config["DATABASE"]))[0]["id"]
        after = self.client.post(f"/penalties/{pid}/fulfill", follow_redirects=True).get_data(as_text=True)
        self.assertIn("marked as served", after)

    def test_add_habit_form_and_validation_error(self):
        ok = self.client.post("/habits", data=dict(title="Read", target_time="21:00",
                              penalty="Donate", forfeit="5"), follow_redirects=True).get_data(as_text=True)
        self.assertIn("Habit added", ok)
        self.assertIn("Read", ok)
        bad = self.client.post("/habits", data=dict(title="Read", target_time="21:00", forfeit="abc"),
                               follow_redirects=True).get_data(as_text=True)
        self.assertIn("forfeit must be a number", bad)

    def test_sidebar_menu_has_grouped_clickable_links(self):
        page = self.client.get("/habits").get_data(as_text=True)
        self.assertIn('class="side-label">TRACKER', page)
        self.assertIn('class="side-label">MANAGE', page)
        for i, (path, label) in enumerate((("/", "Today"), ("/penalties", "Penalties"), ("/history", "History"),
                                           ("/habits", "Habits"), ("/contract", "Contract")), start=1):
            self.assertIn(f'href="{path}" data-key="{i}"', page)
            self.assertIn(f'<span class="label">{label}</span>', page)
        self.assertEqual(page.count('aria-current="page"'), 1)
        self.assertIn("Collapse sidebar", page)

    def test_dashboard_cards_on_today(self):
        wake = habit_id(database.connect(self.app.config["DATABASE"]), "Wake-up")
        self.client.post(f"/habits/{wake}/done")
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn("Good morning", page)
        self.assertIn("Today's progress", page)
        self.assertIn("Next deadline", page)
        self.assertIn("Penalties owed", page)
        self.assertIn("Last 7 days", page)
        self.assertIn("width: 25%", page)   # 1 of 4 done

    def test_history_tabs(self):
        summary = self.client.get("/history").get_data(as_text=True)
        grid = self.client.get("/history?view=grid&days=7").get_data(as_text=True)
        self.assertIn("Success rate", summary)
        self.assertNotIn("Success rate", grid)
        self.assertIn("grid-table", grid)

    def test_devotion_habit_added_once_with_no_contract_and_stays_archived(self):
        path = self.app.config["DATABASE"]
        conn = database.connect(path)
        row = conn.execute("SELECT id, target_time FROM habits WHERE title = 'Daily devotion'").fetchone()
        self.assertEqual(row["target_time"], "06:45")
        self.assertIsNone(conn.execute("SELECT 1 FROM contracts WHERE habit_id = ? AND active = 1",
                                       (row["id"],)).fetchone())
        logic.archive_habit(conn, row["id"])
        conn.close()
        create_app(path, clock=lambda: self.clock[0])  # restart the app
        conn = database.connect(path)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM habits WHERE title = 'Daily devotion'").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT active FROM habits WHERE id = ?", (row["id"],)).fetchone()[0], 0)

    def test_edit_habit_time_through_the_form(self):
        conn = database.connect(self.app.config["DATABASE"])
        hid = habit_id(conn, "Daily devotion")
        ok = self.client.post(f"/habits/{hid}/edit", data=dict(
            title="Daily devotion", window_start="05:00", target_time="05:45"),
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("Habit updated", ok)
        self.assertEqual(conn.execute("SELECT target_time FROM habits WHERE id = ?", (hid,)).fetchone()[0], "05:45")
        bad = self.client.post(f"/habits/{hid}/edit", data=dict(
            title="Daily devotion", window_start="06:00", target_time="05:45"),
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("window must start before the deadline", bad)

    def test_html_in_titles_is_escaped(self):
        self.client.post("/habits", data=dict(title="<script>alert(1)</script>", target_time="21:00"))
        page = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", page)

    def test_contract_markdown_download(self):
        r = self.client.get("/contract.md?name=Melody")
        self.assertEqual(r.status_code, 200)
        text = r.get_data(as_text=True)
        self.assertIn("Melody", text)
        self.assertIn("| Work closure |", text)
        self.assertNotIn("{{", text)
        self.assertIn("attachment", r.headers["Content-Disposition"])


if __name__ == "__main__":
    unittest.main()
