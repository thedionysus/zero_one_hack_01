import unittest

from app import state as st
from lib import decision as dc

SLUGS = {"urea", "dap", "mop", "tsp", "phosphate-rock"}


class TestCalibrateAll(unittest.TestCase):
    def test_calibrates_all_five(self):
        cal = st.calibrate_all()
        self.assertEqual(set(cal["by_fert"].keys()), SLUGS)
        self.assertIn(cal["hero"], SLUGS)
        self.assertEqual(cal["last_real_date"], "2026-03-01")
        urea = cal["by_fert"]["urea"]
        for k in ("native", "corrected", "cov80_native", "cov80_corrected", "trust"):
            self.assertIn(k, urea)
        any_month = next(iter(urea["corrected"].values()))
        for q in ("p10", "p50", "p90"):
            self.assertIn(q, any_month)


class TestAppState(unittest.TestCase):
    def setUp(self):
        self.cal = st.calibrate_all()

    def test_default_selects_hero_and_austrian_persona(self):
        s = st.AppState.default(self.cal)
        self.assertEqual(s.fertilizer, self.cal["hero"])
        self.assertEqual(s.monthly_demand_t, 1000.0)
        self.assertEqual(s.current_stock_t, 3000.0)
        self.assertEqual(s.carrying_cost_pct_yr, 0.18)
        self.assertEqual(s.risk_quantile, "p50")
        self.assertEqual(s.shock_level_pct, 0.0)
        self.assertEqual(s.shock_trend_g, 0.0)

    def test_to_persona(self):
        s = st.AppState.default(self.cal)
        p = s.to_persona()
        self.assertIsInstance(p, dc.Persona)
        self.assertEqual(p.runway_months, 3.0)

    def test_solve_state_no_shock_matches_plain_solve(self):
        s = st.AppState.default(self.cal)
        res = st.solve_state(s, self.cal)
        corrected = self.cal["by_fert"][s.fertilizer]["corrected"]
        expected = dc.solve(corrected, s.to_persona())
        self.assertEqual(res["current_plan"].recommendation, expected.recommendation)
        self.assertFalse(res["diff"]["changed"])
        self.assertAlmostEqual(res["diff"]["savings_delta"], 0.0)

    def test_trend_shock_can_flip_and_is_diffed(self):
        flipped = None
        g = 0.02
        while g <= 0.60 + 1e-9:
            s = st.AppState.default(self.cal)
            s = s.replaced(shock_trend_g=g)
            res = st.solve_state(s, self.cal)
            if res["diff"]["changed"]:
                flipped = res
                break
            g += 0.02
        self.assertIsNotNone(flipped, "some trend should flip the hero decision")
        self.assertNotEqual(flipped["diff"]["recommendation"][0],
                            flipped["diff"]["recommendation"][1])

    def test_savings_eur_uses_fx(self):
        from lib import pipeline
        s = st.AppState.default(self.cal)
        res = st.solve_state(s, self.cal)
        self.assertAlmostEqual(
            res["savings_eur"],
            res["current_plan"].savings * pipeline.EUR_PER_USD, places=9)


if __name__ == "__main__":
    unittest.main()
