import unittest

import reporting


class ReportingTests(unittest.TestCase):
    def test_wilson_interval_brackets_the_rate_and_stays_in_bounds(self):
        lo, hi = reporting.wilson95(0.05, 400)
        self.assertLess(lo, 0.05)
        self.assertGreater(hi, 0.05)
        # a rate near 5% at 400 paths is ~±2pt wide — the whole reason it is shown
        self.assertGreater(hi - lo, 0.03)
        # boundary rates must not escape [0, 1]
        lo0, _ = reporting.wilson95(0.0, 400)
        _, hi1 = reporting.wilson95(1.0, 400)
        self.assertEqual(lo0, 0.0)
        self.assertLessEqual(hi1, 1.0)
        self.assertGreater(hi1, 0.98)
        # more paths -> tighter interval
        lo_big, hi_big = reporting.wilson95(0.05, 4000)
        self.assertLess(hi_big - lo_big, hi - lo)

    def test_tie_cutoff_is_a_parameter_not_a_constant(self):
        confusion = [[0.97, 0.03], [0.03, 0.97]]
        self.assertEqual(reporting.tied_runs(confusion, 2, tolerance=0.05)[0], [])
        self.assertEqual(reporting.tied_runs(confusion, 2, tolerance=0.02)[0], [(0, 1)])

    def test_tied_blocks_are_withheld_from_named_sweep(self):
        confusion = [
            [0.99, 0.00, 0.00],
            [0.01, 0.93, 0.07],
            [0.00, 0.07, 0.93],
        ]
        groups, _ = reporting.tied_runs(confusion, 3, tolerance=0.05)
        self.assertEqual(groups, [(1, 2)])
        self.assertEqual(reporting.stable_factor_indices(3, groups), [0])

    def test_export_preserves_reliability_and_subspace_claim_boundary(self):
        payload = reporting.build_export_payload(
            engine_fingerprint="abc123",
            inputs={"n": 63, "p": 3000, "k": 2, "source": "model"},
            factors=[
                {"factor": "f1", "named_reliable": False, "tie_group": "f1+f2"},
                {"factor": "f2", "named_reliable": False, "tie_group": "f1+f2"},
            ],
            subspaces=[{
                "name": "f1+f2", "q90°": 20.0, "floor°": None,
                "required_history": None,
                "claim_status": "conditional simulation",
            }],
            tie_groups=["f1+f2"],
            assumptions=["conditional simulation"],
        )
        rows = reporting.export_rows(payload)
        self.assertEqual(len(rows), 3)
        self.assertFalse(rows[0]["named_reliable"])
        self.assertEqual(rows[-1]["object_type"], "subspace")
        self.assertIsNone(rows[-1]["floor°"])
        self.assertIsNone(rows[-1]["required_history"])
        self.assertEqual(payload["provenance"]["engine_fingerprint"], "abc123")


if __name__ == "__main__":
    unittest.main()
