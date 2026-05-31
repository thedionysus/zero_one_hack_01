# Keyword Optimization Engine — Engineering Spec v0.1

> Consolidates: the 7 whiteboard sketches, the meeting transcripts, the Sybilion docs (`sybilion_domain_knowledge.md`), and the real run (`sybilion_empirical_findings.md`).
> Goal of this doc: a buildable design, not a concept. Every non-obvious choice is anchored to evidence: **[run]** = observed in the real forecast, **[docs]** = Sybilion docs, **[mtg]** = meeting transcript.

---

## 1. What it is

A loop that, given a monthly target series' **title + description**, discovers the **keyword set (≤20) that minimizes forecast error** — then distils that loop into a small local model so future targets get near-optimal keywords in one forward pass.

```
{title, description}  ──►  Keyword Optimization Engine  ──►  {"keywords": [...]}  (optimal)
```

**Core thesis [mtg]:** keywords steer Sybilion's driver selection; better keywords → less driver noise → better forecast. It is **not an LLM wrapper** — the LLM only *proposes* keywords; quality is judged by Sybilion's **backtest**, not by the LLM.

**Why title+description is the context:** that's the human label of the series you already forecast — Sybilion's `timeseries_metadata = {title, description, keywords}` [docs]. You author it; you don't fetch it. The raw numeric series is *not* the context [mtg: "types won't be relevant"].

---

## 2. Ground-truth constraints (binding facts)

| Fact | Value | Source |
|---|---|---|
| Frequency | monthly only | [docs] |
| `keywords` | ≤ 20 items, each non-empty ≤ 255 bytes | [docs] |
| `title` / `description` | 20–511 / ≤ 2048 bytes | [docs] |
| `recency_factor` | 0.0–1.0 | [docs] |
| `filters.limit` (candidate cap) | 0–1000, default 1000 | [docs] |
| Horizon param | `soft_horizon` / `hard_horizon` (not `horizon`) | [run] |
| Full forecast cost | **€3.14** per run | [run] |
| Full forecast latency | **~10 min** per run | [run] |
| Drivers endpoint | **synchronous**, returns importance + direction, no job | [docs] |
| Usable score | **MAPE only** (`MASE`/`RMSSE` broken ~10⁷; `RMSE==MAE`) | [run] |
| `importance` scale | 0–100 | [run] |
| `direction` / `pearson` | signed, [−1, 1]; lag-indexed | [run] |
| Drivers returned vs used | 20 returned, **10 with importance>0** | [run] |

The cost/latency line is the single most design-shaping fact: **brute force is impossible** (100 sets ≈ €314 / ~17 h serial). Everything below is structured around minimizing full-forecast calls.

---

## 3. Objective function

Two scores: a **cheap proxy** for screening many sets, and the **true score** for the shortlist.

### 3.1 Cheap proxy `S(K)` — via `POST /api/v1/drivers` (sync)
For a keyword set `K` on target `T`, the endpoint returns drivers `D` with importance + direction.

```
used(K)  = { d ∈ D : importance_d > 0 }
M(K)     = Σ_{d ∈ used} importance_d          # "used importance mass", reward
W(K)     = |D| − |used(K)|                    # dead/wasted drivers, penalty  [run: 10/20 were dead]
C(K)     = |distinct macro categories in used(K)|   # coverage / diversity
S(K)     = M(K) − λ_w·W(K) + λ_c·C(K)         # MAXIMIZE   (λ_w, λ_c tunable; start λ_w=5, λ_c=10)
```
- **Sign is irrelevant to importance**: a negative-`direction` driver with high importance still counts as *used* [run: World Equities, dir −0.63, importance 45.86]. Do not penalize inversion — Sybilion already exploits it internally.
- `S(K)` is a **proxy**, not the truth. It must be validated against MAPE on a calibration set (§8, Phase 1).

### 3.2 True score — via `POST /api/v1/forecasts` (async, `backtest=true`)
```
score(K, T) = backtest_metrics.data["12m"].metrics.MAPE     # MINIMIZE
```
Baseline to beat for the robot target = **8.51% MAPE** with the current 20 keywords [run].

### 3.3 Selection rule
Propose `P` sets → screen all by `S` (cheap) → full-forecast the **top `m`** → pick `argmin MAPE`. `m` and the forecast budget `B` are the cost knobs (e.g. `m=3`, `B=10` ⇒ ≤ €31.40 per target).

---

## 4. Architecture — three tiers

