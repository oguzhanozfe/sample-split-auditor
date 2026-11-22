import csv, io, json, unittest
from pathlib import Path
from pipeline import prepare, export


class SplitTests(unittest.TestCase):
    def setUp(self):
        self.d = json.loads(Path(__file__).with_name("example.json").read_text())
        self.e = prepare(self.d)

    def rows(self, picks):
        return list(
            csv.DictReader(
                io.StringIO(export(self.d, self.e, picks)["split-manifest.csv"])
            )
        )

    def test_unapproved_groups_quarantined_together(self):
        rows = self.rows([])
        self.assertEqual(
            {r["split"] for r in rows if r["group"] == "actor-a"}, {"quarantine"}
        )
        self.assertEqual(len(rows), len(self.d["samples"]))

    def test_recommendations_produce_disjoint_groups(self):
        rows = self.rows(
            [c for c in self.e["candidates"] if c["choice"] == "recommended"]
        )
        self.assertNotIn("quarantine", [r["split"] for r in rows])
        self.assertTrue(
            all(
                len({r["split"] for r in rows if r["group"] == g}) == 1
                for g in {r["group"] for r in rows}
            )
        )

    def test_conflicting_approved_destinations_refused(self):
        with self.assertRaises(ValueError):
            self.rows(self.e["candidates"][:2])

    def test_order_invariance_and_fractions(self):
        self.assertEqual(
            self.e, prepare(dict(self.d, samples=list(reversed(self.d["samples"]))))
        )
        with self.assertRaises(ValueError):
            prepare(dict(self.d, targets={"train": 0.9, "test": 0.3}))
