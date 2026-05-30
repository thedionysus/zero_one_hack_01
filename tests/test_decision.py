import unittest
from lib import decision as dec

MONTHS = ["2026-04-01", "2026-05-01", "2026-06-01",
          "2026-07-01", "2026-08-01", "2026-09-01"]


def block(prices_by_q):
    """prices_by_q: {quantile_key: [price per month]} -> forecast_block."""
    out = {}
    for i, m in enumerate(MONTHS):
        out[m] = {q: vals[i] for q, vals in prices_by_q.items()}
    return out


def flat(p, q="p50"):
    return block({q: [p] * len(MONTHS)})


def rising(start, step, q="p50"):
    return block({q: [start + step * i for i in range(len(MONTHS))]})


class TestPersona(unittest.TestCase):
    def test_runway(self):
        p = dec.Persona(monthly_demand_t=100, current_stock_t=300)
        self.assertAlmostEqual(p.runway_months, 3.0)
        self.assertAlmostEqual(p.monthly_carry, 0.18 / 12)

    def test_validation(self):
        with self.assertRaises(ValueError):
            dec.Persona(monthly_demand_t=0)
        with self.assertRaises(ValueError):
            dec.Persona(monthly_demand_t=100, current_stock_t=-1)


class TestSolveRising(unittest.TestCase):
    def test_rising_prices_buy_now_with_savings(self):
        p = dec.Persona(monthly_demand_t=100, current_stock_t=0, carrying_cost_pct_yr=0.18)
        plan = dec.solve(rising(0.30, 0.05), p)
        self.assertEqual(plan.recommendation, "BUY_NOW")
        self.assertEqual(plan.target_month, MONTHS[0])
        self.assertGreater(plan.savings, 0.0)
        self.assertGreater(plan.savings_pct, 0.0)
        # most tonnage bought in month 0
        self.assertGreater(plan.orders_t[MONTHS[0]], plan.orders_t[MONTHS[-1]])


class TestSolveFlat(unittest.TestCase):
    def test_flat_prices_no_savings_buy_as_you_go(self):
        p = dec.Persona(monthly_demand_t=100, current_stock_t=0)
        plan = dec.solve(flat(0.40), p)
        self.assertAlmostEqual(plan.savings, 0.0)
        # each demand month bought in its own month
        for m in MONTHS:
            self.assertAlmostEqual(plan.orders_t[m], 100.0)
        self.assertEqual(plan.recommendation, "SPLIT")


class TestRunwaySkipsFrontMonths(unittest.TestCase):
    def test_stock_covers_first_months(self):
        p = dec.Persona(monthly_demand_t=100, current_stock_t=300)  # runway 3
        plan = dec.solve(flat(0.40), p)
        # only demand months 3,4,5 need buying -> 300 t total
        self.assertAlmostEqual(sum(plan.orders_t.values()), 300.0)

    def test_full_coverage_returns_covered(self):
        p = dec.Persona(monthly_demand_t=100, current_stock_t=10_000)
        plan = dec.solve(flat(0.40), p)
        self.assertEqual(plan.recommendation, "COVERED")
        self.assertAlmostEqual(sum(plan.orders_t.values()), 0.0)


class TestRiskQuantileShiftsBehaviour(unittest.TestCase):
    def test_risk_averse_buys_earlier(self):
        # P50 flat, but P80 rises (wider bands later) -> risk-averse should buy now
        b = block({"p50": [0.40] * 6, "p80": [0.40 + 0.04 * i for i in range(6)]})
        neutral = dec.solve(b, dec.Persona(monthly_demand_t=100, risk_quantile="p50"))
        averse = dec.solve(b, dec.Persona(monthly_demand_t=100, risk_quantile="p80"))
        self.assertGreater(averse.orders_t[MONTHS[0]], neutral.orders_t[MONTHS[0]])
        self.assertEqual(averse.recommendation, "BUY_NOW")

    def test_missing_quantile_raises(self):
        with self.assertRaises(ValueError):
            dec.solve(flat(0.40, q="p50"), dec.Persona(monthly_demand_t=100, risk_quantile="p80"))


if __name__ == "__main__":
    unittest.main()
