# Data Engineering: Fertilizer Datasets — Design Spec

**Date:** 2026-05-30
**Status:** Approved (pending user review of this doc)
**Scope:** Prepare two raw datasets into analysis-ready form. No forecasting, ranking, or cost modeling yet.

---

## 1. Purpose

Two raw datasets must be made analysis-ready for downstream decisions ("which fertilizers to stock up on, from which country to buy"):

- **Dataset 1** (`data/dataset1_worldbank_benchmark_USDperKG.csv`) → **forecasting layer**. World Bank Pink Sheet benchmark, monthly Apr 1996–Mar 2026, 5 fertilizers. Feeds the Sybilion MCP forecaster per product.
- **Dataset 2** (`data/dataset2_ssa_urea_USDperKG.csv`) → **sourcing layer**. Bonilla Cedrez et al. (2019) farm-gate urea prices, annual 2010–2018, 18 SSA countries, ~878 towns. Feeds cross-country price comparison.

This step **only** produces clean, validated, reshaped files. Out of scope: forecasting calls, cross-country ranking logic, shipping/import-cost modeling, nominal↔PPP / FOB↔retail reconciliation.

## 2. Runtime constraints

- **Pure stdlib Python 3.14 only.** Verified MISSING: `pandas`, `numpy`, `statistics`, `pip`. Available: `json`, `csv`, `datetime`. All math (median, mean, percentile, std) hand-rolled.
- No network except the Sybilion MCP dry-run validator.

## 3. Architecture (Approach A — small focused modules)

```
lib/ts_utils.py          # pure functions, fully unit-tested (TDD)
prepare_dataset1.py      # orchestration: dataset1 → forecasting-ready artifacts
prepare_dataset2.py      # orchestration: dataset2 → sourcing-ready artifacts
validate_processed.py    # structural asserts + Sybilion MCP dry-run
tests/                   # unittest suite for ts_utils
docs/superpowers/specs/  # this spec
data/CITATIONS.md        # verbatim source citations
```

`lib/ts_utils.py` pure functions (each single-purpose, testable in isolation):
`slugify`, `mean`, `median`, `percentile`, `linear_interpolate_gap`, `detect_gaps`,
`detect_outlier_jumps`, `detect_flat_tail`, `collapse_duplicate_towns`, `flag_low_price`.

Orchestration scripts read raw CSVs, call `ts_utils`, write to `data/processed/`. Raw CSVs are never mutated.

## 4. Output layout

```
data/processed/
  dataset1/
    urea.json  dap.json  tsp.json  phosphate-rock.json  mop.json   # Sybilion-ready {YYYY-MM-01: float}
    dataset1_quality.csv          # product, data_quality(ok|review), flags(;-joined)
    data_quality_flags.json       # detailed per-product evidence
  dataset2/
    urea_country_year.csv         # country×year median+mean prices, quality cols
    urea_country_summary.csv      # recency-aware one-row-per-country, quality cols
    dataset2_towns_geo.csv        # raw cleaned town geo passthrough (no aggregation)
    data_quality_flags.json       # detailed evidence
```

## 5. Dataset 1 — forecasting layer

### 5.1 Per-product Sybilion series (`<slug>.json`)
- One file per product (urea, dap, tsp, phosphate-rock, mop).
- Format: `{"1996-04-01": 0.21075, ...}` — month-aligned `YYYY-MM-DD` keys, chronological, **no gaps**, finite floats.
- **Units:** `price_usd_per_kg = price_usd_per_tonne / 1000` recomputed at **full float precision**. The CSV's pre-rounded `price_usd_per_kg` (4 dp) is ignored.
- **Gap fill:** Phosphate rock is missing **2023-11**. Fill by **linear interpolation** between 2023-10 and 2023-12. (The only gap across all 5 products.)

### 5.2 Anomaly policy — keep raw, flag, decisions must consume flags
No values are altered except the mandatory gap-fill. Anomalies recorded both as row-level columns (`dataset1_quality.csv`) and detailed evidence (`data_quality_flags.json`).

