# Granary — buy fertilizer at the right moment

**Granary turns a probabilistic price forecast into a defensible procurement decision.**
It recalibrates Sybilion's quantile price forecasts so their confidence bands are honest, then
solves a cost-minimizing *when-and-how-much-to-buy* schedule for a warehouse — and re-solves
live when you type a real-world curveball ("a supplier fell through", "gas spiked 25%/month").

> Zero One Hack_01 · Forecasting AI track (Sybilion) · team **Granary**

---

## Why this problem (domain rationale)

A forecast is a number; a number alone doesn't change a decision. Agricultural buyers face one
concrete question every month: **buy now, or wait?** Buy too early and you pay to carry stock;
wait too long and a price spike eats your margin — and those input costs flow straight through to
the price of food.

Probabilistic forecasts are the right input for that trade-off, **but Sybilion's bands aren't
trustworthy as shipped**: on urea, the nominal *80%* confidence band historically covered only
**~21%** of realized prices, and actuals sat *above* the median during sustained rallies. A tool
that prices decisions off those bands is confidently wrong. Granary fixes the uncertainty first,
then makes the buy/wait call on top of it — across urea, DAP, MOP, TSP, and phosphate rock.

---

## How it works

```
Sybilion forecast ──▶ recalibration ──▶ decision core ──▶ recommendation + schedule
  (quantile bands)     (lib/...)          (lib/decision)    (BUY_NOW / WAIT / SPLIT)
                          ▲                     ▲
                     honest bands          cost-min argmin
                                                ▲
   chat curveball ──▶ Claude parse ──▶ shock levers ──▶ re-solve ──▶ narrate the diff
   (app/agent.py)     (or offline fallback)  (lib/shocks)
```

1. **Recalibration (`lib/recalibration.py`)** — rebuild each month's band from hindcast residuals
   `r = actual − P50`, so `corrected_q(τ) = P50 + quantile(r, τ)`. Widens the band to the true
   error spread *and* shifts it to remove the low bias. Coverage moves from ~21–50% to **~80%**.
2. **Decision core (`lib/decision.py`, pure stdlib)** — for each demand month, buy in the month
   minimizing `price[p]·(1 + carry·(d−p))`. Buy-as-you-go is always a candidate, so the agent is
   **never worse than naive** (savings ≥ 0). A risk lever prices at P50/P70/P80.
3. **Shocks (`lib/shocks.py`)** — a *level* shift (scales magnitude, decision-inert) and a
   compounding *trend* shift (steepens the curve, can flip the recommendation).
4. **Claude edge (`app/agent.py`)** — parses one free-text curveball into a lever change and
   narrates the before→after diff. **No API key needed**: it degrades to a deterministic offline
   parser/narrator, so the demo runs fully offline.
5. **Backtest (`lib/impact.py`)** — leave-one-out hindcast: decide on the forecast, **pay on
   realized actuals**, compare to buy-as-you-go and a perfect-hindsight ceiling.

The Streamlit app (`app/`) wires these into live sliders + a chat box, with Plotly charts for the
forecast band, native-vs-recalibrated coverage, and the purchase schedule.

---

## Run it

Requires **Python 3.14** (the UI dependencies are pinned to cp314 wheels; the decision core is
pure stdlib and works on any 3.x).

```bash
git clone https://github.com/thedionysus/zero_one_hack_01.git
cd zero_one_hack_01

python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/streamlit run app/main.py        # opens http://localhost:8501
```

**Optional — enable Claude-powered chat:** create a `.env` file (gitignored) with:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Without it, the chat curveball still works via the deterministic offline fallback.

### Tests

```bash
.venv/bin/python -m unittest discover -s tests      # 163 tests
```

---

## What to try in the demo

- Pick a fertilizer in the sidebar; watch the recommendation, target month, and forward saving.
- Toggle the risk lever (neutral → cautious → averse) and see the plan bias toward buying earlier.
- Type a curveball in the chat: *"gas spiked, prices rising 25% a month"* — the trend lever moves,
  the plan re-solves, and the recommendation can flip to **BUY_NOW** with a narrated explanation.
- Compare the two-bar **coverage** chart: native vs. recalibrated 80% band.

---

## Project layout

```
app/        Streamlit UI, chat agent edge, charts, state  (UI deps)
lib/        decision core, recalibration, shocks, impact backtest, trust  (pure stdlib)
tests/      163 unit + integration tests
data/       Sybilion forecasts, hindcast trajectories, bake-off champions
docs/       design specs and plans
submission/ pitch deck + submission docs
```

See [`REPORT.md`](./REPORT.md) for results, honest evaluation, and what we'd do next.

---

## License

MIT — see [`LICENSE`](./LICENSE).
