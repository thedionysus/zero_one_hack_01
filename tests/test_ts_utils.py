import unittest
from lib import ts_utils


class TestDateHelpers(unittest.TestCase):
    def test_month_index_is_monotonic_by_month(self):
        self.assertEqual(
            ts_utils.month_index("2024-02-01") - ts_utils.month_index("2024-01-01"), 1
        )
        self.assertEqual(
            ts_utils.month_index("2024-01-01") - ts_utils.month_index("2023-12-01"), 1
        )

    def test_index_to_month_round_trips(self):
        for d in ["1996-04-01", "2023-11-01", "2026-03-01"]:
            self.assertEqual(ts_utils.index_to_month(ts_utils.month_index(d)), d)


class TestStats(unittest.TestCase):
    def test_mean(self):
        self.assertAlmostEqual(ts_utils.mean([1.0, 2.0, 3.0]), 2.0)

    def test_mean_single_element(self):
        self.assertEqual(ts_utils.mean([5.0]), 5.0)

    def test_mean_empty_raises(self):
        with self.assertRaises(ValueError):
            ts_utils.mean([])

    def test_median_odd(self):
        self.assertEqual(ts_utils.median([3, 1, 2]), 2)

    def test_median_even(self):
        self.assertEqual(ts_utils.median([1, 2, 3, 4]), 2.5)

    def test_median_empty_raises(self):
        with self.assertRaises(ValueError):
            ts_utils.median([])

    def test_percentile_nearest_rank(self):
        data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        self.assertEqual(ts_utils.percentile(data, 100), 10)
        self.assertEqual(ts_utils.percentile(data, 50), 5)
        self.assertEqual(ts_utils.percentile([42.0], 99), 42.0)

    def test_percentile_empty_raises(self):
        with self.assertRaises(ValueError):
            ts_utils.percentile([], 99)

    def test_percentile_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            ts_utils.percentile([1, 2, 3], 101)
        with self.assertRaises(ValueError):
            ts_utils.percentile([1, 2, 3], -1)


class TestInterpolate(unittest.TestCase):
    def test_midpoint_for_single_interior_gap(self):
        series = {"2023-10-01": 100.0, "2023-12-01": 200.0}
        self.assertAlmostEqual(
            ts_utils.linear_interpolate_gap(series, "2023-11-01"), 150.0
        )

    def test_weighted_for_wider_gap(self):
        # gap one month after prev (Feb) of a Jan..Apr span
        series = {"2024-01-01": 0.0, "2024-04-01": 30.0}
        self.assertAlmostEqual(
            ts_utils.linear_interpolate_gap(series, "2024-02-01"), 10.0
        )

    def test_non_month_aligned_missing_date_raises(self):
        series = {"2023-10-01": 1.0, "2023-12-01": 2.0}
        with self.assertRaises(ValueError):
            ts_utils.linear_interpolate_gap(series, "2023-11-15")


class TestDetectGaps(unittest.TestCase):
    def test_finds_single_interior_gap(self):
        dates = ["2023-10-01", "2023-12-01", "2024-01-01"]
        self.assertEqual(ts_utils.detect_gaps(dates), ["2023-11-01"])

    def test_no_gaps_returns_empty(self):
        dates = ["2024-01-01", "2024-02-01", "2024-03-01"]
        self.assertEqual(ts_utils.detect_gaps(dates), [])


class TestOutlierJumps(unittest.TestCase):
    def test_flags_large_jump_over_floor(self):
        # flat ~1% MoM noise then a +54% spike on the last month
        series = {}
        val = 100.0
        for i in range(12):
            series[ts_utils.index_to_month(24000 + i)] = val
            val *= 1.01
        spike_date = ts_utils.index_to_month(24000 + 12)
        series[spike_date] = val * 1.54
        flagged = ts_utils.detect_outlier_jumps(series, floor_pct=40.0)
        self.assertIn(spike_date, flagged)

    def test_no_flags_for_calm_series(self):
        series = {ts_utils.index_to_month(24000 + i): 100.0 + i for i in range(12)}
        self.assertEqual(ts_utils.detect_outlier_jumps(series, floor_pct=40.0), [])


class TestFlatTail(unittest.TestCase):
    def test_flags_run_of_four_or_more(self):
        series = {ts_utils.index_to_month(24000 + i): v
                  for i, v in enumerate([1.0, 2.0, 3.0, 5.0, 5.0, 5.0, 5.0])}
        self.assertEqual(ts_utils.detect_flat_tail(series, min_run=4), 4)

    def test_no_flag_for_short_plateau(self):
        series = {ts_utils.index_to_month(24000 + i): v
                  for i, v in enumerate([1.0, 2.0, 5.0, 5.0])}
        self.assertEqual(ts_utils.detect_flat_tail(series, min_run=4), 0)


class TestCollapseDuplicateTowns(unittest.TestCase):
    def test_averages_duplicate_town_year(self):
        rows = [
            {"ISO": "BFA", "year": "2017", "Town": "Yako",
             "price_usd_per_kg_ppp": "1.00", "longitude": "1.0"},
            {"ISO": "BFA", "year": "2017", "Town": "Yako",
             "price_usd_per_kg_ppp": "2.00", "longitude": "1.0"},
            {"ISO": "GHA", "year": "2017", "Town": "Tamale",
             "price_usd_per_kg_ppp": "0.50", "longitude": "9.0"},
        ]
        collapsed, keys = ts_utils.collapse_duplicate_towns(rows)
        self.assertEqual(len(collapsed), 2)
        yako = [r for r in collapsed if r["Town"] == "Yako"][0]
        self.assertAlmostEqual(float(yako["price_usd_per_kg_ppp"]), 1.50)
        self.assertIn(("BFA", "2017", "Yako"), keys)
        self.assertEqual(len(keys), 1)


class TestFlagLowPrice(unittest.TestCase):
    def test_below_floor_flagged(self):
        self.assertTrue(ts_utils.flag_low_price(0.01))
        self.assertTrue(ts_utils.flag_low_price(0.09))

    def test_at_or_above_floor_not_flagged(self):
        self.assertFalse(ts_utils.flag_low_price(0.10))
        self.assertFalse(ts_utils.flag_low_price(1.46))

    def test_nan_price_flagged(self):
        self.assertTrue(ts_utils.flag_low_price(float('nan')))


if __name__ == "__main__":
    unittest.main()
