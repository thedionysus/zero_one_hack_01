import unittest

from app import agent
from app import changes


class _FakeContentBlock:
    def __init__(self, name, inp):
        self.type = "tool_use"
        self.name = name
        self.input = inp


class _FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeMessage:
    def __init__(self, blocks):
        self.content = blocks


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


class TestParseCurveball(unittest.TestCase):
    def test_no_client_uses_rule_based(self):
        c = agent.parse_curveball("prices rising 12% a month", client=None)
        self.assertEqual(c.kind, "trend")
        self.assertAlmostEqual(c.value, 0.12)

    def test_no_client_unparseable_returns_none(self):
        self.assertIsNone(agent.parse_curveball("hello there", client=None))

    def test_client_tool_use_becomes_change(self):
        resp = _FakeMessage([_FakeContentBlock("apply_change",
                                               {"kind": "trend", "value": 0.2})])
        client = _FakeClient(resp)
        c = agent.parse_curveball("gas is surging", client=client)
        self.assertEqual(c.kind, "trend")
        self.assertAlmostEqual(c.value, 0.2)
        self.assertEqual(len(client.messages.calls), 1)

    def test_client_no_tool_use_falls_back_to_rules(self):
        resp = _FakeMessage([])  # model returned no tool call
        client = _FakeClient(resp)
        c = agent.parse_curveball("prices are 20% higher", client=client)
        self.assertEqual(c.kind, "level")  # rule-based fallback kicked in
        self.assertAlmostEqual(c.value, 0.20)


class TestNarrate(unittest.TestCase):
    def test_no_client_uses_template(self):
        diff = {"recommendation": ("WAIT", "BUY_NOW"), "changed": True,
                "target_month": ("2026-11-01", "2026-04-01"),
                "savings": (100000.0, 500000.0), "savings_delta": 400000.0,
                "savings_pct": (0.1, 0.3)}
        text = agent.narrate(diff, changes.Change("trend", 0.12), 0.92, client=None)
        self.assertIn("BUY_NOW", text)

    def test_client_rephrases_via_text_block(self):
        resp = _FakeMessage([_FakeTextBlock("Lock in now — prices are climbing.")])
        client = _FakeClient(resp)
        diff = {"recommendation": ("WAIT", "BUY_NOW"), "changed": True,
                "target_month": ("2026-11-01", "2026-04-01"),
                "savings": (100000.0, 500000.0), "savings_delta": 400000.0,
                "savings_pct": (0.1, 0.3)}
        text = agent.narrate(diff, changes.Change("trend", 0.12), 0.92, client=client)
        self.assertEqual(text, "Lock in now — prices are climbing.")


if __name__ == "__main__":
    unittest.main()
