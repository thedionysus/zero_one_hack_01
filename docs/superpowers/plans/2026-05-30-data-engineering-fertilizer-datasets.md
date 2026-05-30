# Fertilizer Datasets Data-Engineering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the two raw fertilizer CSVs into analysis-ready artifacts — 5 Sybilion-ready monthly series (dataset 1) and cleaned country-level urea price tables with quality flags (dataset 2).

**Architecture:** Pure-stdlib Python 3.14. A single tested utility module (`lib/ts_utils.py`) holds all pure transformation functions; three orchestration scripts (`prepare_dataset1.py`, `prepare_dataset2.py`, `validate_processed.py`) read raw CSVs and write to `data/processed/`. Raw CSVs are never mutated. Flags are written both as row-level columns (so downstream decisions must consume them) and detailed JSON sidecars.

**Tech Stack:** Python 3.14 stdlib only (`csv`, `json`, `unittest`) — verified MISSING: `pandas`, `numpy`, `statistics`, `pip`. All math hand-rolled. Sybilion MCP (`mcp__sybilion__validate_forecast_data`) for a free structural dry-run.

**Spec:** `docs/superpowers/specs/2026-05-30-data-engineering-fertilizer-datasets-design.md`

---

## File Structure

| File | Responsibility |
|------|----------------|
| `lib/__init__.py` | Make `lib` importable. |
| `lib/ts_utils.py` | All pure functions: date math, stats, gap fill, anomaly detection, dedup, low-price flag. |
| `tests/__init__.py` | Make `tests` a package. |
| `tests/test_ts_utils.py` | `unittest` suite for every `ts_utils` function. |
| `tests/test_integration.py` | End-to-end smoke asserts after the prepare scripts run. |
| `prepare_dataset1.py` | dataset1 → `data/processed/dataset1/` (5 JSON series + quality files). |
| `prepare_dataset2.py` | dataset2 → `data/processed/dataset2/` (country tables + town geo + sidecar). |
| `validate_processed.py` | Local structural asserts over processed outputs. |
| `data/CITATIONS.md` | Verbatim source citations. |

**Test command (no pytest):** `python3 -m unittest discover -s tests -v` (run from repo root).

---

### Task 1: Scaffolding

**Files:**
- Create: `lib/__init__.py` (empty)
- Create: `tests/__init__.py` (empty)
- Create: `data/processed/.gitkeep` (empty)

- [ ] **Step 1: Create package + output directories**

```bash
mkdir -p lib tests data/processed/dataset1 data/processed/dataset2
touch lib/__init__.py tests/__init__.py data/processed/.gitkeep
```

- [ ] **Step 2: Verify import path works**

Run: `python3 -c "import lib; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add lib/__init__.py tests/__init__.py data/processed/.gitkeep
git commit -m "chore: scaffold lib/tests/processed dirs for data engineering"
```

---

### Task 2: Date helpers (`month_index`, `index_to_month`)

**Files:**
- Create: `lib/ts_utils.py`
- Test: `tests/test_ts_utils.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ts_utils.py
import unittest
from lib import ts_utils


class TestDateHelpers(unittest.TestCase):
    def test_month_index_is_monotonic_by_month(self):
        self.assertEqual(
            ts_utils.month_index("2024-02-01") - ts_utils.month_index("2024-01-01"), 1
        )
        self.assertEqual(
            ts_utils.month_index("2024-01-01") - ts_utils.month_index("2023-12-01"), 1
        )

    def test_index_to_month_round_trips(self):
        for d in ["1996-04-01", "2023-11-01", "2026-03-01"]:
            self.assertEqual(ts_utils.index_to_month(ts_utils.month_index(d)), d)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_ts_utils.TestDateHelpers -v`
Expected: FAIL — `ModuleNotFoundError`/`AttributeError: module 'lib.ts_utils' has no attribute 'month_index'`.

- [ ] **Step 3: Write minimal implementation**

```python
# lib/ts_utils.py
"""Pure stdlib transformation helpers for fertilizer dataset engineering."""


def month_index(date_str):
    """'YYYY-MM-DD' -> integer count of months since year 0 (month-aligned)."""
    year, month, _day = date_str.split("-")
    return int(year) * 12 + (int(month) - 1)


def index_to_month(idx):
    """Inverse of month_index -> 'YYYY-MM-01'."""
    year, month0 = divmod(idx, 12)
    return f"{year:04d}-{month0 + 1:02d}-01"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_ts_utils.TestDateHelpers -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/ts_utils.py tests/test_ts_utils.py
git commit -m "feat: add month_index/index_to_month date helpers"
```

---

### Task 3: Stats helpers (`mean`, `median`, `percentile`)

**Files:**
- Modify: `lib/ts_utils.py`
- Test: `tests/test_ts_utils.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_ts_utils.py`)

