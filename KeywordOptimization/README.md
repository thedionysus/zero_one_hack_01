# kwopt — Keyword Optimization Engine (v0.2)

Finds the keyword set that minimizes a Sybilion forecast's MAPE for a monthly target, then **uses its
own accumulated results** to propose near-optimal keywords for new targets. REST only.

```
{title, description}  ──►  kwopt  ──►  {"keywords": [...]}  (lowest MAPE)  +  critical driver names
```

## Pipeline
1. **Baseline** — a no-keyword (similarity-only) forecast = the floor; everything is measured as **lift** vs this.
2. **Propose** — static seeds + ablation, OR LLM (T=0.6), OR **experience** (own past best results).
3. **Cheap screen** — `POST /drivers`: `S(K) = used_mass − λ_w·dead + λ_c·coverage (+ λ_s·stability + λ_i·inverted)`.
4. **Score** — top `m` sets full-forecast (`POST /forecasts`, backtest=true) **in parallel**, ranked by 12m MAPE.
5. **Learn** — best `{title,description}→keywords` pairs accumulate; `experience`/distillation reuse them.

Order-invariant cache means no set runs twice. Inverted drivers are kept (and optionally rewarded), never penalized.

## Credit is unlimited → the guard is time & concurrency
`Budget` caps run count, **concurrency**, and optional wall-time (euros tracked for info only).
Credit-rich shortcuts:
```bash
KWOPT_SKIP_SCREEN=1 KWOPT_CONCURRENCY=6 KWOPT_MAX_FORECASTS=40 python -m kwopt.cli optimize
```

## Commands
```bash
export SYBILION_API_TOKEN=sk_...
python -m kwopt.cli probe --set labor_aware --external baseline_artifacts/external_signals.json  # Phase 0
python -m kwopt.cli screen
python -m kwopt.cli ablate --set labor_aware
python -m kwopt.cli optimize --proposer static --rounds 2
python -m kwopt.cli harvest  --manifest targets.json --out harvest.json   # diverse multi-target
python -m kwopt.cli export    --manifest targets.json --out pairs.json     # engine's own pairs
python -m kwopt.cli optimize  --proposer experience --pairs pairs.json     # uses itself
python -m kwopt.cli eval      --manifest targets.json --pairs pairs.json   # leave-one-out lift
```

## Layout
```
kwopt/
  config.py schemas.py
  clients/sybilion.py  llm.py(T=0.6)
  core/hashing.py  scoring.py(S(K), stability, robust_drivers, mape_12m)  validate.py
  cache/store.py            sqlite, thread-safe (parallel-ready); Postgres swap = this file
  agent/proposer.py         Static | LLM | Experience(self-use)
  agent/budget.py           time/concurrency guard
  agent/ablation.py  orchestrator.py(baseline+lift, parallel, robust, driver-list)
  corpus/targets.py  harvest.py        diverse dataset -> accumulated best results
  distill/export.py  eval.py  train.py(stub)   "uses itself": few-shot now, fine-tune later
  cli.py
```

## Scoring knobs (env)
`KWOPT_LAM_W` dead penalty · `KWOPT_LAM_C` coverage reward · `KWOPT_LAM_S` stability reward (default 0)
· `KWOPT_LAM_I` inverted-driver reward (default 0) · `KWOPT_CONCURRENCY` · `KWOPT_MAX_FORECASTS`
· `KWOPT_SKIP_SCREEN` · `KWOPT_TARGET_MAPE` · `KWOPT_PATIENCE` · `KWOPT_PROPOSER=static|llm|experience`.



## VERIFIED against the live API (2026-05)
The two layers return DIFFERENT data — confirmed by a live probe:
- `/drivers` (cheap, sync) -> `data.drivers[]` = `{driver_name, score (0-1 relevance), source}`. No importance/direction.
- forecast `external_signals.json` -> importance (0-100), direction, correlation (post feature-selection).

So the cheap screen ranks keyword sets by candidate **relevance + diversity** (a heuristic pre-filter),
while **importance, inversion, dead-drivers, and MAPE come only from a full forecast** (the truth).
With unlimited credit, `KWOPT_SKIP_SCREEN=1` is a valid strategy: forecast many sets in parallel and skip the weak screen.

## v0.2 changes (concept-audit fixes)
- LLM temperature pinned to **0.6** (meeting spec).
- **No-keyword baseline + keyword lift** (interest-rates-vs-sunscreen insight).
- Driver **stability** (sheet 1) parsed and available as a scoring term.
- Important **inverted drivers** optionally rewarded, never penalized (sheet 4).
- **Robust drivers** recurring across sets surfaced (noise-reduction signal).
- Output includes the winner's **critical driver names**.
- **Experience proposer + corpus harvest + distill export/eval**: the engine uses its own results.
- **Parallel forecasts** + time/concurrency budget (unlimited credit).

## Still future
`distill/train.py` (true local fine-tune on Mac Studio) — ExperienceProposer covers self-use until then.
Co-optimizing `recency_factor`/`filters` (cache already keys on them). Alerts/daily are out of scope (monthly-only API).
