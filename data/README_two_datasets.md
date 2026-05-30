# Two datasets (urea) — units aligned to USD/kg

Both datasets are now expressed in **USD per kilogram**. Urea is the shared product.

---

## Dataset 1 — global benchmark (forecasting layer)
**File:** `dataset1_worldbank_benchmark_USDperKG.csv`
- Source: World Bank "Pink Sheet" benchmark prices (via IndexMundi). Free / open.
- Coverage: monthly, Apr 1996 – Mar 2026.
- Products: Urea, DAP, TSP, Rock phosphate, Potassium chloride (MOP).
- Columns: `product, nutrient_group, date, price_usd_per_tonne, price_usd_per_kg`
  (kept both units; `price_usd_per_kg = price_usd_per_tonne / 1000`).
- Nature: **nominal** wholesale **FOB export-hub** price (e.g. urea FOB Black Sea).

## Dataset 2 — local market prices (sourcing layer)
**File:** `dataset2_ssa_urea_USDperKG.csv`
- Source: Bonilla Cedrez et al. (2019), Harvard Dataverse doi:10.7910/DVN/E0EHLO.
  (License bars redistribution outside Dataverse — keep this copy internal.)
- Coverage: annual, 2010–2018, 18 West & East African countries, ~878 towns.
- Columns: `source, year, fert_type, country, ISO, Town, price_usd_per_kg_ppp,
  rel_price, longitude, latitude, distPort, nat_avg`
- Price column: `price_usd_per_kg_ppp`.
- Nature: **PPP-adjusted** local **farm-gate retail** price.

---

## Important: units match, but levels still differ — by design
After the kg/kg fix, Dataset 1 urea sits around 0.06–0.93 USD/kg while Dataset 2 sits
around 1.0–1.5 USD/kg. That gap is real economics, not a unit error, for two reasons:

1. **Wholesale vs retail:** Dataset 1 is the FOB export benchmark; Dataset 2 is the price
   a farmer pays locally (adds shipping, inland transport, margins, taxes). Retail > FOB.
2. **Nominal vs PPP:** Dataset 1 is nominal market USD; Dataset 2 is PPP-adjusted USD
   (purchasing-power dollars). These are different dollar concepts.

So use Dataset 2's prices for **relative cross-country ranking** ("which market is cheaper")
and Dataset 1 for the **global time trend** — don't compare their absolute levels directly
without a nominal/PPP and retail/FOB adjustment.