```python
class TestStats(unittest.TestCase):
    def test_mean(self):
        self.assertAlmostEqual(ts_utils.mean([1.0, 2.0, 3.0]), 2.0)

    def test_median_odd(self):
        self.assertEqual(ts_utils.median([3, 1, 2]), 2)

    def test_median_even(self):
        self.assertEqual(ts_utils.median([1, 2, 3, 4]), 2.5)

    def test_percentile_nearest_rank(self):
        data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        self.assertEqual(ts_utils.percentile(data, 100), 10)
        self.assertEqual(ts_utils.percentile(data, 50), 5)
        self.assertEqual(ts_utils.percentile([42.0], 99), 42.0)

    def test_percentile_empty_raises(self):
        with self.assertRaises(ValueError):
            ts_utils.percentile([], 99)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_ts_utils.TestStats -v`
Expected: FAIL — `AttributeError: ... has no attribute 'mean'`.

- [ ] **Step 3: Write minimal implementation** (append to `lib/ts_utils.py`)

```python
def mean(values):
    values = list(values)
    return sum(values) / len(values)


def median(values):
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def percentile(values, p):
    """Nearest-rank percentile. p in [0, 100]. Raises ValueError on empty input."""
    s = sorted(values)
    if not s:
        raise ValueError("percentile() of empty sequence")
    if len(s) == 1:
        return s[0]
    k = (p / 100.0) * len(s)
    rank = int(k)
    if rank < k:  # ceil without math module
        rank += 1
    rank = max(1, min(rank, len(s)))
    return s[rank - 1]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_ts_utils.TestStats -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/ts_utils.py tests/test_ts_utils.py
git commit -m "feat: add mean/median/percentile stats helpers"
```

---

### Task 4: `linear_interpolate_gap`

**Files:**
- Modify: `lib/ts_utils.py`
- Test: `tests/test_ts_utils.py`

- [ ] **Step 1: Write the failing test** (append)

```python
class TestInterpolate(unittest.TestCase):
    def test_midpoint_for_single_interior_gap(self):
        series = {"2023-10-01": 100.0, "2023-12-01": 200.0}
        self.assertAlmostEqual(
            ts_utils.linear_interpolate_gap(series, "2023-11-01"), 150.0
        )

    def test_weighted_for_wider_gap(self):
        # gap one month after prev (Feb) of a Jan..Apr span
        series = {"2024-01-01": 0.0, "2024-04-01": 30.0}
        self.assertAlmostEqual(
            ts_utils.linear_interpolate_gap(series, "2024-02-01"), 10.0
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_ts_utils.TestInterpolate -v`
Expected: FAIL — `AttributeError: ... 'linear_interpolate_gap'`.

- [ ] **Step 3: Write minimal implementation** (append)

```python
def linear_interpolate_gap(series, missing_date):
    """Linear value at missing_date from nearest present neighbours on each side.

    series: {'YYYY-MM-DD': float}. missing_date must lie strictly between an
    earlier and a later present key.
    """
    target = month_index(missing_date)
    before = [(month_index(d), v) for d, v in series.items() if month_index(d) < target]
    after = [(month_index(d), v) for d, v in series.items() if month_index(d) > target]
    if not before or not after:
        raise ValueError(f"cannot interpolate {missing_date}: missing a side neighbour")
    pi, pv = max(before)
    ni, nv = min(after)
    frac = (target - pi) / (ni - pi)
    return pv + (nv - pv) * frac
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_ts_utils.TestInterpolate -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/ts_utils.py tests/test_ts_utils.py
git commit -m "feat: add linear_interpolate_gap"
```

---

### Task 5: `detect_gaps`

**Files:**
- Modify: `lib/ts_utils.py`
- Test: `tests/test_ts_utils.py`

- [ ] **Step 1: Write the failing test** (append)

```python
class TestDetectGaps(unittest.TestCase):
    def test_finds_single_interior_gap(self):
        dates = ["2023-10-01", "2023-12-01", "2024-01-01"]
        self.assertEqual(ts_utils.detect_gaps(dates), ["2023-11-01"])

    def test_no_gaps_returns_empty(self):
        dates = ["2024-01-01", "2024-02-01", "2024-03-01"]
        self.assertEqual(ts_utils.detect_gaps(dates), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_ts_utils.TestDetectGaps -v`
Expected: FAIL — `AttributeError: ... 'detect_gaps'`.

- [ ] **Step 3: Write minimal implementation** (append)

```python
def detect_gaps(dates):
    """Return month-aligned 'YYYY-MM-01' strings missing between min and max."""
    if not dates:
        return []
    idxs = sorted(month_index(d) for d in dates)
    present = set(idxs)
    return [index_to_month(i) for i in range(idxs[0], idxs[-1] + 1) if i not in present]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_ts_utils.TestDetectGaps -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/ts_utils.py tests/test_ts_utils.py
git commit -m "feat: add detect_gaps"
```

