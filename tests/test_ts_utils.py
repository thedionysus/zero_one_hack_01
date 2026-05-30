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

    def test_median_odd(self):
        self.assertEqual(ts_utils.median([3, 1, 2]), 2)

    def test_median_even(self):
        self.assertEqual(ts_utils.median([1, 2, 3, 4]), 2.5)

    def test_percentile_nearest_rank(self):
        data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        self.assertEqual(ts_utils.percentile(data, 100), 10)
        self.assertEqual(ts_utils.percentile(data, 50), 5)
        self.assertEqual(ts_utils.percentile([42.0], 99), 42.0)

    def test_percentile_empty_raises(self):
        with self.assertRaises(ValueError):
            ts_utils.percentile([], 99)


if __name__ == "__main__":
    unittest.main()
