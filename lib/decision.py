"""Cost-minimising procurement decision (pure stdlib).

The substantive decision logic: given a (recalibrated) price forecast and a
warehouse persona, decide WHEN and HOW MUCH to buy over the horizon to cover
demand at minimum expected landed+holding cost, never stocking out.

Model. Under linear carrying cost and no capacity limit, each future month's
demand is independent, so we solve per demand-month: to cover demand in month d
we may purchase in any month p <= d (lead time 0 in v1) at that month's
risk-adjusted price, then carry the units (d - p) months. The unit landed cost is

    cost(p, d) = price[p] * (1 + monthly_carry * (d - p))

and the optimal purchase month is argmin over p <= d. Existing stock covers the
first `runway` demand months, so only demand beyond runway is scheduled.

Baseline ("buy-as-you-go"): cover each demand month d by buying in month d
(p = d), i.e. cost price[d], zero carry. Since p = d is always a candidate, the
optimiser never does worse than baseline -> savings >= 0.

Risk tolerance enters through which quantile prices the plan: a risk-averse
buyer prices at a higher quantile, where the (recalibrated) bands are wider for
later months, which penalises waiting and biases toward buying earlier.
"""
from dataclasses import dataclass
from lib.ts_utils import month_index

KG_PER_TONNE = 1000.0

# recommendation thresholds (fraction of scheduled tonnage bought in month 0)
BUY_NOW_FRAC = 0.60
WAIT_FRAC = 0.10


@dataclass(frozen=True)
class Persona:
    """Warehouse procurement profile. All quantities immutable."""
    monthly_demand_t: float
    current_stock_t: float = 0.0
    carrying_cost_pct_yr: float = 0.18
    risk_quantile: str = "p50"  # "p50" neutral; "p70"/"p80" risk-averse

    def __post_init__(self):
        if self.monthly_demand_t <= 0:
            raise ValueError("monthly_demand_t must be positive")
        if self.current_stock_t < 0:
            raise ValueError("current_stock_t must be non-negative")
        if self.carrying_cost_pct_yr < 0:
            raise ValueError("carrying_cost_pct_yr must be non-negative")

    @property
    def monthly_carry(self):
        return self.carrying_cost_pct_yr / 12.0

    @property
    def runway_months(self):
        return self.current_stock_t / self.monthly_demand_t


@dataclass(frozen=True)
class OrderPlan:
    months: list            # ordered forecast month dates
    prices: list            # risk-adjusted price per month (USD/kg)
    orders_t: dict          # {month_date: tonnes to buy in that month}
    purchase_for: dict      # {demand_month_date: chosen purchase_month_date}
    optimal_cost: float     # USD
    baseline_cost: float    # USD
    savings: float          # USD (baseline - optimal)
    savings_pct: float      # fraction of baseline
    recommendation: str     # "BUY_NOW" | "WAIT" | "SPLIT" | "COVERED"
    target_month: str       # primary purchase month (or "" when COVERED)
    rationale: str


def _price_series(forecast_block, risk_quantile):
    """Ordered [(date, price)] at the chosen quantile key."""
    ordered = sorted(forecast_block.items(), key=lambda kv: month_index(kv[0]))
    out = []
    for date, band in ordered:
        if risk_quantile not in band:
            raise ValueError(f"quantile {risk_quantile} missing at {date}")
        out.append((date, float(band[risk_quantile])))
    return out


def _optimal_purchase_index(prices, d, monthly_carry):
    """argmin_{p<=d} price[p]*(1+carry*(d-p)); returns (best_p, unit_cost)."""
    best_p, best_cost = d, prices[d]  # buy-as-you-go is always allowed
    for p in range(d + 1):
        cost = prices[p] * (1.0 + monthly_carry * (d - p))
        if cost < best_cost:
            best_p, best_cost = p, cost
    return best_p, best_cost


def solve(forecast_block, persona):
    """Solve the procurement schedule. Returns an OrderPlan."""
    series = _price_series(forecast_block, persona.risk_quantile)
    months = [d for d, _p in series]
    prices = [p for _d, p in series]
    h = len(months)
    carry = persona.monthly_carry
    demand = persona.monthly_demand_t
    # whole months of demand already covered by stock -> skip those demand months
    covered = int(persona.runway_months)  # floor: partial month still needs buying

    orders_t = {m: 0.0 for m in months}
    purchase_for = {}
    optimal_cost = 0.0
    baseline_cost = 0.0
    for d in range(covered, h):
        p, unit = _optimal_purchase_index(prices, d, carry)
        orders_t[months[p]] += demand
        purchase_for[months[d]] = months[p]
        optimal_cost += demand * KG_PER_TONNE * unit
        baseline_cost += demand * KG_PER_TONNE * prices[d]

    savings = baseline_cost - optimal_cost
    savings_pct = (savings / baseline_cost) if baseline_cost > 0 else 0.0
    rec, target, why = _recommend(months, orders_t, covered, h)
    return OrderPlan(
        months=months, prices=prices, orders_t=orders_t, purchase_for=purchase_for,
        optimal_cost=optimal_cost, baseline_cost=baseline_cost,
        savings=savings, savings_pct=savings_pct,
        recommendation=rec, target_month=target, rationale=why,
    )


def _recommend(months, orders_t, covered, h):
    total = sum(orders_t.values())
    if total <= 0:
        return "COVERED", "", "Existing stock covers the whole forecast horizon."
    now_month = months[0]
    frac_now = orders_t[now_month] / total
    # primary purchase month = largest order, earliest on ties
    target = max(months, key=lambda m: (orders_t[m], -month_index(m)))
    n_active = sum(1 for m in months if orders_t[m] > 0)
    if frac_now >= BUY_NOW_FRAC:
        return ("BUY_NOW", now_month,
                f"{frac_now:.0%} of scheduled tonnage is cheapest bought now — prices are "
                f"expected to rise faster than the cost of carrying inventory.")
    if frac_now <= WAIT_FRAC and n_active <= 2:
        return ("WAIT", target,
                f"Buying now is not optimal; the cheapest landed cost concentrates around "
                f"{target}. Hold and buy then.")
    return ("SPLIT", target,
            f"Optimal cost spreads purchases across {n_active} months (largest at {target}); "
            f"stagger orders rather than buying all at once.")