---

### Task 6: `detect_outlier_jumps`

**Files:**
- Modify: `lib/ts_utils.py`
- Test: `tests/test_ts_utils.py`

Rule: flag any month whose `|MoM %|` exceeds `max(floor_pct, percentile(historical |MoM%|, 99))`.

- [ ] **Step 1: Write the failing test** (append)

```python
class TestOutlierJumps(unittest.TestCase):
    def test_flags_large_jump_over_floor(self):
        # flat ~1% MoM noise then a +54% spike on the last month
        series = {}
        val = 100.0
        for i in range(12):
            series[ts_utils.index_to_month(24000 + i)] = val
            val *= 1.01
        spike_date = ts_utils.index_to_month(24000 + 12)
        series[spike_date] = val * 1.54
        flagged = ts_utils.detect_outlier_jumps(series, floor_pct=40.0)
        self.assertIn(spike_date, flagged)

    def test_no_flags_for_calm_series(self):
        series = {ts_utils.index_to_month(24000 + i): 100.0 + i for i in range(12)}
        self.assertEqual(ts_utils.detect_outlier_jumps(series, floor_pct=40.0), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_ts_utils.TestOutlierJumps -v`
Expected: FAIL — `AttributeError: ... 'detect_outlier_jumps'`.

- [ ] **Step 3: Write minimal implementation** (append)

```python
def detect_outlier_jumps(series, floor_pct=40.0):
    """Flag dates whose |month-over-month %| exceeds max(floor_pct, p99 of history).

    series: {'YYYY-MM-DD': float}. Returns sorted list of flagged date keys.
    """
    ordered = sorted(series.items(), key=lambda kv: month_index(kv[0]))
    moms = []  # (date, abs_pct)
    for i in range(1, len(ordered)):
        prev_v = ordered[i - 1][1]
        if prev_v == 0:
            continue
        pct = abs((ordered[i][1] / prev_v - 1.0) * 100.0)
        moms.append((ordered[i][0], pct))
    if not moms:
        return []
    p99 = percentile([m[1] for m in moms], 99)
    threshold = max(floor_pct, p99)
    return sorted(d for d, pct in moms if pct > threshold)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_ts_utils.TestOutlierJumps -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/ts_utils.py tests/test_ts_utils.py
git commit -m "feat: add detect_outlier_jumps"
```

---

### Task 7: `detect_flat_tail`

**Files:**
- Modify: `lib/ts_utils.py`
- Test: `tests/test_ts_utils.py`

Rule: return the length of the trailing run of bit-identical values if `>= min_run`, else 0.

- [ ] **Step 1: Write the failing test** (append)

```python
class TestFlatTail(unittest.TestCase):
    def test_flags_run_of_four_or_more(self):
        series = {ts_utils.index_to_month(24000 + i): v
                  for i, v in enumerate([1.0, 2.0, 3.0, 5.0, 5.0, 5.0, 5.0])}
        self.assertEqual(ts_utils.detect_flat_tail(series, min_run=4), 4)

    def test_no_flag_for_short_plateau(self):
        series = {ts_utils.index_to_month(24000 + i): v
                  for i, v in enumerate([1.0, 2.0, 5.0, 5.0])}
        self.assertEqual(ts_utils.detect_flat_tail(series, min_run=4), 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_ts_utils.TestFlatTail -v`
Expected: FAIL — `AttributeError: ... 'detect_flat_tail'`.

- [ ] **Step 3: Write minimal implementation** (append)

```python
def detect_flat_tail(series, min_run=4):
    """Length of the trailing run of identical values if >= min_run, else 0."""
    ordered = sorted(series.items(), key=lambda kv: month_index(kv[0]))
    if not ordered:
        return 0
    last = ordered[-1][1]
    run = 0
    for _date, v in reversed(ordered):
        if v == last:
            run += 1
        else:
            break
    return run if run >= min_run else 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_ts_utils.TestFlatTail -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/ts_utils.py tests/test_ts_utils.py
git commit -m "feat: add detect_flat_tail"
```

---

### Task 8: `collapse_duplicate_towns`

**Files:**
- Modify: `lib/ts_utils.py`
- Test: `tests/test_ts_utils.py`

