import unittest
from lib import forecast_scoring as fs
from lib import ts_utils as tu


class TestSeasonalNaive(unittest.TestCase):
    def test_naive_mae_lag(self):
        series = {"2020-01-01": 10.0, "2020-02-01": 12.0,
                  "2020-03-01": 11.0, "2020-04-01": 15.0}
        # lag-2 diffs: |11-10|=1, |15-12|=3 -> mean 2.0
        self.assertAlmostEqual(fs.seasonal_naive_mae(series, season=2), 2.0)

    def test_naive_rmse_lag(self):
        series = {"2020-01-01": 10.0, "2020-02-01": 12.0,
                  "2020-03-01": 11.0, "2020-04-01": 15.0}
        # sqrt((1 + 9)/2) = sqrt(5)
        self.assertAlmostEqual(fs.seasonal_naive_rmse(series, season=2), 5.0 ** 0.5)

    def test_naive_too_short_raises(self):
        with self.assertRaises(ValueError):
            fs.seasonal_naive_mae({"2020-01-01": 1.0}, season=2)


class TestExtractPoints(unittest.TestCase):
    def _traj(self):
        return {"data": [
            {"forecast_end": "2025-08-01", "forecast_series": {
                "2025-07-01": {"actual": 10.0, "quantile_forecast": {"0.50": 8.0}},
                "2025-08-01": {"actual": 20.0, "quantile_forecast": {"0.50": 16.0}},
            }},
            {"forecast_end": "2026-09-01", "forecast_series": {  # STALE: past last_real
                "2026-09-01": {"actual": None, "quantile_forecast": {"0.50": 1.0}},
            }},
        ]}

    def test_excludes_stale_window(self):
        pts, scored, excluded = fs.extract_scorable_points(self._traj(), "2026-03-01")
        self.assertEqual(scored, 1)
        self.assertEqual(excluded, 1)
        self.assertEqual(len(pts), 2)
        self.assertEqual(pts[0], (10.0, {"0.50": 8.0}))

    def test_skips_none_actual_in_kept_window(self):
        traj = {"data": [
            {"forecast_end": "2025-08-01", "forecast_series": {
                "2025-07-01": {"actual": None, "quantile_forecast": {"0.50": 8.0}},
                "2025-08-01": {"actual": 20.0, "quantile_forecast": {"0.50": 16.0}},
            }},
        ]}
        pts, scored, excluded = fs.extract_scorable_points(traj, "2026-03-01")
        self.assertEqual((scored, excluded, len(pts)), (1, 0, 1))


class TestPointMetrics(unittest.TestCase):
    POINTS = [
        (10.0, {"0.05": 4.0, "0.10": 5.0, "0.50": 8.0, "0.90": 9.0, "0.95": 9.5}),
        (20.0, {"0.05": 12.0, "0.10": 14.0, "0.50": 16.0, "0.90": 22.0, "0.95": 25.0}),
    ]

    def test_mae(self):
        self.assertAlmostEqual(fs.mae_points(self.POINTS), 3.0)  # (2+4)/2

    def test_rmse(self):
        self.assertAlmostEqual(fs.rmse_points(self.POINTS), 10.0 ** 0.5)  # sqrt((4+16)/2)

    def test_mape(self):
        # (0.2 + 0.2)/2 * 100
        self.assertAlmostEqual(fs.mape_points(self.POINTS), 20.0)

    def test_coverage_80(self):
        # pt1: 5..9 does NOT cover 10 -> miss; pt2: 14..22 covers 20 -> hit => 0.5
        self.assertAlmostEqual(fs.band_coverage(self.POINTS, *fs.BAND_80), 0.5)

    def test_coverage_90(self):
        # pt1: 4..9.5 misses 10; pt2: 12..25 covers 20 => 0.5
        self.assertAlmostEqual(fs.band_coverage(self.POINTS, *fs.BAND_90), 0.5)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            fs.mae_points([])
