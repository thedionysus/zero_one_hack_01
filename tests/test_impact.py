import json
import os
import unittest

from lib import impact
from lib import pipeline

UREA_TRAJ = os.path.join(pipeline.DATA_DIR, "bakeoff", "urea", "OFF",
                         "backtest_trajectories.json")


def _load(path):
    with open(path) as f:
        return json.load(f)


class TestImpact(unittest.TestCase):
    def setUp(self):
        self.traj = _load(UREA_TRAJ)
        self.persona = pipeline.AUSTRIAN_UREA_PERSONA
        self.last_real = "2026-03-01"

    def test_scorable_windows_match_scoring(self):
        wins = impact._scorable_windows(self.traj, self.last_real)
        self.assertEqual(len(wins), 2)

    def test_backtest_shape(self):
        res = impact.backtest(self.traj, self.last_real, self.persona)
        self.assertEqual(res["n_windows"], 2)
        self.assertEqual(len(res["per_window"]), 2)
        for w in res["per_window"]:
            for key in ("agent_cost", "baseline_cost", "saving",
                        "ceiling_saving", "capture_ratio", "recommendation"):
                self.assertIn(key, w)

    def test_ceiling_bounds_agent_saving(self):
        res = impact.backtest(self.traj, self.last_real, self.persona)
        for w in res["per_window"]:
            self.assertLessEqual(w["saving"], w["ceiling_saving"] + 1e-6)

    def test_totals_consistent(self):
        res = impact.backtest(self.traj, self.last_real, self.persona)
        tot = sum(w["saving"] for w in res["per_window"])
        self.assertAlmostEqual(res["total_saving"], tot, places=6)


if __name__ == "__main__":
    unittest.main()
