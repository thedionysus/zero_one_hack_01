import unittest
from lib import pipeline
from lib import decision as dc

SLUGS = {"urea", "dap", "mop", "tsp", "phosphate-rock"}


class TestPipeline(unittest.TestCase):
    def test_persona_runway(self):
        p = pipeline.AUSTRIAN_UREA_PERSONA
        self.assertEqual(p.monthly_demand_t, 1000.0)
        self.assertEqual(p.runway_months, 3.0)

    def test_last_real_date_from_manifest(self):
        self.assertEqual(pipeline.load_manifest()["last_real_date"], "2026-03-01")

    def test_run_all_covers_five_fertilizers(self):
        run = pipeline.run_all()
        self.assertEqual(set(run["results"].keys()), SLUGS)
        self.assertIn(run["hero"], SLUGS)

    def test_each_result_shape_and_savings_nonnegative(self):
        run = pipeline.run_all()
        for slug, r in run["results"].items():
            self.assertIsInstance(r["plan"], dc.OrderPlan)
            self.assertGreaterEqual(r["plan"].savings, 0.0)
            self.assertGreaterEqual(r["savings_eur"], 0.0)
            self.assertIn(r["plan"].recommendation,
                          {"BUY_NOW", "WAIT", "SPLIT", "COVERED"})
            self.assertIn(r["trust"]["label"], {"high", "medium", "low"})

    def test_recalibration_lifts_coverage(self):
        run = pipeline.run_all()
        cal = run["results"]["urea"]["calibration"]
        self.assertGreater(cal["cov80_corrected"], cal["cov80_native"])

    def test_savings_eur_matches_fx(self):
        run = pipeline.run_all()
        for r in run["results"].values():
            self.assertAlmostEqual(
                r["savings_eur"], r["plan"].savings * pipeline.EUR_PER_USD, places=9)

    def test_hero_is_argmax_trust(self):
        run = pipeline.run_all()
        hero_score = run["results"][run["hero"]]["trust"]["score"]
        for r in run["results"].values():
            self.assertLessEqual(r["trust"]["score"], hero_score + 1e-12)


if __name__ == "__main__":
    unittest.main()
