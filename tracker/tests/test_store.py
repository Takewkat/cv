"""Storage: atomic write, backups and their rotation, the revision check, validation, migration, the data path."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import store  # noqa: E402


def card(**fields):
    base = {"id": "c1", "column": "applied", "company": "Example Corp", "role": "QA Engineer",
            "history": [{"column": "applied", "date": "2026-09-01"}]}
    return {**base, **fields}


def document(*cards):
    return dict(store.default_document(), cards=list(cards))


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "nested", "applications.json")
        self.store = store.Store(self.path, keep=3)

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def backups(self):
        return sorted(os.listdir(self.store.backup_dir)) if os.path.isdir(self.store.backup_dir) else []

    def test_missing_file_gives_the_default_board(self):
        doc = self.store.load()
        self.assertEqual([c["id"] for c in doc["columns"]],
                         ["applied", "hr", "manager", "technical", "case", "final", "offer", "closed"])
        self.assertEqual([c["kind"] for c in doc["columns"] if c["kind"]], ["start", "closed"])
        self.assertEqual(doc["cards"], [])
        self.assertIsNone(doc["updatedAt"])

    def test_save_writes_and_returns_a_new_revision(self):
        saved = self.store.save(document(card()))
        self.assertIsNotNone(saved["updatedAt"])
        self.assertEqual(self.read(), saved)
        again = self.store.save(dict(saved, cards=[]))
        self.assertNotEqual(again["updatedAt"], saved["updatedAt"])

    def test_failed_write_keeps_the_previous_file_and_no_temp_file(self):
        first = self.store.save(document(card()))
        with mock.patch.object(store.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.store.save(dict(first, cards=[]))
        self.assertEqual(self.read(), first)
        leftovers = [n for n in os.listdir(os.path.dirname(self.path)) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_each_write_backs_up_the_previous_file_and_keeps_the_newest(self):
        doc = self.store.save(document())
        self.assertEqual(self.backups(), [])
        for i in range(5):
            previous = self.read()
            doc = self.store.save(dict(doc, cards=[card(company=f"Company {i}")]))
            with open(os.path.join(self.store.backup_dir, self.backups()[-1]), encoding="utf-8") as f:
                self.assertEqual(json.load(f), previous)
        self.assertEqual(len(self.backups()), 3)

    def test_stale_revision_is_a_conflict(self):
        loaded = self.store.load()
        self.store.save(document(card()))
        with self.assertRaises(store.Conflict):
            self.store.save(dict(loaded, cards=[]))
        self.assertEqual(len(self.read()["cards"]), 1)

    def test_invalid_documents_are_rejected(self):
        cases = {
            "not an object": [],
            "unknown schema": dict(document(), schemaVersion=99),
            "unknown top field": dict(document(), extra=1),
            "columns not a list": dict(document(), columns="applied"),
            "card column not text": document(card(column=7)),
            "card without company": document(card(company=" ")),
            "unknown card field": document(card(salaryEUR=1)),
            "bad date": document(card(nextDate="10/10/2026")),
            "inbound not a flag": document(card(inbound="yes")),
            "bad outcome": document(card(column="closed", closedReason="vanished")),
            "empty history": document(card(history=[])),
            "history entry without date": document(card(history=[{"column": "applied"}])),
            "bad cv kind": document(card(cvKind="mine")),
            "comments not a list": document(card(comments="hi")),
            "comment without date": document(card(comments=[{"text": "hi"}])),
            "comment with a bad date": document(card(comments=[{"at": "yesterday", "text": "hi"}])),
            "empty comment": document(card(comments=[{"at": "2026-10-07T10:00:00.000Z", "text": " "}])),
            "comment too long": document(card(comments=[{"at": "2026-10-07T10:00:00Z", "text": "x" * 5001}])),
            "duplicate card id": document(card(), card()),
            "text too long": document(card(role="x" * 201)),
            "card id with a slash": document(card(id="../x")),
        }
        for name, doc in cases.items():
            with self.subTest(name):
                with self.assertRaises(store.Invalid):
                    self.store.save(doc)
        self.assertFalse(os.path.exists(self.path))

    def test_full_card_is_valid(self):
        store.validate(document(card(url="https://example.com/job", inbound=True, profile="alex", variant="main",
                                     nextDate="2026-10-10", posting="p", touchedOn="2026-09-02",
                                     cvKind="other", cvNote="hand-tuned", column="closed", closedReason="ghosted",
                                     comments=[{"at": "2026-09-05T09:30:00.000Z", "text": "Recruiter called"},
                                               {"at": "2026-09-06T18:00:00+02:00", "text": "Sent the case study"}],
                                     history=[{"column": "applied", "date": "2026-09-01"},
                                              {"column": "technical", "date": "2026-09-10"},
                                              {"column": "closed", "date": "2026-09-20"}])))

    def test_minimal_card_is_valid(self):
        store.validate(document({"id": "c1", "column": "applied", "company": "Example Corp",
                                 "history": [{"column": "applied", "date": "2026-10-07"}]}))

    def test_fields_of_earlier_versions_become_a_first_comment(self):
        old = card(notes="Liked the team", location="Paris", salary="55k", contact="Sam", nextStep="Call back",
                   nextTime="14:00", source="wttj", initiator="inbound", appliedOn="2026-09-01",
                   comments=[{"at": "2026-09-03T10:00:00Z", "text": "Later comment"}],
                   history=[{"column": "applied", "date": "2026-09-01", "step": "Sent"}])
        saved = self.store.save(dict(document(old), schemaVersion=2))
        c = saved["cards"][0]
        self.assertTrue(c["inbound"])
        self.assertEqual(c["history"], [{"column": "applied", "date": "2026-09-01"}])
        self.assertEqual(c["comments"][0], {"at": "2026-09-01T12:00:00Z", "text": "Notes: Liked the team\n"
                         "Next step: Call back\nInterview time: 14:00\nLocation: Paris\nSalary: 55k\nContact: Sam\n"
                         "Source: wttj"})
        self.assertEqual(c["comments"][1]["text"], "Later comment")
        for gone in ("notes", "location", "salary", "contact", "nextStep", "nextTime", "source", "initiator", "appliedOn"):
            self.assertNotIn(gone, c)

    def test_column_names_always_come_from_the_default_list(self):
        doc = document(card(column="technical"))
        doc["columns"][0]["name"] = "Applied / Contacted"
        doc["columns"].insert(-1, {"id": "lunch", "name": "Team lunch", "kind": ""})
        saved = self.store.save(doc)
        self.assertEqual(saved["columns"], store.DEFAULT_COLUMNS)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(dict(saved, columns=[dict(c, name="Old " + c["name"]) for c in saved["columns"]]), f)
        self.assertEqual(self.store.load()["columns"], store.DEFAULT_COLUMNS)
        self.assertEqual(self.store.load()["cards"][0]["column"], "technical")

    def test_old_document_is_upgraded_without_losing_cards(self):
        v1 = {"schemaVersion": 1, "updatedAt": None, "columns": [
            {"id": "applied", "name": "Applied"}, {"id": "screen", "name": "Recruiter screen"},
            {"id": "interviews", "name": "Technical interviews"}, {"id": "final", "name": "Final / Offer"},
            {"id": "lunch", "name": "Team lunch"}, {"id": "closed", "name": "Closed"}],
            "cards": [card(id="a", column="screen", history=[{"column": "applied", "date": "2026-09-01"},
                                                             {"column": "screen", "date": "2026-09-05"}]),
                      card(id="b", column="interviews", history=[{"column": "interviews", "date": "2026-09-02"}]),
                      card(id="c", column="lunch", history=[{"column": "lunch", "date": "2026-09-03"}]),
                      card(id="d", column="closed", closedReason="ghosted",
                           history=[{"column": "final", "date": "2026-09-04"}, {"column": "closed", "date": "2026-09-09"}])]}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(v1, f)
        doc = self.store.load()
        self.assertEqual(doc["schemaVersion"], store.SCHEMA_VERSION)
        self.assertEqual([c["column"] for c in doc["cards"]], ["hr", "technical", "lunch", "closed"])
        self.assertEqual([h["column"] for h in doc["cards"][0]["history"]], ["applied", "hr"])
        self.assertEqual(doc["columns"][:-2], store.DEFAULT_COLUMNS[:-1])
        self.assertEqual(doc["columns"][-2], {"id": "lunch", "name": "Team lunch", "kind": ""})
        self.assertEqual(doc["columns"][-1], store.DEFAULT_COLUMNS[-1])
        saved = self.store.save(doc)
        self.assertEqual(self.read(), saved)
        self.assertEqual(len(self.backups()), 1)

    def test_long_or_non_text_legacy_fields_are_kept_whole(self):
        old = card(notes="n" * 4990, location="Paris", salary=55000)
        c = self.store.save(dict(document(old), schemaVersion=2))["cards"][0]
        self.assertEqual([x["text"] for x in c["comments"]],
                         ["Notes: " + "n" * 4990, "Location: Paris\nSalary: 55000"])

    def test_board_with_many_old_columns_still_loads(self):
        cols = [{"id": f"old{i}", "name": f"Old {i}"} for i in range(10)]
        old = {"schemaVersion": 1, "updatedAt": None, "columns": cols + [{"id": "closed", "name": "Closed"}],
               "cards": [card(id=f"c{i}", column=f"old{i}", history=[{"column": f"old{i}", "date": "2026-09-01"}])
                         for i in range(10)]}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(old, f)
        doc = self.store.load()
        self.assertEqual(len(doc["columns"]), len(store.DEFAULT_COLUMNS) + 10)
        self.assertEqual(len(doc["cards"]), 10)

    def test_old_import_is_upgraded_on_save(self):
        v1 = {"schemaVersion": 1, "updatedAt": None, "columns": [{"id": "applied", "name": "Applied"},
              {"id": "closed", "name": "Closed"}], "cards": [card(column="applied")]}
        self.assertEqual(self.store.save(v1)["schemaVersion"], store.SCHEMA_VERSION)

    def test_corrupt_file_is_reported_not_overwritten(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{not json")
        with self.assertRaises(store.StoreError):
            self.store.load()
        with self.assertRaises(store.StoreError):
            self.store.save(document())
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{not json")


class DataPathTest(unittest.TestCase):
    def test_default_is_tracker_data(self):
        self.assertEqual(store.data_path(), os.path.join(store.HERE, "data", "applications.json"))

    def test_argument_wins_over_environment(self):
        self.assertEqual(store.data_path("/tmp/a.json", "/tmp/b.json"), "/tmp/a.json")
        self.assertEqual(store.data_path(None, "/tmp/b.json"), "/tmp/b.json")

    def test_home_is_expanded(self):
        self.assertEqual(store.data_path("~/t.json"), os.path.join(os.path.expanduser("~"), "t.json"))

    def test_folder_gets_the_default_file_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(store.data_path(tmp), os.path.join(tmp, "applications.json"))
            self.assertEqual(store.data_path(tmp + "/new/"), os.path.join(tmp, "new", "applications.json"))

    def test_store_creates_parent_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a", "b", "applications.json")
            store.Store(path)
            self.assertTrue(os.path.isdir(os.path.dirname(path)))


if __name__ == "__main__":
    unittest.main()