Rule: group rows by `(ISO, year, Town)`; where >1, average `price_usd_per_kg_ppp` into one row (keep the first row's other fields — same town ⇒ same geo). Return `(collapsed_rows, collapsed_keys)`.

- [ ] **Step 1: Write the failing test** (append)

```python
class TestCollapseDuplicateTowns(unittest.TestCase):
    def test_averages_duplicate_town_year(self):
        rows = [
            {"ISO": "BFA", "year": "2017", "Town": "Yako",
             "price_usd_per_kg_ppp": "1.00", "longitude": "1.0"},
            {"ISO": "BFA", "year": "2017", "Town": "Yako",
             "price_usd_per_kg_ppp": "2.00", "longitude": "1.0"},
            {"ISO": "GHA", "year": "2017", "Town": "Tamale",
             "price_usd_per_kg_ppp": "0.50", "longitude": "9.0"},
        ]
        collapsed, keys = ts_utils.collapse_duplicate_towns(rows)
        self.assertEqual(len(collapsed), 2)
        yako = [r for r in collapsed if r["Town"] == "Yako"][0]
        self.assertAlmostEqual(float(yako["price_usd_per_kg_ppp"]), 1.50)
        self.assertIn(("BFA", "2017", "Yako"), keys)
        self.assertEqual(len(keys), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_ts_utils.TestCollapseDuplicateTowns -v`
Expected: FAIL — `AttributeError: ... 'collapse_duplicate_towns'`.

- [ ] **Step 3: Write minimal implementation** (append)

```python
def collapse_duplicate_towns(rows):
    """Collapse duplicate (ISO, year, Town) rows by averaging price.

    rows: list of dict (csv.DictReader rows) with str 'price_usd_per_kg_ppp'.
    Returns (collapsed_rows, collapsed_keys) where collapsed_keys lists the
    (ISO, year, Town) tuples that had >1 source row. Output preserves first-seen
    order; the averaged price is written back as a string.
    """
    groups = {}
    order = []
    for r in rows:
        key = (r["ISO"], r["year"], r["Town"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)

    collapsed = []
    collapsed_keys = []
    for key in order:
        members = groups[key]
        base = dict(members[0])
        if len(members) > 1:
            avg = mean(float(m["price_usd_per_kg_ppp"]) for m in members)
            base["price_usd_per_kg_ppp"] = f"{avg:.6g}"
            collapsed_keys.append(key)
        collapsed.append(base)
    return collapsed, collapsed_keys
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_ts_utils.TestCollapseDuplicateTowns -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add lib/ts_utils.py tests/test_ts_utils.py
git commit -m "feat: add collapse_duplicate_towns"
```

---

### Task 9: `flag_low_price`

**Files:**
- Modify: `lib/ts_utils.py`
- Test: `tests/test_ts_utils.py`

- [ ] **Step 1: Write the failing test** (append)

```python
class TestFlagLowPrice(unittest.TestCase):
    def test_below_floor_flagged(self):
        self.assertTrue(ts_utils.flag_low_price(0.01))
        self.assertTrue(ts_utils.flag_low_price(0.09))

    def test_at_or_above_floor_not_flagged(self):
        self.assertFalse(ts_utils.flag_low_price(0.10))
        self.assertFalse(ts_utils.flag_low_price(1.46))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_ts_utils.TestFlagLowPrice -v`
Expected: FAIL — `AttributeError: ... 'flag_low_price'`.

- [ ] **Step 3: Write minimal implementation** (append)

```python
def flag_low_price(price, floor=0.10):
    """True when price is below the implausible-low floor (USD/kg PPP)."""
    return float(price) < floor
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_ts_utils.TestFlagLowPrice -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/ts_utils.py tests/test_ts_utils.py
git commit -m "feat: add flag_low_price"
```

---

### Task 10: `prepare_dataset1.py` (forecasting-layer build)

**Files:**
- Create: `prepare_dataset1.py`
- Test: `tests/test_integration.py`

Builds the 5 Sybilion-ready series + quality artifacts. Product → filename via an explicit map (the parenthetical product names make a generic slugify unreliable, so the map guarantees the exact spec filenames).

- [ ] **Step 1: Write the failing integration test**

```python
# tests/test_integration.py
import json
import os
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D1 = os.path.join(ROOT, "data", "processed", "dataset1")


class TestDataset1Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["python3", "prepare_dataset1.py"], cwd=ROOT, check=True)

    def test_five_series_files_exist(self):
        for slug in ["urea", "dap", "tsp", "phosphate-rock", "mop"]:
            self.assertTrue(os.path.exists(os.path.join(D1, f"{slug}.json")), slug)

    def test_series_are_gapless_chronological_finite(self):
        for slug in ["urea", "dap", "tsp", "phosphate-rock", "mop"]:
            with open(os.path.join(D1, f"{slug}.json")) as fh:
                series = json.load(fh)
            keys = list(series.keys())
            self.assertEqual(keys, sorted(keys), f"{slug} not chronological")
            # 1996-04 .. 2026-03 inclusive = 360 months, no gaps
            self.assertEqual(len(keys), 360, f"{slug} wrong length")
            for v in series.values():
                self.assertTrue(isinstance(v, float))

    def test_phosphate_rock_gap_was_filled(self):
        with open(os.path.join(D1, "phosphate-rock.json")) as fh:
            series = json.load(fh)
        self.assertIn("2023-11-01", series)

    def test_quality_csv_flags_phosphate_rock(self):
        import csv
        with open(os.path.join(D1, "dataset1_quality.csv")) as fh:
            rows = {r["product"]: r for r in csv.DictReader(fh)}
        self.assertEqual(rows["Phosphate rock"]["data_quality"], "review")
        self.assertIn("stale_flat_tail", rows["Phosphate rock"]["flags"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_integration.TestDataset1Build -v`
Expected: FAIL — `prepare_dataset1.py` does not exist (`subprocess.CalledProcessError` / file-not-found).

- [ ] **Step 3: Write the implementation**

```python
# prepare_dataset1.py
"""Build Sybilion-ready monthly series + quality artifacts from dataset 1."""
import csv
import json
import os

from lib import ts_utils

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "data", "dataset1_worldbank_benchmark_USDperKG.csv")
OUT = os.path.join(ROOT, "data", "processed", "dataset1")

PRODUCT_SLUGS = {
    "Urea": "urea",
    "DAP (diammonium phosphate)": "dap",
    "Triple superphosphate (TSP)": "tsp",
    "Phosphate rock": "phosphate-rock",
    "Potassium chloride (MOP)": "mop",
}

# Data ends here; "today" is later -> stale-latest-data note (see spec section 5.2).
LAST_DATA_MONTH = "2026-03-01"


def load_series():
    """product -> {'YYYY-MM-DD': price_usd_per_kg (full precision)}."""
    series = {p: {} for p in PRODUCT_SLUGS}
    with open(RAW, newline="") as fh:
        for r in csv.DictReader(fh):
            kg = float(r["price_usd_per_tonne"]) / 1000.0
            series[r["product"]][r["date"]] = kg
    return series


def fill_gaps(series_for_product):
    """Linear-interpolate every missing interior month. Returns list of filled dates."""
    filled = []
    for missing in ts_utils.detect_gaps(list(series_for_product.keys())):
        series_for_product[missing] = ts_utils.linear_interpolate_gap(
            series_for_product, missing
        )
        filled.append(missing)
    return filled


def build():
    os.makedirs(OUT, exist_ok=True)
    raw = load_series()
    quality_rows = []
    detailed = {}

    for product, slug in PRODUCT_SLUGS.items():
        s = raw[product]
        filled = fill_gaps(s)
        ordered = {d: s[d] for d in sorted(s, key=ts_utils.month_index)}

        with open(os.path.join(OUT, f"{slug}.json"), "w") as fh:
            json.dump(ordered, fh, indent=2)

        flags = []
        outliers = ts_utils.detect_outlier_jumps(ordered, floor_pct=40.0)
        flat_run = ts_utils.detect_flat_tail(ordered, min_run=4)
        if outliers:
            flags.append("outlier_jump")
        if flat_run:
            flags.append("stale_flat_tail")
        if filled:
            flags.append("interpolated_gap")
        # Whole dataset 1 ends one+ month before "today" -> stale latest data.
        flags.append("stale_latest_data")

        quality_rows.append({
            "product": product,
            "data_quality": "review" if (outliers or flat_run or filled) else "ok",
            "flags": ";".join(flags),
        })
        detailed[product] = {
            "slug": slug,
            "outlier_jump_dates": outliers,
            "flat_tail_run_length": flat_run,
            "interpolated_gap_dates": filled,
            "last_data_month": LAST_DATA_MONTH,
        }

    with open(os.path.join(OUT, "dataset1_quality.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["product", "data_quality", "flags"])
        w.writeheader()
        w.writerows(quality_rows)

    with open(os.path.join(OUT, "data_quality_flags.json"), "w") as fh:
        json.dump(detailed, fh, indent=2)

    print(f"dataset1: wrote {len(PRODUCT_SLUGS)} series to {OUT}")


if __name__ == "__main__":
    build()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_integration.TestDataset1Build -v`
Expected: PASS (4 tests). The `stale_latest_data` flag note: because every product carries `stale_latest_data`, `data_quality` is driven by the *substantive* flags (outlier/flat/gap) only — Phosphate rock becomes `review`.

- [ ] **Step 5: Commit**

```bash
git add prepare_dataset1.py tests/test_integration.py
git commit -m "feat: build Sybilion-ready dataset1 series with quality flags"
```

---

### Task 11: `prepare_dataset2.py` (sourcing-layer build)

**Files:**
- Create: `prepare_dataset2.py`
- Modify: `tests/test_integration.py`

Produces `dataset2_towns_geo.csv` (cleaned/deduped passthrough), `urea_country_year.csv`, `urea_country_summary.csv`, and a sidecar.

- [ ] **Step 1: Write the failing integration test** (append to `tests/test_integration.py`)

```python
D2 = os.path.join(ROOT, "data", "processed", "dataset2")


class TestDataset2Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["python3", "prepare_dataset2.py"], cwd=ROOT, check=True)

    def _rows(self, name):
        import csv
        with open(os.path.join(D2, name)) as fh:
            return list(csv.DictReader(fh))

    def test_outputs_exist(self):
        for name in ["dataset2_towns_geo.csv", "urea_country_year.csv",
                     "urea_country_summary.csv", "data_quality_flags.json"]:
            self.assertTrue(os.path.exists(os.path.join(D2, name)), name)

    def test_towns_geo_deduped(self):
        # 6226 raw rows - 46 duplicate rows collapsed = 6180 town-year rows
        self.assertEqual(len(self._rows("dataset2_towns_geo.csv")), 6180)

    def test_country_year_has_no_null_keys(self):
        rows = self._rows("urea_country_year.csv")
        self.assertEqual(len(rows), 131)
        for r in rows:
            self.assertTrue(r["ISO"] and r["year"] and r["median_price_usd_per_kg_ppp"])

    def test_summary_one_row_per_country_with_recency_flag(self):
        rows = self._rows("urea_country_summary.csv")
        self.assertEqual(len(rows), 18)
        niger = [r for r in rows if r["country"] == "Niger"][0]
        # Niger's latest year is 2013 (< 2016) -> review
        self.assertEqual(niger["data_quality"], "review")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_integration.TestDataset2Build -v`
Expected: FAIL — `prepare_dataset2.py` does not exist.

- [ ] **Step 3: Write the implementation**

```python
# prepare_dataset2.py
"""Build cleaned country-level urea price tables + town geo passthrough from dataset 2."""
import csv
import json
import os
from collections import defaultdict

from lib import ts_utils

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "data", "dataset2_ssa_urea_USDperKG.csv")
OUT = os.path.join(ROOT, "data", "processed", "dataset2")

LOW_PRICE_FLOOR = 0.10
MIN_YEARS = 3          # < this -> review
STALE_LATEST_YEAR = 2016  # latest_year < this -> review


def build():
    os.makedirs(OUT, exist_ok=True)
    with open(RAW, newline="") as fh:
        raw_rows = list(csv.DictReader(fh))

    collapsed, collapsed_keys = ts_utils.collapse_duplicate_towns(raw_rows)

    # --- towns geo passthrough (raw, cleaned, not aggregated) ---
    geo_fields = ["ISO", "country", "year", "Town",
                  "longitude", "latitude", "distPort", "price_usd_per_kg_ppp"]
    with open(os.path.join(OUT, "dataset2_towns_geo.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=geo_fields)
        w.writeheader()
        for r in collapsed:
            w.writerow({k: r[k] for k in geo_fields})

    # --- country x year aggregation ---
    by_cy = defaultdict(list)   # (ISO, country, year) -> [price floats]
    low_by_cy = defaultdict(int)
    low_towns = []
    for r in collapsed:
        price = float(r["price_usd_per_kg_ppp"])
        key = (r["ISO"], r["country"], r["year"])
        by_cy[key].append(price)
        if ts_utils.flag_low_price(price, LOW_PRICE_FLOOR):
            low_by_cy[key] += 1
            low_towns.append({"ISO": r["ISO"], "year": r["year"],
                              "Town": r["Town"], "price": price})

    cy_rows = []
    for (iso, country, year), prices in sorted(by_cy.items()):
        low = low_by_cy[(iso, country, year)]
        cy_rows.append({
            "ISO": iso,
            "country": country,
            "year": year,
            "median_price_usd_per_kg_ppp": f"{ts_utils.median(prices):.4f}",
            "mean_price": f"{ts_utils.mean(prices):.4f}",
            "town_count": len(prices),
            "flagged_low_price_town_count": low,
            "data_quality": "review" if (low > 0 or len(prices) < 3) else "ok",
        })

    with open(os.path.join(OUT, "urea_country_year.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "ISO", "country", "year", "median_price_usd_per_kg_ppp", "mean_price",
            "town_count", "flagged_low_price_town_count", "data_quality"])
        w.writeheader()
        w.writerows(cy_rows)

    # --- country summary (recency-aware) ---
    by_country = defaultdict(list)  # ISO -> list of cy_rows
    for row in cy_rows:
        by_country[row["ISO"]].append(row)

    summary_rows = []
    for iso, rows in sorted(by_country.items()):
        years = sorted(int(r["year"]) for r in rows)
        latest = max(years)
        latest_row = [r for r in rows if int(r["year"]) == latest][0]
        all_year_medians = [float(r["median_price_usd_per_kg_ppp"]) for r in rows]
        summary_rows.append({
            "ISO": iso,
            "country": rows[0]["country"],
            "latest_year": latest,
            "latest_year_price": latest_row["median_price_usd_per_kg_ppp"],
            "mean_price_all_years": f"{ts_utils.mean(all_year_medians):.4f}",
            "years_covered": len(years),
            "data_quality": "review" if (len(years) < MIN_YEARS
                                         or latest < STALE_LATEST_YEAR) else "ok",
        })

    with open(os.path.join(OUT, "urea_country_summary.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "ISO", "country", "latest_year", "latest_year_price",
            "mean_price_all_years", "years_covered", "data_quality"])
        w.writeheader()
        w.writerows(summary_rows)

    with open(os.path.join(OUT, "data_quality_flags.json"), "w") as fh:
        json.dump({
            "collapsed_duplicate_town_years": [list(k) for k in collapsed_keys],
            "low_price_floor": LOW_PRICE_FLOOR,
            "low_price_towns": low_towns,
        }, fh, indent=2)

    print(f"dataset2: {len(cy_rows)} country-years, {len(summary_rows)} countries -> {OUT}")


if __name__ == "__main__":
    build()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_integration.TestDataset2Build -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add prepare_dataset2.py tests/test_integration.py
git commit -m "feat: build cleaned dataset2 country tables with quality flags"
```

---

### Task 12: `validate_processed.py` (local structural asserts)

**Files:**
- Create: `validate_processed.py`

Pure-local checks; exits non-zero on any failure. (The Sybilion MCP dry-run is Task 13 — it cannot run from inside a Python script.)

- [ ] **Step 1: Write the implementation**

```python
# validate_processed.py
"""Structural validation of processed outputs. Exits non-zero on failure."""
import csv
import json
import os
import sys

from lib import ts_utils

ROOT = os.path.dirname(os.path.abspath(__file__))
D1 = os.path.join(ROOT, "data", "processed", "dataset1")
D2 = os.path.join(ROOT, "data", "processed", "dataset2")
SLUGS = ["urea", "dap", "tsp", "phosphate-rock", "mop"]


def fail(msg, errors):
    errors.append(msg)


def main():
    errors = []

    # dataset1: each series gapless, chronological, finite, >= 120 points
    for slug in SLUGS:
        path = os.path.join(D1, f"{slug}.json")
        if not os.path.exists(path):
            fail(f"missing series file: {slug}.json", errors)
            continue
        with open(path) as fh:
            series = json.load(fh)
        keys = list(series.keys())
        if keys != sorted(keys):
            fail(f"{slug}: not chronological", errors)
        if ts_utils.detect_gaps(keys):
            fail(f"{slug}: has gaps {ts_utils.detect_gaps(keys)}", errors)
        if len(keys) < 120:
            fail(f"{slug}: only {len(keys)} points (<120)", errors)
        for d, v in series.items():
            if not isinstance(v, float) or v != v:  # NaN check
                fail(f"{slug}: non-finite value at {d}", errors)
                break

    # dataset2: key tables present, no null keys, plausible prices
    cy = os.path.join(D2, "urea_country_year.csv")
    if not os.path.exists(cy):
        fail("missing urea_country_year.csv", errors)
    else:
        with open(cy) as fh:
            for r in csv.DictReader(fh):
                if not (r["ISO"] and r["year"] and r["median_price_usd_per_kg_ppp"]):
                    fail(f"null key in country_year: {r}", errors)
                m = float(r["median_price_usd_per_kg_ppp"])
                if not (0.0 < m < 10.0):
                    fail(f"implausible median {m} for {r['ISO']} {r['year']}", errors)

    if errors:
        print("VALIDATION FAILED:")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print("VALIDATION PASSED: all processed outputs structurally valid.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `python3 validate_processed.py`
Expected: `VALIDATION PASSED: all processed outputs structurally valid.`

- [ ] **Step 3: Commit**

```bash
git add validate_processed.py
git commit -m "feat: add local structural validation of processed outputs"
```

---

### Task 13: Sybilion MCP dry-run (agent step, no credits)

**Files:** none (uses the generated `data/processed/dataset1/*.json`).

This step is performed by the executing agent calling the MCP tool — it cannot be scripted in Python. Run a **free** structural dry-run on each of the 5 series at `soft_horizon = 12`.

- [ ] **Step 1: For each slug in `urea, dap, tsp, phosphate-rock, mop`** — read `data/processed/dataset1/<slug>.json`, then call `mcp__sybilion__validate_forecast_data` with exactly:

```json
{
  "pipeline_version": "v1",
  "frequency": "monthly",
  "soft_horizon": 12,
  "backtest": false,
  "accept_stale_latest_data": true,
  "timeseries_metadata": {
    "title": "World Bank Pink Sheet monthly benchmark price for <PRODUCT>, USD per kilogram",
    "description": "Nominal FOB export-hub wholesale benchmark price for <PRODUCT> (USD/kg), monthly Apr 1996 - Mar 2026, World Bank Pink Sheet via IndexMundi. Used to forecast forward fertilizer price trend."
  },
  "timeseries": { ...contents of <slug>.json... }
}
```

(`accept_stale_latest_data: true` is intentional and structural-only — the data legitimately ends 2026-03; this dry-run does not commit any real forecast. See spec §1/§7.)

- [ ] **Step 2: Confirm each call returns success** (no validation error). If any series is rejected, record the exact reason and STOP — do not paper over it.

- [ ] **Step 3: Record the outcome** in the commit message of Task 15 (e.g. "5/5 series pass Sybilion dry-run at soft_horizon=12"). No code change in this task.

---

### Task 14: `data/CITATIONS.md`

**Files:**
- Create: `data/CITATIONS.md`

- [ ] **Step 1: Fetch the verbatim dataset 2 citation**

Use WebFetch on `https://doi.org/10.7910/DVN/E0EHLO` (Harvard Dataverse) and copy the dataset's official "Cite Dataset" text verbatim.

- [ ] **Step 2: Write the file** (substitute the fetched verbatim citation for dataset 2)

```markdown
# Data Sources & Citations

## Dataset 1 — World Bank "Pink Sheet" benchmark (`dataset1_worldbank_benchmark_USDperKG.csv`)
World Bank Commodity Price Data ("The Pink Sheet"), accessed via IndexMundi.
Free / open. Monthly FOB export-hub benchmark prices, Apr 1996 - Mar 2026.
Products: Urea, DAP, TSP, Rock phosphate, Potassium chloride (MOP).

## Dataset 2 — SSA farm-gate urea prices (`dataset2_ssa_urea_USDperKG.csv`)
<VERBATIM citation text fetched from https://doi.org/10.7910/DVN/E0EHLO>

DOI: 10.7910/DVN/E0EHLO
License note: redistribution outside Harvard Dataverse is restricted; this copy
is retained for internal hackathon use only and is attributed here per the
source's citation requirements.
```

- [ ] **Step 3: Commit**

```bash
git add data/CITATIONS.md
git commit -m "docs: add verbatim source citations for both datasets"
```

---

### Task 15: Full-suite verification + commit processed outputs

**Files:**
- Add: `data/processed/**` generated artifacts.

- [ ] **Step 1: Run the full test suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: all tests PASS (ts_utils unit tests + both integration classes).

- [ ] **Step 2: Regenerate clean outputs and validate**

```bash
python3 prepare_dataset1.py
python3 prepare_dataset2.py
python3 validate_processed.py
```
Expected: final line `VALIDATION PASSED: all processed outputs structurally valid.`

- [ ] **Step 3: Commit the processed artifacts**

```bash
git add data/processed/dataset1 data/processed/dataset2
git commit -m "data: add analysis-ready processed fertilizer datasets

5/5 dataset1 series pass Sybilion dry-run at soft_horizon=12.
dataset2: 131 country-years, 18 country summaries, 46 town-years collapsed."
```

- [ ] **Step 4: Final coverage sanity check**

Confirm every `lib/ts_utils.py` public function has at least one test in `tests/test_ts_utils.py` (month_index, index_to_month, mean, median, percentile, linear_interpolate_gap, detect_gaps, detect_outlier_jumps, detect_flat_tail, collapse_duplicate_towns, flag_low_price). All 11 are covered ⇒ ≥80% of the module.

---

## Self-Review

**Spec coverage:**
- §2 stdlib-only → all code uses only `csv`/`json`/`unittest`, hand-rolled math (Tasks 2-9). ✓
- §4 layout → Tasks 10/11 write exactly the specified files. ✓
- §5.1 full-precision USD/kg + gap fill → `load_series` (`/1000.0`), `fill_gaps` (Task 10). ✓
- §5.2 anomaly flags + stale note → `detect_outlier_jumps`/`detect_flat_tail`/`interpolated_gap`/`stale_latest_data` (Task 10). ✓
- §6.1 dedup + low-price flag + ISO key → Tasks 8, 11. ✓
- §6.2/§6.3 country-year + recency summary → Task 11. ✓
- §6.4 raw town geo passthrough → Task 11. ✓
- §7 validation (local + dry-run at soft_horizon 12, accept_stale true) → Tasks 12, 13. ✓
- §8 TDD pure funcs + integration smoke → Tasks 2-9 (TDD), 10-11 (integration). ✓
- §9 citations → Task 14. ✓

**Placeholder scan:** The only intentional fill-in is the verbatim DOI citation in Task 14 (must be fetched live — cannot be invented) and the `<PRODUCT>` substitution in Task 13 metadata. No vague "add error handling" steps; all code is complete. ✓

**Type consistency:** `month_index`/`index_to_month`, `mean`/`median`/`percentile`, `detect_gaps`/`detect_outlier_jumps`/`detect_flat_tail`, `collapse_duplicate_towns` (returns `(rows, keys)`), `flag_low_price(price, floor)` — names and signatures match between definition (Tasks 2-9) and use (Tasks 10-12). ✓
