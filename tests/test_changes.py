import unittest

from app import changes
from app import state as st


class TestApplyChange(unittest.TestCase):
    def setUp(self):
        self.cal = st.calibrate_all()
        self.s = st.AppState.default(self.cal)

    def test_apply_trend(self):
        out = changes.apply_change(self.s, changes.Change("trend", 0.12))
        self.assertEqual(out.shock_trend_g, 0.12)
        self.assertEqual(self.s.shock_trend_g, 0.0)  # original unchanged

    def test_apply_level(self):
        out = changes.apply_change(self.s, changes.Change("level", 0.30))
        self.assertEqual(out.shock_level_pct, 0.30)

    def test_apply_persona_fields(self):
        out = changes.apply_change(self.s, changes.Change("stock", 1000.0))
        self.assertEqual(out.current_stock_t, 1000.0)
        out2 = changes.apply_change(self.s, changes.Change("risk", "p70"))
        self.assertEqual(out2.risk_quantile, "p70")

    def test_apply_fertilizer(self):
        out = changes.apply_change(self.s, changes.Change("fertilizer", "urea"))
        self.assertEqual(out.fertilizer, "urea")

    def test_reset_clears_shocks(self):
        shocked = self.s.replaced(shock_level_pct=0.3, shock_trend_g=0.1)
        out = changes.apply_change(shocked, changes.Change("reset", None))
        self.assertEqual(out.shock_level_pct, 0.0)
        self.assertEqual(out.shock_trend_g, 0.0)

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            changes.apply_change(self.s, changes.Change("nonsense", 1))


class TestRuleBasedParse(unittest.TestCase):
    def test_rising_keyword_plus_pct_is_trend(self):
        c = changes.rule_based_parse("gas spiked, prices +30%")
        self.assertEqual(c.kind, "trend")
        self.assertAlmostEqual(c.value, 0.30)

    def test_per_month_phrasing_is_trend(self):
        c = changes.rule_based_parse("prices rising 12% a month")
        self.assertEqual(c.kind, "trend")
        self.assertAlmostEqual(c.value, 0.12)

    def test_plain_higher_is_level(self):
        c = changes.rule_based_parse("prices are 20% higher")
        self.assertEqual(c.kind, "level")
        self.assertAlmostEqual(c.value, 0.20)

    def test_runway_phrase_sets_stock_months(self):
        c = changes.rule_based_parse("a supplier fell through, only 1 month of stock left")
        self.assertEqual(c.kind, "stock_months")
        self.assertAlmostEqual(c.value, 1.0)

    def test_reset_phrase(self):
        c = changes.rule_based_parse("reset to normal")
        self.assertEqual(c.kind, "reset")

    def test_unparseable_returns_none(self):
        self.assertIsNone(changes.rule_based_parse("tell me a joke"))


class TestNarrateTemplate(unittest.TestCase):
    def test_flip_narration_mentions_both_recs(self):
        diff = {"recommendation": ("WAIT", "BUY_NOW"), "changed": True,
                "target_month": ("2026-11-01", "2026-04-01"),
                "savings": (100000.0, 500000.0), "savings_delta": 400000.0,
                "savings_pct": (0.1, 0.3)}
        text = changes.narrate_template(diff, changes.Change("trend", 0.12), 0.92)
        self.assertIn("WAIT", text)
        self.assertIn("BUY_NOW", text)
        self.assertIn("€", text)

    def test_no_change_narration(self):
        diff = {"recommendation": ("WAIT", "WAIT"), "changed": False,
                "target_month": ("2026-11-01", "2026-11-01"),
                "savings": (100000.0, 130000.0), "savings_delta": 30000.0,
                "savings_pct": (0.1, 0.13)}
        text = changes.narrate_template(diff, changes.Change("level", 0.30), 0.92)
        self.assertIn("WAIT", text)


if __name__ == "__main__":
    unittest.main()
