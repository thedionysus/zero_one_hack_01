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

    def test_stock_curveball_updates_stock_slider(self):
        # "1 month of stock" -> stock_months intent -> 1 * 1000 t/mo demand = 1000 t.
        at = AppTest.from_file("app/main.py", default_timeout=30).run()
        at.chat_input[0].set_value(
            "a supplier fell through, only 1 month of stock left").run()
        self.assertFalse(at.exception)
        self.assertEqual(at.slider(key="stock").value, 1000.0)

    def test_example_chip_fires_curveball_and_flips_recommendation(self):
        # An example-prompt chip (shown only when the log is empty) routes through the
        # same curveball path as typed input: one click moves the levers and flips the
        # recommendation metric.
        at = AppTest.from_file("app/main.py", default_timeout=30).run()
        base_rec = at.metric[0].value
        at.button(key="chip_0").click().run()
        self.assertFalse(at.exception)
        self.assertNotEqual(at.metric[0].value, base_rec)
        self.assertGreaterEqual(len(at.session_state["chat_log"]), 2)

    def test_clear_empties_chat_log_and_zeroes_shock_levers(self):
        # The Clear control wipes the transcript AND resets the trend + level shock
        # levers back to zero.
        at = AppTest.from_file("app/main.py", default_timeout=30).run()
        at.chat_input[0].set_value("prices rising 30% a month").run()  # trend = 0.30
        at.chat_input[0].set_value("prices are 20% higher").run()      # level = 0.20
        self.assertEqual(at.slider(key="trend").value, 0.30)
        self.assertEqual(at.slider(key="level").value, 0.20)
        self.assertGreaterEqual(len(at.session_state["chat_log"]), 2)
        at.button(key="clear_chat").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["chat_log"], [])
        self.assertEqual(at.slider(key="trend").value, 0.0)
        self.assertEqual(at.slider(key="level").value, 0.0)

    def test_card_renders_transcript_with_avatars(self):
        # The conversation card renders the transcript with role avatars and does not
        # crash with a populated log.
        at = AppTest.from_file("app/main.py", default_timeout=30).run()
        at.chat_input[0].set_value("prices rising 30% a month").run()
        self.assertFalse(at.exception)
        messages = at.chat_message
        self.assertGreaterEqual(len(messages), 2)            # user + agent
        # Explicit role avatars (not the role-name default) confirm the new card chrome.
        self.assertEqual(messages[0].proto.avatar, "🧑")     # user turn
        self.assertEqual(messages[1].proto.avatar, "🤖")     # agent turn


if __name__ == "__main__":
    unittest.main()
