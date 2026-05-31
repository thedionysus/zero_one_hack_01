# Granary — Forecasting AI (Sybilion)

> Turning a probabilistic price forecast into a defensible procurement decision —
> with the forecast's own confidence bands recalibrated so the decision can be trusted.

---

## Team

- **Arlav Dullahi** — decision engine, app, evaluation
- **h12014883 (TU Wien)** — data engineering, forecast bake-off

**Track:** Forecasting AI (Sybilion)

---

## TL;DR

**Granary** is a fertilizer-procurement decision agent. It takes Sybilion's probabilistic
price forecasts, **recalibrates their (badly overconfident) confidence bands** against
historical residuals, then solves a cost-minimizing **when-and-how-much-to-buy** schedule
for a warehouse — and re-solves live when a user types a real-world curveball
("a supplier fell through", "gas spiked 25%/month"). The headline technical result is the
calibration lift: an "80%" band that historically covered only **~21–50%** of actual prices
is rebuilt to cover **~80%**, which is what makes the buy/wait recommendation defensible.

---

## Problem

A forecast is a number; a number alone doesn't change a decision. Agricultural buyers face a
concrete question every month: **do I buy my urea now, or wait?** Buy too early and you pay
to carry inventory; wait too long and you eat a price spike. Sybilion ships *probabilistic*
forecasts (quantile bands), which is exactly the right input for that trade-off — **except
the bands are not trustworthy as shipped.**

We measured it: on urea, the model's nominal **80% band covered only ~21%** of realized
prices, and actuals sat **above** the median forecast during sustained rallies. A procurement
tool that prices decisions off those bands is confidently wrong. So the problem we chose:
**make the forecast's uncertainty honest, then turn it into a cost-minimizing purchase
schedule a buyer can defend to their CFO.** We focus on five fertilizers (urea, DAP, MOP,
TSP, phosphate rock) and an Austrian warehouse persona.

---

## Approach

- **Conformal recalibration of the bands (`lib/recalibration.py`).** We rebuild each forecast
  month's band from hindcast residuals `r = actual − P50`: `corrected_q(τ) = P50 + quantile(r, τ)`.
  This simultaneously **widens** the band to the true error spread (fixes overconfidence) and
  **shifts** it by the median residual (fixes the low bias). Split-conformal in spirit.
- **Cost-minimizing decision core (`lib/decision.py`, pure stdlib).** Per demand-month, pick the
  purchase month minimizing `price[p]·(1 + carry·(d−p))`. Buy-as-you-go (`p=d`) is always a
  candidate, so the agent **never does worse than naive** (savings ≥ 0). A risk lever prices
  the plan at P50/P70/P80 of the *recalibrated* band.
- **Forecast-agnostic shocks (`lib/shocks.py`).** Two levers: a **level shift** (decision-inert,
  scales magnitude) and a compounding **trend shift** (steepens the curve and can flip the
  recommendation toward BUY_NOW). This is the "adapt to a mid-run assumption shift" mechanism.
- **Claude as a thin NL edge, not the brain (`app/agent.py`).** Claude does exactly two jobs:
  parse one free-text curveball into a lever change, and narrate the before→after diff. The
  decision itself is deterministic stdlib. **No API key? It degrades to a deterministic offline
  parser/narrator** — the demo runs fully offline.
- **Rigorous backtest (`lib/impact.py`).** Leave-one-out hindcast: recalibrate from the *other*
  windows (no leakage), decide on the forecast, **re-price on realized actuals** — "decide on
  the forecast, pay on the truth" — and compare against a perfect-hindsight ceiling.

Runs locally; Streamlit UI + Plotly charts. Decision core has **zero** third-party dependencies.

---

## How to run it

See [`README.md`](./README.md) for full detail. Short version:

```bash
git clone https://github.com/thedionysus/zero_one_hack_01.git
cd zero_one_hack_01
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app/main.py          # opens http://localhost:8501
```

No API key required — the chat curveball uses a deterministic offline fallback. To enable the
Claude-powered parse/narrate, put `ANTHROPIC_API_KEY=...` in a `.env` file (gitignored).
Run the tests with `.venv/bin/python -m unittest discover -s tests`.

---

## Results

**Headline — calibration lift (the core, verifiable result).** Recalibration moves the in-sample
80% band coverage onto the 80% target across all five fertilizers:

| Fertilizer      | 80% coverage (native → corrected) | Trust score | Default recommendation | Forward saving vs naive* |
|-----------------|-----------------------------------|-------------|------------------------|--------------------------|
| urea            | 0.21 → 0.83                       | 0.48 (med)  | SPLIT                  | €387,250                 |
| phosphate-rock  | 1.00 → 0.83                       | 0.69 (high) | WAIT                   | €166,164                 |
| DAP             | 0.21 → 0.83                       | 0.47 (med)  | SPLIT                  | €11,896                  |
| TSP             | 0.21 → 0.83                       | 0.44 (med)  | SPLIT                  | €9,056                   |
| MOP             | 0.50 → 0.83                       | 0.54 (med)  | SPLIT                  | €0                       |

