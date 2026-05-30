import unittest

try:
    from streamlit.testing.v1 import AppTest
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False


@unittest.skipUnless(HAS_STREAMLIT, "streamlit not installed (run under .venv)")
class TestAppSmoke(unittest.TestCase):
    def setUp(self):
        import os
        os.environ["PROCUREMENT_NO_LLM"] = "1"  # force offline path in tests

    def _run(self):
        at = AppTest.from_file("app/main.py", default_timeout=30)
        return at.run()

    def test_app_runs_without_exception(self):
        at = self._run()
        self.assertFalse(at.exception)

    def test_shows_a_recommendation_metric(self):
        at = self._run()
        self.assertGreaterEqual(len(at.metric), 1)

    def test_trend_slider_flips_recommendation_metric(self):
        base = self._run()
        base_rec = base.metric[0].value  # the Recommendation metric is rendered first
        at = AppTest.from_file("app/main.py", default_timeout=30).run()
        at.slider(key="trend").set_value(at.slider(key="trend").max).run()
        self.assertNotEqual(at.metric[0].value, base_rec)
        self.assertIn(at.metric[0].value, {"BUY_NOW", "WAIT", "SPLIT", "COVERED"})


if __name__ == "__main__":
    unittest.main()
