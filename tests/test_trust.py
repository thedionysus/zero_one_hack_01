import unittest
from lib import trust


class TestComponentScores(unittest.TestCase):
    def test_calibration_perfect_is_one(self):
        self.assertAlmostEqual(trust.calibration_score(0.80, 0.90), 1.0)

    def test_calibration_bad_clamps_zero(self):
        self.assertEqual(trust.calibration_score(0.22, 0.28), 0.0)

    def test_skill_beats_naive_is_one(self):
        self.assertEqual(trust.skill_score(1.0), 1.0)
        self.assertEqual(trust.skill_score(0.5), 1.0)

    def test_skill_worse_than_naive_decays(self):
        self.assertAlmostEqual(trust.skill_score(5.0), 0.2)

    def test_skill_nonpositive_raises(self):
        with self.assertRaises(ValueError):
            trust.skill_score(0.0)

    def test_accuracy_linear(self):
        self.assertAlmostEqual(trust.accuracy_score(0.0), 1.0)
        self.assertAlmostEqual(trust.accuracy_score(25.0), 0.5)
        self.assertEqual(trust.accuracy_score(80.0), 0.0)


class TestTrustBundle(unittest.TestCase):
    def _good(self):
        return {"cov80": 0.80, "cov90": 0.90, "mase": 0.8, "mape": 8.0}

    def _bad(self):
        return {"cov80": 0.22, "cov90": 0.28, "mase": 5.1, "mape": 24.0}

    def test_good_beats_bad(self):
        g = trust.trust_from_metrics(self._good())
        b = trust.trust_from_metrics(self._bad())
        self.assertGreater(g["score"], b["score"])
        self.assertEqual(g["label"], "high")
        self.assertEqual(b["label"], "low")

    def test_bounds(self):
        for m in (self._good(), self._bad()):
            s = trust.trust_from_metrics(m)["score"]
            self.assertGreaterEqual(s, 0.0)
            self.assertLessEqual(s, 1.0)


class TestRelativeWeights(unittest.TestCase):
    def test_sums_to_one(self):
        w = trust.relative_weights({"urea": 0.8, "dap": 0.6, "mop": 0.2})
        self.assertAlmostEqual(sum(w.values()), 1.0)
        self.assertGreater(w["urea"], w["mop"])

    def test_all_zero_is_uniform(self):
        w = trust.relative_weights({"a": 0.0, "b": 0.0})
        self.assertAlmostEqual(w["a"], 0.5)
        self.assertAlmostEqual(w["b"], 0.5)

    def test_empty(self):
        self.assertEqual(trust.relative_weights({}), {})


if __name__ == "__main__":
    unittest.main()