*\*Forward saving is priced on the **corrected** forecast: optimal schedule vs. a buy-as-you-go
buyer over the 12-month horizon. It isolates the value of **timing**, assuming the forecast is
right.* MOP's **€0 is a correct result**, not a bug — its prices never rise faster than the 1.5%/mo
carrying cost, so buying ahead can't pay and the agent correctly defers to buy-as-you-go.

**Baseline comparison — out-of-sample backtest (`lib/impact.py`).** Decisions made on the
forecast, then paid at realized prices, vs. buy-as-you-go, over the available hindcast windows:

| Fertilizer | Windows | Total saving % (out-of-sample) |
|------------|---------|--------------------------------|
| urea       | 2       | **+2.69%**                     |
| TSP        | 2       | 0.00%                          |
| MOP        | 2       | −0.28%                         |
| DAP        | 2       | −1.07%                         |
| phosphate  | 2       | −3.33%                         |

We report this **honestly**: on a 2-window hindcast the policy is directionally positive on
urea (its strongest, most-rallying series) but **mixed-to-negative elsewhere**. The sample is
too small to claim robust out-of-sample profit — see "What didn't work".

**Evidence.** 163 unit/integration tests pass (`.venv/bin/python -m unittest discover -s tests`).
Calibration diagnostics in `data/forecast_exploration/`.

---

## What worked

- **The calibration story is real and measurable.** The 0.21→0.83 coverage lift on urea is the
  single most defensible thing we built, and it's *visible* in the app as a two-bar chart — the
  jury can see the native band was 4× too narrow.
- **Decision core is provably no-worse-than-naive.** Seeding the argmin with buy-as-you-go means
  `savings ≥ 0` by construction; the level-shift-inertness property is unit-tested.
- **The offline fallback.** The whole adaptive-curveball demo runs with no API key — Claude is an
  enhancement, not a dependency, so the demo can't fail on a network blip.

## What didn't work

- **Out-of-sample savings are thin.** Only 2 scorable hindcast windows survive the staleness
  filter, and on that sample the policy is negative on 3 of 5 fertilizers. The forward (in-model)
  savings look great; the truth-paid backtest says "directional, not proven." We chose to surface
  this rather than hide it.
- **Trust score is a blunt composite.** It blends calibration/skill/accuracy into one number;
  three of five fertilizers land in an undifferentiated "medium" bucket.
- **Python 3.14 friction.** A lazy numpy import inside Plotly, interrupted by a Streamlit rerun,
  left numpy half-initialized and crashed every chart render until restart; we fixed it with an
  eager import (`app/charts.py`).

## What you'd do with another 36 hours

- Widen the hindcast: generate more scorable windows (relax the staleness filter, add
  cross-fertilizer pooling) to get the out-of-sample backtest to statistical significance.
- Add **driver-importance** attribution (which input moved the forecast) to the chart, closing
  the last Sybilion track deliverable.
- Replace the single trust scalar with a per-dimension trust panel.

---

## Track-specific deliverables (Forecasting AI / Sybilion)

- [x] Working application — not slideware (`app/main.py`, Streamlit)
- [x] Backtest results validating the decision logic (`lib/impact.py`, table above)
- [ ] **Driver-importance visualization** — *not yet in the demo* (honest gap; see next steps)
- [x] Agent adapts to a mid-run assumption shift (chat curveball → trend/level shock → re-solve)
- [x] Domain choice rationale stated above in "Problem"

---

## Credits & dependencies

- **Open-source libraries:** streamlit 1.58.0, plotly 6.7.0, anthropic 0.105.2 (UI/chat only;
  the decision core is pure Python stdlib). numpy is a transitive Plotly dependency.
- **Pre-trained models:** none of our own; Sybilion provided the price forecasts.
- **External APIs:** Anthropic Claude (optional NL parse + narration; offline fallback otherwise).
- **AI coding assistants used:** Claude Code.
- **Datasets:** Sybilion fertilizer price forecasts + hindcast trajectories (provided for the track).

---

## A note on honesty

The **forward saving** numbers are priced on our own corrected forecast — they measure timing
value *if the forecast holds*, not realized profit. The **out-of-sample backtest** is the honest
check, and on a small 2-window hindcast it is only convincing for urea. Nothing in the decision
core is mocked; the only stubbed-out path is the offline NL parser, which is a deterministic
keyword/number extractor used when no `ANTHROPIC_API_KEY` is present (clearly labeled in
`app/agent.py`).

---

*Submitted by team Granary for Zero One Hack_01, May 2026.*
