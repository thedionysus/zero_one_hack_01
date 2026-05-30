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


    def test_chat_curveball_flips_recommendation(self):
        # A typed rising-trend curveball must move the trend slider AND flip the
        # recommendation, via the offline rule-based path (no API key in tests).
        at = AppTest.from_file("app/main.py", default_timeout=30).run()
        base_rec = at.metric[0].value  # Recommendation metric is first
        at.chat_input[0].set_value("prices rising 30% a month").run()
        self.assertNotEqual(at.metric[0].value, base_rec)
        self.assertEqual(at.slider(key="trend").value, 0.30)  # chat moved the slider

    def test_unparseable_curveball_is_handled_gracefully(self):
        # An unparseable curveball must not crash and must not move any lever; it
        # should surface a chat message instead.
        at = AppTest.from_file("app/main.py", default_timeout=30).run()
        base_trend = at.slider(key="trend").value
        at.chat_input[0].set_value("tell me a joke").run()
        self.assertFalse(at.exception)
        self.assertEqual(at.slider(key="trend").value, base_trend)
        self.assertGreaterEqual(len(at.chat_message), 1)


if __name__ == "__main__":
    unittest.main()
