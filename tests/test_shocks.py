import unittest

from lib import shocks
from lib import pipeline
from lib import decision as dc


class TestLevelShift(unittest.TestCase):
    def test_scales_every_quantile(self):
        block = {"2026-04-01": {"p05": 1.0, "p50": 2.0, "p95": 4.0}}
        out = shocks.level_shift(block, 0.30)
        self.assertAlmostEqual(out["2026-04-01"]["p50"], 2.6)
        self.assertAlmostEqual(out["2026-04-01"]["p95"], 5.2)

    def test_does_not_mutate_input(self):
        block = {"2026-04-01": {"p50": 2.0}}
        shocks.level_shift(block, 0.5)
        self.assertEqual(block["2026-04-01"]["p50"], 2.0)

    def test_rejects_full_drop(self):
        with self.assertRaises(ValueError):
            shocks.level_shift({"d": {"p50": 1.0}}, -1.0)


class TestPlanDiff(unittest.TestCase):
    def test_detects_recommendation_change(self):
        before = dc.OrderPlan([], [], {}, {}, 100.0, 100.0, 0.0, 0.0, "WAIT", "x", "r")
        after = dc.OrderPlan([], [], {}, {}, 80.0, 100.0, 20.0, 0.2, "BUY_NOW", "y", "r")
        diff = shocks.plan_diff(before, after)
        self.assertTrue(diff["changed"])
        self.assertEqual(diff["recommendation"], ("WAIT", "BUY_NOW"))
        self.assertAlmostEqual(diff["savings_delta"], 20.0)


class TestShockIntegration(unittest.TestCase):
    def test_shock_resolves_on_hero(self):
        run = pipeline.run_all()
        hero = run["results"][run["hero"]]
        corrected = hero["calibration"]["corrected"]
        persona = pipeline.AUSTRIAN_UREA_PERSONA
        before = dc.solve(corrected, persona)
        after = dc.solve(shocks.level_shift(corrected, 0.30), persona)
        diff = shocks.plan_diff(before, after)
        self.assertGreaterEqual(after.savings, 0.0)
        self.assertIn("changed", diff)


if __name__ == "__main__":
    unittest.main()
