import unittest

try:
    import plotly.graph_objects as go  # noqa: F401
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

if HAS_PLOTLY:
    from app import charts
    from app import state as st


@unittest.skipUnless(HAS_PLOTLY, "plotly not installed (run under .venv)")
class TestCharts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cal = st.calibrate_all()
        s = st.AppState.default(cls.cal)
        cls.res = st.solve_state(s, cls.cal)

    def test_forecast_figure_has_band_and_line(self):
        fig = charts.forecast_figure(
            self.res["native"], self.res["corrected"], self.res["current_plan"])
        import plotly.graph_objects as go
        self.assertIsInstance(fig, go.Figure)
        self.assertGreaterEqual(len(fig.data), 2)

    def test_calibration_figure_two_bars(self):
        fig = charts.calibration_figure(
            self.res["cov80_native"], self.res["cov80_corrected"])
        self.assertEqual(len(fig.data), 1)
        self.assertEqual(len(fig.data[0].x), 2)

    def test_savings_figure_is_bar_over_months(self):
        fig = charts.savings_figure(self.res["current_plan"])
        self.assertGreaterEqual(len(fig.data), 1)
        self.assertEqual(len(fig.data[0].x), len(self.res["current_plan"].months))

    def test_trust_rows_cover_all_five(self):
        rows = charts.trust_rows(self.cal)
        self.assertEqual(len(rows), 5)
        for r in rows:
            for k in ("fertilizer", "trust", "label", "cov80_native", "cov80_corrected"):
                self.assertIn(k, r)
        scores = [r["trust"] for r in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
