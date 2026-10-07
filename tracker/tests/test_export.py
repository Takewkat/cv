"""CSV export: one row per card, stage names, outcome and stage reached, CV names, formula guard."""
import csv
import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import export  # noqa: E402
import store  # noqa: E402


class ExportTest(unittest.TestCase):
    def doc(self):
        return dict(store.default_document(), cards=[
            {"id": "a", "column": "closed", "company": "Example Corp", "role": "SRE", "profile": "alex",
             "variant": "main", "closedReason": "ghosted", "inbound": True,
             "comments": [{"at": "2026-09-02T10:00:00Z", "text": "first"}, {"at": "2026-09-09T10:00:00Z", "text": "last"}],
             "history": [{"column": "applied", "date": "2026-09-01"}, {"column": "technical", "date": "2026-09-08"},
                         {"column": "closed", "date": "2026-09-20"}]},
            {"id": "b", "column": "applied", "company": "=HYPERLINK(\"x\")", "cvKind": "other", "cvNote": "hand-tuned",
             "history": [{"column": "applied", "date": "2026-10-01"}]},
        ])

    def test_rows(self):
        labels = {("alex", "main"): "Backend"}
        rows = list(export.rows(self.doc(), labels, today=datetime.date(2026, 10, 7)))
        self.assertEqual(rows[0][:10], ["Example Corp", "SRE", "Closed", "Ghosted", "Technical", "2026-09-01",
                                        "2026-09-20", 17, "yes", "Backend"])
        self.assertEqual(rows[0][12:14], [2, "2026-09-09 last"])
        self.assertEqual(rows[0][14], "2026-09-01 Applied; 2026-09-08 Technical; 2026-09-20 Closed")
        self.assertEqual(rows[1][9], "Other: hand-tuned")

    def test_file_has_a_bom_a_header_and_no_live_formula(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.csv")
            self.assertEqual(export.write_csv(self.doc(), {}, path), 2)
            with open(path, "rb") as f:
                self.assertTrue(f.read().startswith(b"\xef\xbb\xbf"))
            with open(path, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))
        self.assertEqual(rows[0], export.HEADER)
        self.assertEqual(rows[1][9], "alex / main")
        self.assertTrue(rows[2][0].startswith("'="))


if __name__ == "__main__":
    unittest.main()
