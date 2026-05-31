# kwopt — Original Design Plan *(as conceived, pre-build)*
### A keyword-optimization engine for the Sybilion forecast API

*This is the plan we wrote **before** building and testing. It rests on one central premise — that keyword choice steers Sybilion's driver selection and therefore its forecast accuracy. The findings report documents what happened when we put that premise to the test.*

---

## Aim

Given any monthly time series (with a title + description), automatically find the **keyword set that minimizes Sybilion's 12-month backtest MAPE** — and then have the engine **"use itself"**: reuse its own past wins to propose near-optimal keywords for new series in a single pass, eventually via a small **local distilled model** running on Heimyo's on-prem hardware.

It is explicitly **not an LLM wrapper.** An LLM only *proposes* candidate keyword sets; their quality is judged solely by Sybilion's backtest MAPE — the ground truth.

## Central premise *(the assumption everything rests on)*

> **Keyword choice → which drivers Sybilion attaches → backtest MAPE.**
>
> If we can find the keywords that surface the *right* drivers, we minimize forecast error. The entire optimization-and-distillation stack is built on this causal chain being real and steerable.

## How Sybilion works *(our model of it)*

Sybilion builds a driver pool from **three searches**, then fits and backtests:

1. **Similarity-TS** — finds catalog series with similar history (needs *no* keywords).
2. **Regex** — matches over the metadata (title / description / keywords).
3. **Semantic** — embeds the metadata (title / description / keywords / origin).

→ ~1,000-candidate driver pool → **feature selection** to <100 → model fit → **backtest** (MAPE / MASE / RMSSE).

Keywords feed searches **2 and 3** — so keywords were our intended lever on driver selection.

## The optimization loop

| Step | What | Cost |
|---|---|---|
| 1. Propose | generate candidate keyword sets (static seeds / LLM / experience) | free |
| 2. Screen `S(K)` | rank sets via the cheap `/drivers` endpoint (relevance mass + category & source diversity) | cheap (sync) |
| 3. Shortlist | keep the top-N sets | free |
| 4. Forecast | full Sybilion forecast on the shortlist, **in parallel** → 12m MAPE | expensive (~€3 each) |
| 5. Select | keep the best set by **lift vs the no-keyword baseline** | — |
| 6. Iterate | feed winners back, repeat | — |

Two-tier by design: the **cheap `/drivers` screen** is a *proxy* used to avoid paying for bad keyword sets; the **full-forecast 12m MAPE** is the *true objective*. Every set is cached under an **order-invariant key** (`{a,b}` == `{b,a}`) so nothing is ever re-run.

## The engine

- **Proposers:** `static` (hand-written seed sets), `llm` (model invents new sets), `experience` (reuse the engine's own past wins).
- **Core:** order-invariant cache (sqlite), driver scoring (relevance from `/drivers` vs importance from a forecast's `external_signals`), ablation (which keywords actually earn their drivers), budget control, parallel orchestrator.
- **CLI verbs:** `probe` · `screen` · `optimize` · `ablate` · `harvest` · `export` · `eval`.

## The 5-phase roadmap

| Phase | Goal | Output |
|---|---|---|
| **0 — Probe** | verify the cheap `/drivers` screen agrees with full-forecast importance | trust the screen, or recalibrate it |
| **1 — Cheap loop** | wire screening + cache on one target (no forecasts yet) | a working screen |
| **2 — Full objective** | real loop on one target: baseline → screen → forecast → best keywords | the first lift-vs-baseline number |
| **3 — Corpus / diversity** | run the loop across many targets in different industries (`harvest`), accumulating `{series → winning keywords}` | a corpus that generalizes beyond one target |
| **4 — Distillation ("uses itself")** | reuse past wins on new targets (`experience` proposer → fine-tuned local model) | new target → good keywords in one pass, no search |

## The endgame — "the engine uses itself"

Phase 4 is the point of the whole build: a growing corpus of *(series features → winning keyword set)* lets the engine propose near-optimal keywords for an unseen series **without any search or LLM call** — eventually a small local model on Heimyo's on-prem Mac Studio. New series in → good keywords out, instantly and for free.

---

## What this plan set out to validate

Everything above is **downstream of the central premise**: that *which* keywords you choose changes forecast accuracy. Phases 0–2 were deliberately structured to test that premise **cheaply, before** committing to the expensive Phase 3–4 distillation.

→ *See `kwopt_findings.md` for what the testing actually revealed.*
