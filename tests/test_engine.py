import unittest

import numpy as np

import calibration
import engine


class EngineContractTests(unittest.TestCase):
    def test_complete_spectrum_must_really_be_complete(self):
        with self.assertRaisesRegex(ValueError, "exactly n=6"):
            engine.from_spectrum([10, 5, 1, 1], n=6, k=2)

        out = engine.from_spectrum([10, 5, 1, 1, 1, 1], n=6, k=2)
        self.assertEqual(out["bulk_count"], 4)
        self.assertEqual(out["spectrum_source"], "complete spectrum")

    def test_explicit_bulk_summary_checks_count(self):
        with self.assertRaisesRegex(ValueError, "bulk count must be n-k=4"):
            engine.from_spectrum([10, 5], n=6, k=2, bulk_mean=1, bulk_count=2)

        out = engine.from_spectrum([10, 5], n=6, k=2, bulk_mean=1, bulk_count=4)
        self.assertEqual(out["theta"], [10.0, 5.0])
        self.assertEqual(out["ell"], 1.0)

    def test_strengths_must_be_rank_ordered(self):
        with self.assertRaisesRegex(ValueError, "strongest to weakest"):
            engine.simulate(40, 10, 2, [0.01, 0.02], 0.16, "normal", reps=5)
        # Equal strengths are a valid exact-tie stress, not an input error.
        engine.validate_calibration(40, 10, 2, [0.02, 0.02], 0.16, reps=5)

    def test_factor_assignment_is_one_to_one(self):
        overlaps = np.array([[0.90, 0.89], [0.80, 0.10]])
        assignment = engine._best_permutation(overlaps)
        self.assertEqual(sorted(assignment.tolist()), [0, 1])
        self.assertEqual(assignment.tolist(), [1, 0])

    def test_q90_reports_monte_carlo_interval(self):
        out = engine.simulate(
            100, 12, 2, [0.04, 0.01], 0.16, "normal", reps=80, seed=123)
        ci = out["q90_mc95"]
        self.assertEqual(ci["confidence"], 0.95)
        for lower, point, upper in zip(
                ci["lower"], out["quantiles"]["0.9"], ci["upper"]):
            self.assertLessEqual(lower, point)
            self.assertLessEqual(point, upper)

    def test_numpy_only_eigensolver_matches_optional_scipy(self):
        matrix = np.array([[4.0, 1.0, 0.2], [1.0, 3.0, 0.1], [0.2, 0.1, 1.0]])
        vals_ref, vecs_ref = engine._top_k(matrix, 2, 3)
        scipy_eigh = engine._sp_eigh
        try:
            engine._sp_eigh = None
            vals_np, vecs_np = engine._top_k(matrix, 2, 3)
        finally:
            engine._sp_eigh = scipy_eigh
        self.assertTrue(np.allclose(vals_ref, vals_np))
        self.assertTrue(np.allclose(np.abs((vecs_ref * vecs_np).sum(axis=0)), 1.0))

    def test_sweep_identity_includes_paths_and_engine(self):
        a, d2 = calibration.engine_args([16.0], [1.25], 40.0)
        build_identity = calibration.key(3000, 1, a, d2, "t")[-1]
        self.assertEqual(build_identity[0], calibration.CACHED_REPS)
        self.assertEqual(build_identity[1], calibration.engine_fingerprint())


if __name__ == "__main__":
    unittest.main()