Detection rules:
- **Outlier MoM jump:** flag any month where `|MoM %| > max(40%, p99 of that product's own historical |MoM%|)`. Hybrid: each fertilizer judged against its own volatility, with a hard 40% floor. (Catches Urea 2026-03 +54%, MOP historical +255%; ignores ±10% noise.)
- **Flat-tail:** flag when the **last ≥4 consecutive months are bit-identical** (catches Phosphate rock's 8× 152.5).
- **Interpolated gap:** flag the filled month.
- **Stale-latest-data:** data ends 2026-03, today 2026-05 → record a `stale_latest_data` note. The pipeline does **not** silently decide the forecast-time stale handling (supply current-month value vs extend horizon vs accept) — that is deferred to the forecasting step.

`dataset1_quality.csv` columns: `product, data_quality, flags`. `data_quality = review` if any flag present, else `ok`. Phosphate rock will be `review / stale_flat_tail;interpolated_gap`.

All 5 series are generated regardless of flags (no special-casing the pipeline); Phosphate rock's degenerate flat tail is surfaced via its `review` status so forecasting treats it as low-confidence.

## 6. Dataset 2 — sourcing layer

### 6.0 Two mixed sources (discovered during execution — REVISED)
The raw file is **not** a single source. The `source` column holds two:
- **`Afr`** — 1,433 rows, 401 **named towns**, median 1.26 USD/kg PPP. The Bonilla Cedrez farm-gate retail data the README documents.
- **`LSMS`** — 4,793 rows, **blank `Town`**, median 1.16, present in only 11 of 131 country-years. Living Standards Measurement Study household-survey prices (undocumented in the README). **Each LSMS row carries full geo** (longitude/latitude/distPort, 4793/4793).

**Decision (user-approved):** include **both** sources as **independent observations**. Rationale: the dataset's own `nat_avg` matches the all-rows median (|diff| 0.0013) far better than named-only (0.0124), i.e. the curators' national average already includes LSMS. The earlier "46 duplicate (country,year,town)" count was an artifact of treating every blank-`Town` LSMS row as one duplicated town; only **35 genuine named-town duplicate groups (36 extra rows)** exist.

### 6.1 Cleaning (applied before any rollup)
- **Split by town label:** named-town rows vs blank-town (LSMS) rows.
- **Deduplicate named towns only:** average-collapse the 35 genuine `(ISO, year, Town)` duplicate groups (36 extra rows) into one observation each. Blank-town LSMS rows are **never** collapsed — each is an independent observation. Net: 6226 − 36 = **6190** cleaned observations (1,397 named + 4,793 LSMS). Log collapsed named-town keys in the sidecar.
- **Low-price flag:** prices below **0.10 USD/kg PPP floor** (min observed 0.01 — implausible for urea) are **flagged, not dropped**. Logged per observation.
- **Standardize:** trim/normalize country & town casing. Join key is **ISO** (verified 1:1 with country name; sidesteps the `Cote d'Ivoire` apostrophe).
- Prices verified: 0 zero/negative/empty.

### 6.2 `urea_country_year.csv` (one row per country×year)
Columns: `ISO, country, year, median_price_usd_per_kg_ppp, mean_price, obs_count, n_afr_obs, n_lsms_obs, flagged_low_price_obs_count, data_quality`.
- Aggregated over **all 6190 observations** (named + LSMS), reproducing the dataset's own `nat_avg`. **Median** is the primary statistic (robust; verified ≈ `nat_avg`, avg |diff| 0.0013). **Mean** retained for context.
- `n_afr_obs` / `n_lsms_obs` give the per-source breakdown so the decision layer can see how much of a country-year is household-survey vs retail.
- `data_quality = review` when `flagged_low_price_obs_count > 0` **or** `obs_count < 3`, else `ok`.
- 131 country-years. Unbalanced panel preserved — no fabricated years.

### 6.3 `urea_country_summary.csv` (recency-aware, one row per country)
Columns: `ISO, country, latest_year, latest_year_price, mean_price_all_years, years_covered, data_quality`.
- `latest_year_price` = median of the most recent available year (the recency-aligned comparison value).
- `data_quality = review` when `years_covered < 3` **or** `latest_year < 2016` (stale coverage), else `ok`.
- Rationale: the panel is unbalanced in recency (Niger ends 2013, Rwanda 2015–2018). Ranking on `latest_year_price` while *seeing* the recency flag prevents comparing a 2013 price against a 2018 price.

### 6.4 `dataset2_towns_geo.csv` (raw geo passthrough)
Columns: `source, ISO, country, year, Town, longitude, latitude, distPort, price_usd_per_kg_ppp`.
- All **6190** cleaned observations (named `Afr` + blank-town `LSMS`); both carry full geo, so both are useful for the future shipping work. `source` column distinguishes them; `Town` is blank for LSMS rows.
- Cleaned/deduped (named-town dups collapsed), **not aggregated**. Geo engineering (port mapping, inland haul, freight model) is deferred to the future shipping-cost work — no premature country-level aggregation.

## 7. Validation (`validate_processed.py`)
- **Structural asserts (local):** row counts, no nulls in key columns, monotonic & gapless dates (dataset1), plausible value ranges.
- **Sybilion dry-run:** call `mcp__sybilion__validate_forecast_data` on each of the 5 series. Free (no credits, no forecast). Payload: `soft_horizon = 12` (strongest proof — pass at 12 ⇒ pass at all; aligns with 6–12 month procurement runway), `frequency = monthly`, `pipeline_version = v1`, `accept_stale_latest_data = true` (structural validation only; documented; does not commit forecasting to accept stale).

## 8. Testing
- **TDD** the pure functions in `lib/ts_utils.py` (RED→GREEN), `unittest`, target ≥80% coverage of that module.
- **Integration smoke** for `prepare_dataset1.py` / `prepare_dataset2.py`: run end-to-end on the real CSVs, assert output row counts, no nulls in key cols, monotonic dates, value ranges. No mocked MCP / no CSV fixtures for orchestration.

## 9. Licensing & attribution
- Dataset 2 is license-restricted (Harvard Dataverse, bars redistribution outside Dataverse). Per user decision: **commit both raw and derived files, mitigate with proper attribution.**
- `data/CITATIONS.md` carries verbatim citations: Bonilla Cedrez et al. (2019), DOI `10.7910/DVN/E0EHLO` (fetched verbatim from the Dataverse page during implementation); World Bank Pink Sheet / IndexMundi for dataset 1.

## 10. Decision ledger (grill outcomes)
| # | Decision | Resolution |
|---|----------|-----------|
| 0 | Output scope | Analysis-ready files only |
| 1 | Stale-data dry-run | `accept_stale_latest_data: true`, structural only; real stale decision deferred |
| 2 | Duplicate town-years (46) | Average-collapse before rollup; log |
| 3 | Low prices (min 0.01) | Flag below 0.10 floor, keep raw; flags feed decisions |
| 4 | Flag delivery | Row-level columns + detailed sidecar JSON |
| 5 | License/git | Commit both, add verbatim citations |
| 6 | Units | Full-precision recomputed USD/kg |
| 7 | Phosphate rock | Generate all 5, flag `review / stale_flat_tail` |
| 8 | Country summary | Recency-aware; `review` if `years_covered<3` or `latest_year<2016` |
| 9 | Geo | Defer aggregation; raw town passthrough |
| 10 | Testing | TDD pure functions; integration-smoke scripts |
| 11 | Layout | `data/processed/{dataset1,dataset2}/…`; drop long CSV |
| 12 | Validation horizon | Dry-run at `soft_horizon = 12` |
| 13 | Thresholds | Outlier `|MoM%| > max(40%, p99)`; flat-tail last ≥4 identical |
