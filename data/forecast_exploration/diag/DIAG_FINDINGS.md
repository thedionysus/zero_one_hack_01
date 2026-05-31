# Why was external_signals empty? — diagnostic experiment (2026-05-30)

Controlled test: **same settings, vary only the series.** All runs `recency_factor=0.0` (full
archive), no filters, h=6, `backtest=false`, last 120 monthly points.

| Run | series | recency_factor | external_signals | drivers | cost |
|-----|--------|----------------|------------------|---------|------|
| Run A (earlier) | urea | 0.5 | **empty {}** | 0 | €0.89 |
| Run B (earlier) | urea | 0.7 | **empty {}** | 0 | €0.86 |
| D4 | **WTI crude** | 0.0 | **48.9 KB** | ~35 | €3.27 |
| D3 | **MOP potash (fertilizer!)** | 0.0 | **49.7 KB** | ~35 | €2.54 |
| D1 | urea | 0.0 | _pending_ | ? | ? |
| D2 | DAP | 0.0 | _pending_ | ? | ? |
| D5 | natural gas | 0.0 | _pending_ | ? | ? |

## CORRECTION to the earlier "the knobs do nothing" claim

That claim was based on too narrow a sweep: Run A vs B only compared `recency_factor` **0.5 vs 0.7**
(both recent-weighted) — never **0.0** (full archive). At `recency_factor=0.0`:
- **WTI crude** matched ~35 drivers — so the account/archive CAN surface drivers (refutes the
  "archive thin / feature disabled" hypothesis).
- **MOP potash, a fertilizer benchmark, also matched ~35 drivers** — so it is NOT simply
  "fertilizers are unmatchable." A fertilizer DID get drivers once the full archive was searched.

**Most likely explanation: `recency_factor` was the lever all along.** At the default-ish 0.5–0.7,
the driver-selection news/market window is too recent and the candidate search returns nothing
usable for these long monthly series; at 0.0 (full archive) the search surfaces a rich candidate set.
The runtime corroborates this: `recency=0.0` jobs took ~8–20 min vs ~3 min for `recency=0.5` —
a much larger search. (Caveat: D3/D4 also used 120-pt trimmed series vs Run A/B's 360 pts; length
could contribute. D1 urea at recency 0.0 + 120 pts is the clean tie-breaker — pending.)

## What a populated external_signals.json looks like (WTI crude, ~35 drivers)
Per driver: `driver_name`, `pearson_correlation` (by lag 3–6 + overall), `direction` (sign by
horizon), `importance` (model attribution 0–100 by horizon). Selected WTI drivers:
- **"Equities – World"** — importance **100**, corr ~0.56 (the model's dominant driver)
- "Commodity price – Index" — corr **0.77**, importance 0 (highly correlated, but model didn't lean on it)
- "Services/Retail/Industry – price expectations" (Italy, Greece, Albania, Malta…) — corr 0.7–0.8
- "Stock levels for oil products" (Germany, Hungary), "Crude oil imports – Norway Ekofisk"
- **Spurious**: "Population – Afghanistan" importance **99.85**, "Population – Europe/Syria/Lebanon" —
  monotonic-trend artifacts, no causal meaning.

### Output-interpretation lessons for the decision layer
1. **`importance` ≠ `pearson_correlation`.** Some high-corr drivers have importance 0; some high-importance
   drivers are spurious trends. Use both, and sanity-check names.
2. **The archive is heavily macro/European** (HICP, EU price-expectation surveys, Eurostat-style series)
   + global financial aggregates (Equities-World, Commodities-World). Drivers that match are mostly
   inflation/expectations/energy-stock proxies — useful context, not fertilizer-specific fundamentals.
3. **Driver-aware forecasts cost ~3–4× more** (€2.5–3.3 vs €0.85) and run much longer.
4. To get drivers on these series, **set `recency_factor` low (≈0.0)**; keyword/category/region hints
   were secondary (Run B's hints with recency 0.7 still returned nothing).
