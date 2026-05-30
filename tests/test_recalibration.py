import unittest
from lib import recalibration as rc


def _pts(p50, actuals):
    """Build [(actual, quantile_dict)] sharing one P50."""
    return [(a, {"0.10": p50 * 0.97, "0.50": p50, "0.90": p50 * 1.03}) for a in actuals]


class TestResiduals(unittest.TestCase):
    def test_residuals(self):
        pts = [(10.0, {"0.50": 8.0}), (20.0, {"0.50": 16.0})]
        self.assertEqual(rc.residuals_from_points(pts), [2.0, 4.0])

    def test_residuals_empty_raises(self):
        with self.assertRaises(ValueError):
            rc.residuals_from_points([])

    def test_offsets_monotone_and_full(self):
        offs = rc.residual_offsets([float(x) for x in range(20)])
        self.assertEqual(len(offs), 19)
        vals = [offs[t] for t in rc.QUANTILE_TAUS]
        self.assertEqual(vals, sorted(vals))  # non-decreasing


class TestRecalibrateBlock(unittest.TestCase):
    def test_block_shifts_p50_by_offset(self):
        block = {"2026-04-01": {"p50": 1.0}}
        offs = {t: 0.5 for t in rc.QUANTILE_TAUS}  # flat +0.5
        out = rc.recalibrate_block(block, offs)
        self.assertAlmostEqual(out["2026-04-01"]["p50"], 1.5)
        self.assertIn("p05", out["2026-04-01"])
        self.assertIn("p95", out["2026-04-01"])

    def test_does_not_mutate_input(self):
        block = {"2026-04-01": {"p50": 1.0}}
        rc.recalibrate_block(block, {t: 0.1 for t in rc.QUANTILE_TAUS})
        self.assertEqual(block, {"2026-04-01": {"p50": 1.0}})


class TestCoverageLift(unittest.TestCase):
    def test_in_sample_coverage_near_nominal(self):
        # residuals 0..19; in-sample 80% band should cover ~80%
        pts = _pts(1.0, [1.0 + r for r in range(20)])
        offs = rc.residual_offsets(rc.residuals_from_points(pts))
        cov = rc.coverage_with_offsets(pts, offs, 0.10, 0.90)
        self.assertGreaterEqual(cov, 0.70)
        self.assertLessEqual(cov, 0.95)


class TestEndToEnd(unittest.TestCase):
    def _forecast_json(self):
        return {"data": {"forecast_series": {
            "2026-04-01": {"forecast": 1.0, "quantile_forecast": {
                "0.05": 0.97, "0.10": 0.98, "0.50": 1.0, "0.90": 1.02, "0.95": 1.03}},
        }}}

    def _trajectories(self):
        # actuals sit ABOVE a tight native band -> native 80% under-covers
        fs_series = {}
        for i, a in enumerate([1.0, 1.1, 1.2, 1.3, 0.9]):
            fs_series[f"2025-0{i+1}-01"] = {
                "actual": a,
                "quantile_forecast": {"0.10": 0.97, "0.50": 1.0, "0.90": 1.03},
            }
        return {"data": [{"forecast_end": "2025-05-01", "forecast_series": fs_series}]}

    def test_recalibrate_lifts_coverage_and_corrects_bias(self):
        out = rc.recalibrate(self._forecast_json(), self._trajectories(), "2026-03-01")
        self.assertGreater(out["bias"], 0)  # model under-predicted -> positive shift
        self.assertGreaterEqual(out["cov80_corrected"], out["cov80_native"])
        self.assertIn("2026-04-01", out["corrected"])


if __name__ == "__main__":
    unittest.main()
