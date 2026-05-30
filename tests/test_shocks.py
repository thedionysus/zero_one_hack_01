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


class TestTrendShift(unittest.TestCase):
    def test_identity_at_zero(self):
        block = {"2026-04-01": {"p50": 2.0}, "2026-05-01": {"p50": 3.0}}
        self.assertEqual(shocks.trend_shift(block, 0.0), block)

    def test_compounds_by_month_position(self):
        block = {"2026-04-01": {"p50": 1.0},
                 "2026-05-01": {"p50": 1.0},
                 "2026-06-01": {"p50": 1.0}}
        out = shocks.trend_shift(block, 0.10)
        self.assertAlmostEqual(out["2026-04-01"]["p50"], 1.00)   # i=0
        self.assertAlmostEqual(out["2026-05-01"]["p50"], 1.10)   # i=1
        self.assertAlmostEqual(out["2026-06-01"]["p50"], 1.21)   # i=2

    def test_orders_by_calendar_not_dict_insertion(self):
        # Later date inserted first must still get the larger exponent.
        block = {"2026-06-01": {"p50": 1.0}, "2026-04-01": {"p50": 1.0}}
        out = shocks.trend_shift(block, 0.10)
        self.assertAlmostEqual(out["2026-04-01"]["p50"], 1.00)
        self.assertAlmostEqual(out["2026-06-01"]["p50"], 1.21)

    def test_does_not_mutate_input(self):
        block = {"2026-04-01": {"p50": 2.0}, "2026-05-01": {"p50": 2.0}}
        shocks.trend_shift(block, 0.2)
        self.assertEqual(block["2026-05-01"]["p50"], 2.0)

    def test_rejects_full_drop(self):
        with self.assertRaises(ValueError):
            shocks.trend_shift({"2026-04-01": {"p50": 1.0}}, -1.0)


class TestTrendFlipsDecision(unittest.TestCase):
    def test_some_ramp_flips_hero_to_buy_now(self):
        # Forecast-agnostic: SOME positive monthly trend must flip the trust-hero
        # toward BUY_NOW. No hardcoded magnitude or hero -- search a range and
        # assert existence, so this stays valid as the forecasts change.
        run = pipeline.run_all()
        corrected = run["results"][run["hero"]]["calibration"]["corrected"]
        persona = pipeline.AUSTRIAN_UREA_PERSONA
        recs = set()
        g = 0.02
        while g <= 0.60 + 1e-9:
            recs.add(dc.solve(shocks.trend_shift(corrected, g), persona).recommendation)
            g += 0.02
        self.assertIn("BUY_NOW", recs)


if __name__ == "__main__":
    unittest.main()