```
┌─ TIER 0  Proposer (LLM) ───────────────────────────────────────────┐
│  in: title, description, past-attempts table                       │
│  ChatGPT/LLM, T=0.6  →  JSON {"keywords":[≤20]}        [mtg]        │
└───────────────┬────────────────────────────────────────────────────┘
                │  canonical-hash → cache lookup (skip if seen)  [sheet 6]
                ▼
┌─ TIER 1  Cheap screen (sync) ──────────────────────────────────────┐
│  POST /api/v1/drivers  →  S(K) = M − λ_w·W + λ_c·C                  │
│  ablation here (§6) to attribute/prune keywords                    │
│  rank candidates; keep top m                                        │
└───────────────┬────────────────────────────────────────────────────┘
                │  shortlist only (m sets)
                ▼
┌─ TIER 2  True score (async, €3.14/10min) ──────────────────────────┐
│  POST /api/v1/forecasts (backtest=true) → poll → MAPE_12m          │
│  record {attempt#, keywords, S, MAPE, cost}                        │
└───────────────┬────────────────────────────────────────────────────┘
                ▼
        update best; feed history to Tier 0; stop on budget/convergence
                ▼
   accumulate {title,description}→best_keywords across DIVERSE targets → distil (§9)
```

Mapping to the whiteboards: Tier 0 = sheets 5/7 (prompt → keywords JSON), Tier 1 = sheet 3 driver search made cheap, Tier 2 = sheet 5 evaluate/backtest, the cache spine = sheet 6, inverted-driver handling = sheet 4.

---

## 5. Cache & hash schema

**Hash (order-invariant) [sheet 6 / mtg "order doesn't matter"]:**
```
normalize(k) = lower(trim(collapse_whitespace(k)))
key = sha256( target_id + "|" + ",".join(sorted(normalize(k) for k in K)) )
```
Permutations `[A,D,C,B]` and `[A,B,C,D]` → identical key → cache hit → skip [mtg].

**Storage (PostgreSQL — single source of truth, persisted to disk [mtg]):**

```sql
-- cheap-tier results
CREATE TABLE driver_cache (
  key            text PRIMARY KEY,         -- canonical hash
  target_id      text NOT NULL,
  keywords       text[] NOT NULL,          -- sorted, normalized
  drivers        jsonb NOT NULL,           -- raw external-signals-style payload
  used_mass      double precision,         -- M(K)
  dead_count     int,                      -- W(K)
  coverage       int,                      -- C(K)
  screen_score   double precision,         -- S(K)
  created_at     timestamptz DEFAULT now()
);

-- expensive-tier results
CREATE TABLE forecast_cache (
  key            text PRIMARY KEY,         -- same canonical hash (target_id + keywords)
  target_id      text NOT NULL,
  keywords       text[] NOT NULL,
  job_id         text,
  mape_12m       double precision,         -- the objective
  artifacts_ref  jsonb,                    -- hrefs / local paths to the 5 artifacts
  eur_cents      int,                      -- realized cost  [run: 314]
  created_at     timestamptz DEFAULT now()
);

-- per-target optimization log (feeds the LLM's "past attempts")  [sheet 5]
CREATE TABLE attempts (
  target_id      text NOT NULL,
  attempt_no     int  NOT NULL,
  keywords       text[] NOT NULL,
  screen_score   double precision,
  mape_12m       double precision,         -- null until full-forecast scored
  created_at     timestamptz DEFAULT now(),
  PRIMARY KEY (target_id, attempt_no)
);
```
Both tiers check their cache before any API call. Reuse a stable `X-Request-ID` on Drivers to dedupe billing on retries [docs].

---

## 6. Ablation protocol (keyword → driver attribution)

Driver names are macro categories, not your keywords [run] — so attribution can't be read off; you knock keywords out and watch the result.

1. **Group ablation first** (cheap, few runs): drop whole clusters (e.g. the 8-keyword labor cluster) → re-screen on `/drivers` → Δ`S`.
2. **Individual ablation on survivors**: drop one keyword at a time → Δ`S`.
3. **Decision rule per keyword:**

| Effect on `S` (or MAPE) when removed | Meaning | Action |
|---|---|---|
| Drops a lot | earned a used driver | **keep** |
| ~No change | dead weight | **prune** |
| Improves | active noise | **remove** |

Run ablation on the **sync Drivers endpoint** (cheap); confirm only the final candidate set with one full forecast. This keeps a 20-keyword attribution under a couple of euros instead of ~€63.

---

## 7. Agent harness — loop contract

**Per-iteration state:** `{ target: {title, description}, history: attempts[], best: {keywords, mape} }`.

**Step contract:**
1. **Propose** — LLM(T=0.6) given `target` + `history` → `{"keywords":[≤20]}`. Validate (≤20, each ≤255 B, non-empty) before use.
2. **Hash & cache** — skip if key seen.
3. **Screen** — `/drivers` → `S(K)`; persist to `driver_cache` + `attempts`.
4. **Shortlist** — if `S(K)` in current top-`m`, queue for Tier 2.
5. **Score** — `/forecasts` backtest=true → `MAPE`; persist to `forecast_cache` + update `attempts.mape_12m`.
6. **Update** — refresh `best`; append to `history`.

**Stopping (any):** forecast budget `B` spent · no MAPE improvement in `k` consecutive scored sets · MAPE ≤ target. [mtg: minimize the score, loop with past-attempts context]

---

## 8. Diverse dataset (the training corpus)

**Why diverse [mtg]:** trained on one industry it only works for that industry; spread across sectors so the distilled model generalizes.

**Composition (target ≈ 10–100 series [mtg numbers]):** spread across
- sectors (manufacturing, retail/sales, energy, services, financial KPIs),
- shapes (trending, strongly seasonal, intermittent-demand, and at least a few **known inverse-driver** cases like the sunscreen↔raw-materials example [mtg]),
- regions/categories (vary `filters`).

**Per target, store:** `{title, description, series}` + the loop's converged `best_keywords` + `best_mape`. That triple `{title, description} → best_keywords` is the distillation training pair.

---

## 9. Distillation (efficiency endgame)

Once enough converged pairs are collected:

- **Input (standardized):** JSON `{title, description}` — *not* the time series [mtg].
- **Output:** JSON `{"keywords":[...]}`.
- **Model:** small open-source LLM (LLaMA-class, ~8 GB [mtg]) fine-tuned locally on the **Mac Studio M4 Max**.
- **Payoff:** one forward pass → near-optimal keywords, **zero per-query API cost**. This is why distillation is economically necessary given €3.14/run, not a nice-to-have.
- **Eval (held-out targets):** compare MAPE from distilled keywords vs. loop-optimized vs. no-keywords baseline. Success = distilled ≈ loop-optimized, both < baseline.

---

## 10. Build phases

| Phase | Deliverable | Cost guard |
|---|---|---|
| **0 · Probe** | One `/drivers` call for the robot target — confirm it returns the same importance/direction structure as `external_signals.json`; record billing | ~cents |
| **1 · Cheap loop** | Tier 0 + Tier 1 + cache on a single target; ablation; validate `S(K)` correlates with MAPE on ~5 full forecasts | ≤ €20 |
| **2 · Full objective** | Add Tier 2 + budget/convergence; beat 8.51% MAPE on the robot target | ≤ €30/target |
| **3 · Corpus** | Run the loop across the diverse dataset; collect `{context → best_keywords}` pairs | bounded by `B`×N |
| **4 · Distil** | Fine-tune local model; held-out eval | local only |

**First validating test [run]:** re-run the robot target with the **labor cluster pruned** (keep manufacturing / industrial-production / equities / energy terms). If MAPE drops below 8.51% and `dead_count` falls, the whole premise is confirmed for one full forecast (~€3).

---

## 11. Open items to verify (don't build on assumptions)

| Unknown | Why it matters | How to resolve |
|---|---|---|
| Does `/drivers` importance == forecast feature-selection importance? | If they diverge, `S(K)` is a weaker proxy | Phase 0 probe: compare `/drivers` output to this run's `external_signals.json` |
| Are `importance=0` drivers billed on `/drivers`? | Affects screening cost model | Phase 0 billing check |
| Lag domain (saw 0/1/6) | Bounds inverse/lead-lag logic | Inspect `/drivers` + OpenAPI |
| `soft_horizon` vs `hard_horizon` semantics | Correct request shape | Live OpenAPI |
| Does Sybilion already de-noise internally (feature selection to <100)? | The engine optimizes the *input* to that step, not the step itself — keep scope on keywords | [mtg] confirms internal FS exists; engine sits upstream |

---

## 12. Scope guard

The engine optimizes **one input** (keywords) to an existing forecasting service. It does **not** rebuild forecasting, feature selection, or driver retrieval — Sybilion owns those. The only levers are `keywords`, `recency_factor`, `filters`. Stay there.
