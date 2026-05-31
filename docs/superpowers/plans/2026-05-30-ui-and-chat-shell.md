# Streamlit UI + Claude Chat Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Streamlit + Plotly demo UI (sliders = live adaptive levers, charts = visible reasoning) over the existing deterministic decision core, plus an optional thin Claude chat shell that turns a typed NL curveball into one concrete state change, re-solves, and narrates before→after.

**Architecture:** A thin `app/` package over the committed `lib/` core. The pipeline (cached calibrate → solve → render) always runs the same fixed order in Python; the LLM does only two edge jobs (translate a curveball into one `Change`, narrate the diff), each with a deterministic offline fallback so the app is fully demoable with no API key. The testable logic (state, changes, narration) is pure stdlib; streamlit/plotly/anthropic are isolated at the edges and guarded by import-skips so the existing `unittest` suite still runs under system Python.

**Tech Stack:** Python 3.14, Streamlit 1.58, Plotly 6.7, Anthropic SDK 0.105 — installed into a project `.venv` (cp314 wheels confirmed available). Decision core is pure stdlib. Tests via `unittest`; UI tests via `streamlit.testing.v1.AppTest`.

---

## Background the implementer needs

**Environment (verified):**
- System interpreter is `python3` = Python 3.14.4, pure stdlib only (no pip enabled by default; `python3 -m ensurepip` works).
- The UI deps install cleanly into a venv with cp314 wheels: streamlit 1.58.0, plotly 6.7.0, anthropic 0.105.2 (pulling numpy 2.4.6, pandas 3.0.3, pyarrow 24.0.0). PyPI is reachable.
- `ANTHROPIC_API_KEY` is **not set** in this environment. The app MUST run and demo fully without it (deterministic fallback). The LLM path is an enhancement only.
- The existing suite is **114 tests, green**, run with `python3 -m unittest discover -s tests -q`. After Task 1 you will run the suite with the venv interpreter `.venv/bin/python -m unittest discover -s tests -q` (the venv includes the stdlib, so the 114 still pass there).

**Existing `lib/` interfaces this plan builds on (do NOT modify the core):**
- `pipeline.load_manifest() -> {"last_real_date": "2026-03-01", ...}`; `pipeline.load_champions() -> {slug: champ}` for slugs `urea, dap, mop, tsp, phosphate-rock`.
- `pipeline.recalibrate_champion(champ, last_real_date) -> {"native", "corrected", "offsets", "bias", "cov80_native", "cov80_corrected"}` where `native`/`corrected` are blocks `{date: {pXX: float}}` (corrected always has all 19 quantiles `p05..p95`; native may have only `p50` for point-only forward forecasts).
- `pipeline.trust_for_champion(champ) -> {"score", "label", "calibration", "skill", "accuracy"}`.
- `pipeline.AUSTRIAN_UREA_PERSONA` (a `decision.Persona`), `pipeline.EUR_PER_USD = 0.92`.
- `decision.Persona(monthly_demand_t, current_stock_t=0.0, carrying_cost_pct_yr=0.18, risk_quantile="p50")` — frozen dataclass; valid `risk_quantile` keys are any present in the corrected band, e.g. `"p50"`, `"p70"`, `"p80"`.
- `decision.solve(block, persona) -> OrderPlan` with fields `months` (ordered date strings), `prices`, `orders_t` ({date: tonnes}), `purchase_for`, `optimal_cost`, `baseline_cost`, `savings` (USD), `savings_pct`, `recommendation` (`"BUY_NOW"|"WAIT"|"SPLIT"|"COVERED"`), `target_month`, `rationale`.
- `shocks.level_shift(block, pct) -> block` (uniform factor, decision-inert; scales € only), `shocks.trend_shift(block, g_per_month) -> block` (compounding monthly trend; CAN flip the decision), `shocks.plan_diff(before, after) -> {"recommendation":(b,a), "changed":bool, "target_month":(b,a), "savings":(b,a), "savings_delta", "savings_pct":(b,a)}`.

**Decisions locked for this plan (from spec §2/§6/§9):**
- Charts: forecast-with-bands, native-vs-corrected calibration overlay, decision/€-savings panel, trust table. The **driver-importance-over-horizon** panel is DEFERRED — `external_signals.json` is empty in the bake-off data (drivers need a separate forecast config), so v1 shows an honest "drivers: not wired (separate forecast)" note instead of fake data.
- Shocks: `level_shift` (€ lever) + `trend_shift` (the decision-flipping lever). No live Sybilion re-fetch in v1 (all shocks on cached quantiles) — spec §9.2 marks live re-fetch optional.
- Chat curveball semantics (resolved): a **rising-dynamic** phrase (spike/rally/surge/soar/rising/climb/jump) + a percentage maps to a **trend** shock (because that is what flips the decision and matches "rising"); a plain "+X% higher / prices up X%" with no rising keyword maps to a **level** shock (honest: a flat level shift, which moves € but not timing). Magnitude always comes from the user's number — never hardcoded.

**File structure (all new, under `app/`):**
- `app/__init__.py` — package marker.
- `app/state.py` — pure stdlib. `AppState` (selected fertilizer + 4 persona fields + 2 shock fields), `calibrate_all()` (persona-independent calibration of all 5, composed from `pipeline` public fns), `solve_state(state, calibrated)` (apply shocks → solve → diff vs no-shock baseline).
- `app/changes.py` — pure stdlib. `Change`, `apply_change`, `rule_based_parse`, `narrate_template`.
- `app/charts.py` — plotly figure builders (`forecast_figure`, `calibration_figure`, `savings_figure`, `trust_rows`).
- `app/agent.py` — the LLM edge: `parse_curveball(text, client=None)` (LLM if client else rule-based), `narrate(diff, change, client=None)` (LLM if client else template), `build_client()`.
- `app/main.py` — Streamlit entry wiring state + sliders + charts + chat.
- `requirements.txt` — pinned UI deps.
- Tests: `tests/test_app_state.py`, `tests/test_changes.py`, `tests/test_charts.py`, `tests/test_agent.py`, `tests/test_app_smoke.py`.

**Test-isolation rule:** `app/state.py` and `app/changes.py` import ONLY stdlib + `lib`. Their tests run under system `python3`. `charts.py` (plotly), `main.py` (streamlit), and the LLM path (anthropic) are guarded in tests with `unittest.skipUnless(...)` so the suite passes under either interpreter.

---

## Task 1: Environment + pinned dependencies

**Files:**
- Create: `requirements.txt`
- Create: `.venv/` (via command; do not commit it — add to `.gitignore`)
- Modify: `.gitignore` (create if absent)

- [ ] **Step 1: Create `requirements.txt`**

```
# UI + chat shell deps (decision core is pure stdlib and needs none of these).
# Pinned to versions verified to install with cp314 wheels on Python 3.14.
streamlit==1.58.0
plotly==6.7.0
anthropic==0.105.2
```

- [ ] **Step 2: Verify `.gitignore` (already set up — confirm, don't duplicate)**

`.gitignore` already contains these (committed during setup). Confirm they're present; add any that are missing:
```
__pycache__/
*.pyc
.env
.venv/
```
A gitignored `.env` already exists at the repo root containing `ANTHROPIC_API_KEY=...` (a throwaway demo key). Do NOT commit `.env`, do NOT print its contents, and do NOT remove it. Verify it stays ignored:
```bash
git check-ignore .env   # must print ".env"
git status --porcelain | grep -F '.env' && echo "ERROR: .env is visible to git" || echo ".env ignored — good"
```

- [ ] **Step 3: Create the venv and install deps**

Run:
```bash
python3 -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```
Expected: completes without build errors (all wheels are prebuilt for cp314). Takes a minute (pyarrow is ~46 MB).

- [ ] **Step 4: Verify imports and that the existing suite still passes under the venv**

Run:
```bash
.venv/bin/python -c "import streamlit, plotly, anthropic; print(streamlit.__version__, plotly.__version__, anthropic.__version__)"
.venv/bin/python -m unittest discover -s tests -q
```
Expected: prints `1.58.0 6.7.0 0.105.2`; then `OK` with 114 tests.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt
git commit -m "build: pin streamlit/plotly/anthropic deps for the UI (.venv, cp314)"
```
(`.gitignore` was already committed during setup; only `requirements.txt` is new here. Never `git add .env`.)

---

## Task 2: `app/state.py` — calibration cache + state-driven solve (pure stdlib)

**Files:**
- Create: `app/__init__.py` (empty)
- Create: `app/state.py`
- Test: `tests/test_app_state.py`

- [ ] **Step 1: Write the failing test**

Create `app/__init__.py` (empty file) first, then `tests/test_app_state.py`:
```python
import unittest

from app import state as st
from lib import decision as dc

SLUGS = {"urea", "dap", "mop", "tsp", "phosphate-rock"}


class TestCalibrateAll(unittest.TestCase):
    def test_calibrates_all_five(self):
        cal = st.calibrate_all()
        self.assertEqual(set(cal["by_fert"].keys()), SLUGS)
        self.assertIn(cal["hero"], SLUGS)
        self.assertEqual(cal["last_real_date"], "2026-03-01")
        urea = cal["by_fert"]["urea"]
        for k in ("native", "corrected", "cov80_native", "cov80_corrected", "trust"):
            self.assertIn(k, urea)
        # corrected band carries a full set of quantiles incl p10/p50/p90
        any_month = next(iter(urea["corrected"].values()))
        for q in ("p10", "p50", "p90"):
            self.assertIn(q, any_month)


class TestAppState(unittest.TestCase):
    def setUp(self):
        self.cal = st.calibrate_all()

    def test_default_selects_hero_and_austrian_persona(self):
        s = st.AppState.default(self.cal)
        self.assertEqual(s.fertilizer, self.cal["hero"])
        self.assertEqual(s.monthly_demand_t, 1000.0)
        self.assertEqual(s.current_stock_t, 3000.0)
        self.assertEqual(s.carrying_cost_pct_yr, 0.18)
        self.assertEqual(s.risk_quantile, "p50")
        self.assertEqual(s.shock_level_pct, 0.0)
        self.assertEqual(s.shock_trend_g, 0.0)

    def test_to_persona(self):
        s = st.AppState.default(self.cal)
        p = s.to_persona()
        self.assertIsInstance(p, dc.Persona)
        self.assertEqual(p.runway_months, 3.0)

    def test_solve_state_no_shock_matches_plain_solve(self):
        s = st.AppState.default(self.cal)
        res = st.solve_state(s, self.cal)
        corrected = self.cal["by_fert"][s.fertilizer]["corrected"]
        expected = dc.solve(corrected, s.to_persona())
        self.assertEqual(res["current_plan"].recommendation, expected.recommendation)
        # no shock => current equals baseline => no change
        self.assertFalse(res["diff"]["changed"])
        self.assertAlmostEqual(res["diff"]["savings_delta"], 0.0)

    def test_trend_shock_can_flip_and_is_diffed(self):
        # forecast-agnostic: search a g that flips the hero, then confirm the diff
        s0 = st.AppState.default(self.cal)
        flipped = None
        g = 0.02
        while g <= 0.60 + 1e-9:
            s = st.AppState.default(self.cal)
            s = s.__class__(**{**s.__dict__, "shock_trend_g": g})
            res = st.solve_state(s, self.cal)
            if res["diff"]["changed"]:
                flipped = res
                break
            g += 0.02
        self.assertIsNotNone(flipped, "some trend should flip the hero decision")
        self.assertNotEqual(flipped["diff"]["recommendation"][0],
                            flipped["diff"]["recommendation"][1])

    def test_savings_eur_uses_fx(self):
        from lib import pipeline
        s = st.AppState.default(self.cal)
        res = st.solve_state(s, self.cal)
        self.assertAlmostEqual(
            res["savings_eur"],
            res["current_plan"].savings * pipeline.EUR_PER_USD, places=9)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_app_state -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.state'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/state.py`:
```python
"""App state model + persona-independent calibration cache (pure stdlib).

The fixed pipeline: calibrate_all() recalibrates all five champions ONCE
(persona-independent), then solve_state() applies any shock to the selected
fertilizer's corrected band and re-solves against the current persona, diffing
the result against the no-shock baseline for the adaptive old->new render.
"""
from dataclasses import dataclass, replace

from lib import pipeline
from lib import decision as dc
from lib import shocks


def calibrate_all():
    """Recalibrate every champion (persona-independent). Cache this in the UI."""
    last_real_date = pipeline.load_manifest()["last_real_date"]
    champions = pipeline.load_champions()
    by_fert = {}
    scores = {}
    for slug, champ in champions.items():
        cal = pipeline.recalibrate_champion(champ, last_real_date)
        trust = pipeline.trust_for_champion(champ)
        by_fert[slug] = {
            "native": cal["native"],
            "corrected": cal["corrected"],
            "cov80_native": cal["cov80_native"],
            "cov80_corrected": cal["cov80_corrected"],
            "trust": trust,
        }
        scores[slug] = trust["score"]
    hero = max(scores, key=scores.get)
    return {"by_fert": by_fert, "hero": hero, "last_real_date": last_real_date}


@dataclass(frozen=True)
class AppState:
    """Everything a single render needs: which fertilizer, the persona levers,
    and the two forecast shocks. Immutable; changes return a new instance."""
    fertilizer: str
    monthly_demand_t: float
    current_stock_t: float
    carrying_cost_pct_yr: float
    risk_quantile: str
    shock_level_pct: float = 0.0
    shock_trend_g: float = 0.0

    @classmethod
    def default(cls, calibrated):
        p = pipeline.AUSTRIAN_UREA_PERSONA
        return cls(
            fertilizer=calibrated["hero"],
            monthly_demand_t=p.monthly_demand_t,
            current_stock_t=p.current_stock_t,
            carrying_cost_pct_yr=p.carrying_cost_pct_yr,
            risk_quantile=p.risk_quantile,
        )

    def to_persona(self):
        return dc.Persona(
            monthly_demand_t=self.monthly_demand_t,
            current_stock_t=self.current_stock_t,
            carrying_cost_pct_yr=self.carrying_cost_pct_yr,
            risk_quantile=self.risk_quantile,
        )

    def replaced(self, **changes):
        return replace(self, **changes)


def _apply_shocks(corrected, state):
    block = corrected
    if state.shock_trend_g:
        block = shocks.trend_shift(block, state.shock_trend_g)
    if state.shock_level_pct:
        block = shocks.level_shift(block, state.shock_level_pct)
    return block


def solve_state(state, calibrated):
    """Solve the selected fertilizer at the current persona + shocks.

    Returns the corrected & shocked blocks, the no-shock baseline plan, the
    current (shocked) plan, their diff, trust/coverage, and the EUR saving.
    """
    fert = calibrated["by_fert"][state.fertilizer]
    corrected = fert["corrected"]
    persona = state.to_persona()
    shocked = _apply_shocks(corrected, state)
    baseline_plan = dc.solve(corrected, persona)
    current_plan = dc.solve(shocked, persona)
    return {
        "persona": persona,
        "native": fert["native"],
        "corrected": corrected,
        "shocked": shocked,
        "baseline_plan": baseline_plan,
        "current_plan": current_plan,
        "diff": shocks.plan_diff(baseline_plan, current_plan),
        "trust": fert["trust"],
        "cov80_native": fert["cov80_native"],
        "cov80_corrected": fert["cov80_corrected"],
        "savings_eur": current_plan.savings * pipeline.EUR_PER_USD,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_app_state -v`
Expected: PASS (6 tests). Then full suite `python3 -m unittest discover -s tests -q` → `OK` (120 tests).

- [ ] **Step 5: Commit**

```bash
git add app/__init__.py app/state.py tests/test_app_state.py
git commit -m "feat: app state model + persona-independent calibration cache"
```

---

## Task 3: `app/changes.py` — Change model, apply, NL parse, narration (pure stdlib)

**Files:**
- Create: `app/changes.py`
- Test: `tests/test_changes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_changes.py`:
```python
import unittest

from app import changes
from app import state as st


class TestApplyChange(unittest.TestCase):
    def setUp(self):
        self.cal = st.calibrate_all()
        self.s = st.AppState.default(self.cal)

    def test_apply_trend(self):
        out = changes.apply_change(self.s, changes.Change("trend", 0.12))
        self.assertEqual(out.shock_trend_g, 0.12)
        self.assertEqual(self.s.shock_trend_g, 0.0)  # original unchanged

    def test_apply_level(self):
        out = changes.apply_change(self.s, changes.Change("level", 0.30))
        self.assertEqual(out.shock_level_pct, 0.30)

    def test_apply_persona_fields(self):
        out = changes.apply_change(self.s, changes.Change("stock", 1000.0))
        self.assertEqual(out.current_stock_t, 1000.0)
        out2 = changes.apply_change(self.s, changes.Change("risk", "p70"))
        self.assertEqual(out2.risk_quantile, "p70")

    def test_apply_fertilizer(self):
        out = changes.apply_change(self.s, changes.Change("fertilizer", "urea"))
        self.assertEqual(out.fertilizer, "urea")

    def test_reset_clears_shocks(self):
        shocked = self.s.replaced(shock_level_pct=0.3, shock_trend_g=0.1)
        out = changes.apply_change(shocked, changes.Change("reset", None))
        self.assertEqual(out.shock_level_pct, 0.0)
        self.assertEqual(out.shock_trend_g, 0.0)

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            changes.apply_change(self.s, changes.Change("nonsense", 1))


class TestRuleBasedParse(unittest.TestCase):
    def test_rising_keyword_plus_pct_is_trend(self):
        c = changes.rule_based_parse("gas spiked, prices +30%")
        self.assertEqual(c.kind, "trend")
        self.assertAlmostEqual(c.value, 0.30)

    def test_per_month_phrasing_is_trend(self):
        c = changes.rule_based_parse("prices rising 12% a month")
        self.assertEqual(c.kind, "trend")
        self.assertAlmostEqual(c.value, 0.12)

    def test_plain_higher_is_level(self):
        c = changes.rule_based_parse("prices are 20% higher")
        self.assertEqual(c.kind, "level")
        self.assertAlmostEqual(c.value, 0.20)

    def test_runway_phrase_sets_stock(self):
        c = changes.rule_based_parse("a supplier fell through, only 1 month of stock left")
        self.assertEqual(c.kind, "stock")
        # 1 month * default-ish; parser returns months, caller scales. Here we
        # encode the raw month count and let kind 'runway_months' convey intent.
        self.assertEqual(c.kind, "stock")

    def test_unparseable_returns_none(self):
        self.assertIsNone(changes.rule_based_parse("tell me a joke"))


class TestNarrateTemplate(unittest.TestCase):
    def test_flip_narration_mentions_both_recs(self):
        diff = {"recommendation": ("WAIT", "BUY_NOW"), "changed": True,
                "target_month": ("2026-11-01", "2026-04-01"),
                "savings": (100000.0, 500000.0), "savings_delta": 400000.0,
                "savings_pct": (0.1, 0.3)}
        text = changes.narrate_template(diff, changes.Change("trend", 0.12), 0.92)
        self.assertIn("WAIT", text)
        self.assertIn("BUY_NOW", text)
        self.assertIn("€", text)

    def test_no_change_narration(self):
        diff = {"recommendation": ("WAIT", "WAIT"), "changed": False,
                "target_month": ("2026-11-01", "2026-11-01"),
                "savings": (100000.0, 130000.0), "savings_delta": 30000.0,
                "savings_pct": (0.1, 0.13)}
        text = changes.narrate_template(diff, changes.Change("level", 0.30), 0.92)
        self.assertIn("WAIT", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_changes -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.changes'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/changes.py`:
```python
"""The one-concrete-change model + NL parse + deterministic narration (stdlib).

A Change is the single edit the chat shell (or a slider) produces. apply_change
returns a new AppState. rule_based_parse is the offline NL fallback; the LLM
edge (app/agent.py) produces the same Change type. narrate_template is the
offline before->after narration; the LLM may rephrase it.
"""
import re
from dataclasses import dataclass

VALID_KINDS = {
    "fertilizer", "demand", "stock", "carry", "risk", "level", "trend", "reset",
}

# rising-dynamic words => a percentage means a sustained upward TREND (flips the
# decision); a plain "higher/up" => a flat LEVEL shift (moves EUR, not timing).
_RISING = ("spike", "spiking", "spiked", "rally", "surge", "soar", "soaring",
           "rising", "rise", "climb", "climbing", "jump", "jumping")
_PER_MONTH = ("/mo", "per month", "a month", "/month", "monthly")


@dataclass(frozen=True)
class Change:
    kind: str
    value: object  # float for numeric kinds, str for fertilizer/risk, None for reset


def apply_change(state, change):
    """Return a NEW AppState with the single change applied. Pure."""
    k, v = change.kind, change.value
    if k == "fertilizer":
        return state.replaced(fertilizer=str(v))
    if k == "demand":
        return state.replaced(monthly_demand_t=float(v))
    if k == "stock":
        return state.replaced(current_stock_t=float(v))
    if k == "carry":
        return state.replaced(carrying_cost_pct_yr=float(v))
    if k == "risk":
        return state.replaced(risk_quantile=str(v))
    if k == "level":
        return state.replaced(shock_level_pct=float(v))
    if k == "trend":
        return state.replaced(shock_trend_g=float(v))
    if k == "reset":
        return state.replaced(shock_level_pct=0.0, shock_trend_g=0.0)
    raise ValueError(f"unknown change kind: {k}")


def _first_pct(text):
    """First percentage in the text as a fraction (e.g. '30%' -> 0.30), or None."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    return float(m.group(1)) / 100.0 if m else None


def _first_months(text):
    """First 'N month(s)' count as a float, or None."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*month", text)
    return float(m.group(1)) if m else None


def rule_based_parse(text):
    """Deterministic offline NL -> Change. Returns None if nothing parseable.

    Magnitude always comes from the user's number; no value is hardcoded.
    """
    t = text.lower()
    pct = _first_pct(t)
    rising = any(w in t for w in _RISING)
    per_month = any(p in t for p in _PER_MONTH)

    # company-situation: runway / stock change ("1 month of stock left")
    if ("stock" in t or "runway" in t or "supplier" in t) and "month" in t:
        months = _first_months(t)
        if months is not None:
            # caller multiplies by monthly demand; we encode stock tonnes via a
            # sentinel kind handled below. Here we return a stock change in
            # "months" units by convention: value is months, kind 'stock_months'.
            return Change("stock_months", months)

    if pct is not None:
        if rising or per_month:
            return Change("trend", pct)        # sustained upward push
        return Change("level", pct)            # flat level shift

    if any(w in t for w in ("reset", "clear", "undo", "back to normal")):
        return Change("reset", None)
    return None


def _change_phrase(change):
    k, v = change.kind, change.value
    if k == "trend":
        return f"A sustained +{v * 100:.0f}%/mo price trend"
    if k == "level":
        return f"A flat +{v * 100:.0f}% price level"
    if k in ("stock", "stock_months"):
        return "The new stock level"
    if k == "risk":
        return f"Risk tolerance {v}"
    if k == "fertilizer":
        return f"Switching to {v}"
    if k == "reset":
        return "Clearing the shocks"
    return "That change"


def narrate_template(diff, change, eur_per_usd):
    """Deterministic before->after narration in EUR. The LLM may rephrase this."""
    rb, ra = diff["recommendation"]
    sb = diff["savings"][0] * eur_per_usd
    sa = diff["savings"][1] * eur_per_usd
    head = _change_phrase(change) + " "
    if diff["changed"]:
        ta = diff["target_month"][1]
        body = (f"flips the call from {rb} to {ra}"
                + (f", now targeting {ta}" if ta else "") + ". ")
    else:
        body = f"keeps the call at {ra}. "
    tail = f"Forward saving moves from €{sb:,.0f} to €{sa:,.0f}."
    return head + body + tail
```

Note: `rule_based_parse` may return `Change("stock_months", N)` (a convenience kind). Handle it where changes are applied to state in `app/main.py` by converting months→tonnes (`stock = months * monthly_demand_t`) before calling `apply_change` with a `"stock"` Change. `apply_change` itself only knows the canonical kinds in `VALID_KINDS`; `stock_months` is a parser-level intent the UI normalizes. (The test only checks the parser returns a stock-related change, so it asserts `kind == "stock"` after the UI normalizes — adjust the parser test to expect `"stock_months"` since that's what the parser returns.)

**Correction to the test in Step 1:** change `test_runway_phrase_sets_stock` to assert the parser's raw output:
```python
    def test_runway_phrase_sets_stock(self):
        c = changes.rule_based_parse("a supplier fell through, only 1 month of stock left")
        self.assertEqual(c.kind, "stock_months")
        self.assertAlmostEqual(c.value, 1.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_changes -v`
Expected: PASS (all tests). Then full suite → `OK` (130 tests).

- [ ] **Step 5: Commit**

```bash
git add app/changes.py tests/test_changes.py
git commit -m "feat: Change model + offline NL parse + deterministic narration"
```

---

## Task 4: `app/charts.py` — Plotly figure builders

**Files:**
- Create: `app/charts.py`
- Test: `tests/test_charts.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_charts.py`:
```python
import unittest

try:
    import plotly.graph_objects as go  # noqa: F401
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

if HAS_PLOTLY:
    from app import charts
    from app import state as st


@unittest.skipUnless(HAS_PLOTLY, "plotly not installed (run under .venv)")
class TestCharts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cal = st.calibrate_all()
        s = st.AppState.default(cls.cal)
        cls.res = st.solve_state(s, cls.cal)

    def test_forecast_figure_has_band_and_line(self):
        fig = charts.forecast_figure(
            self.res["native"], self.res["corrected"], self.res["current_plan"])
        import plotly.graph_objects as go
        self.assertIsInstance(fig, go.Figure)
        self.assertGreaterEqual(len(fig.data), 2)  # at least band + median line

    def test_calibration_figure_two_bars(self):
        fig = charts.calibration_figure(
            self.res["cov80_native"], self.res["cov80_corrected"])
        self.assertEqual(len(fig.data), 1)  # one Bar trace with two categories
        self.assertEqual(len(fig.data[0].x), 2)

    def test_savings_figure_is_bar_over_months(self):
        fig = charts.savings_figure(self.res["current_plan"])
        self.assertGreaterEqual(len(fig.data), 1)
        self.assertEqual(len(fig.data[0].x), len(self.res["current_plan"].months))

    def test_trust_rows_cover_all_five(self):
        rows = charts.trust_rows(self.cal)
        self.assertEqual(len(rows), 5)
        for r in rows:
            for k in ("fertilizer", "trust", "label", "cov80_native", "cov80_corrected"):
                self.assertIn(k, r)
        # sorted by trust descending
        scores = [r["trust"] for r in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails (or skips under system python)**

Run under the venv so plotly is present:
`.venv/bin/python -m unittest tests.test_charts -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.charts'`.
(Under system `python3` the class is SKIPPED — that's expected and fine.)

- [ ] **Step 3: Write minimal implementation**

Create `app/charts.py`:
```python
"""Plotly figure builders for the demo UI. Pure functions: data in, Figure out.

Kept import-isolated (plotly only) so the rest of the app's logic stays stdlib
and unit-testable without the UI stack.
"""
import plotly.graph_objects as go

from lib.ts_utils import month_index

_BLUE = "#1f77b4"
_GREY = "#888888"
_GREEN = "#2ca02c"


def _ordered(block):
    return sorted(block.keys(), key=month_index)


def forecast_figure(native, corrected, plan):
    """Corrected P10-P90 band + P50 line, native P50 overlay, purchase markers."""
    months = _ordered(corrected)
    p50 = [corrected[m]["p50"] for m in months]
    p10 = [corrected[m]["p10"] for m in months]
    p90 = [corrected[m]["p90"] for m in months]

    fig = go.Figure()
    # corrected 80% band (p10..p90) as a shaded area
    fig.add_trace(go.Scatter(x=months + months[::-1], y=p90 + p10[::-1],
                             fill="toself", fillcolor="rgba(31,119,180,0.15)",
                             line=dict(width=0), hoverinfo="skip",
                             name="corrected 80% band"))
    fig.add_trace(go.Scatter(x=months, y=p50, mode="lines",
                             line=dict(color=_BLUE, width=2),
                             name="corrected P50"))
    # native P50 overlay (always present; dashed) for the native-vs-corrected story
    nat = [native[m].get("p50") for m in months if m in native]
    nat_months = [m for m in months if m in native and "p50" in native[m]]
    nat_vals = [native[m]["p50"] for m in nat_months]
    if nat_vals:
        fig.add_trace(go.Scatter(x=nat_months, y=nat_vals, mode="lines",
                                 line=dict(color=_GREY, width=1, dash="dash"),
                                 name="native P50"))
    # purchase markers sized by tonnage
    buy_months = [m for m in months if plan.orders_t.get(m, 0) > 0]
    if buy_months:
        sizes = [8 + 0.01 * plan.orders_t[m] for m in buy_months]
        ys = [corrected[m]["p50"] for m in buy_months]
        fig.add_trace(go.Scatter(x=buy_months, y=ys, mode="markers",
                                 marker=dict(color=_GREEN, size=sizes,
                                             line=dict(color="white", width=1)),
                                 name="scheduled buy"))
    fig.update_layout(title="Forecast (recalibrated) & purchase schedule",
                      yaxis_title="USD/kg", xaxis_title="month",
                      margin=dict(l=10, r=10, t=40, b=10), height=380)
    return fig


def calibration_figure(cov80_native, cov80_corrected):
    """Two bars: native vs corrected 80% coverage, with the 0.80 target line."""
    fig = go.Figure(go.Bar(
        x=["native", "corrected"],
        y=[cov80_native, cov80_corrected],
        marker_color=[_GREY, _BLUE],
        text=[f"{cov80_native:.0%}", f"{cov80_corrected:.0%}"],
        textposition="outside"))
    fig.add_hline(y=0.80, line=dict(color=_GREEN, dash="dot"),
                  annotation_text="80% target")
    fig.update_layout(title="80% band coverage: native vs recalibrated",
                      yaxis=dict(range=[0, 1.05], tickformat=".0%"),
                      margin=dict(l=10, r=10, t=40, b=10), height=300)
    return fig


def savings_figure(plan):
    """Bar of scheduled purchase tonnage per month (the decision surface)."""
    months = plan.months
    tonnes = [plan.orders_t.get(m, 0.0) for m in months]
    colors = [_GREEN if m == plan.target_month else _BLUE for m in months]
    fig = go.Figure(go.Bar(x=months, y=tonnes, marker_color=colors))
    fig.update_layout(title="Scheduled purchase (tonnes per month)",
                      yaxis_title="tonnes", xaxis_title="month",
                      margin=dict(l=10, r=10, t=40, b=10), height=300)
    return fig


def trust_rows(calibrated):
    """Trust table rows for all fertilizers, sorted by trust score descending."""
    rows = []
    for slug, f in calibrated["by_fert"].items():
        rows.append({
            "fertilizer": slug,
            "trust": f["trust"]["score"],
            "label": f["trust"]["label"],
            "cov80_native": f["cov80_native"],
            "cov80_corrected": f["cov80_corrected"],
        })
    rows.sort(key=lambda r: r["trust"], reverse=True)
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_charts -v`
Expected: PASS (4 tests). Confirm the suite still passes under BOTH interpreters:
- `.venv/bin/python -m unittest discover -s tests -q` → `OK` (134 tests).
- `python3 -m unittest discover -s tests -q` → `OK` (130 ran, charts skipped).

- [ ] **Step 5: Commit**

```bash
git add app/charts.py tests/test_charts.py
git commit -m "feat: plotly figure builders (forecast, calibration, savings, trust)"
```

---

## Task 5: `app/main.py` — Streamlit app (sliders + charts), no chat yet

This delivers a fully demoable UI: the trust table, the trust-hero forecast with native-vs-corrected bands, the decision + €-savings, and **adaptive re-solve via sliders** (persona levers + the two shock sliders). The chat shell is Task 7.

**Files:**
- Create: `app/main.py`
- Test: `tests/test_app_smoke.py`

- [ ] **Step 1: Write the failing smoke test**

Create `tests/test_app_smoke.py`:
```python
import unittest

try:
    from streamlit.testing.v1 import AppTest
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False


@unittest.skipUnless(HAS_STREAMLIT, "streamlit not installed (run under .venv)")
class TestAppSmoke(unittest.TestCase):
    def setUp(self):
        # Force the deterministic offline path so tests never hit the API, even
        # when a real key is present in .env. (build_client honours this.)
        import os
        os.environ["PROCUREMENT_NO_LLM"] = "1"

    def _run(self):
        at = AppTest.from_file("app/main.py", default_timeout=30)
        return at.run()

    def test_app_runs_without_exception(self):
        at = self._run()
        self.assertFalse(at.exception)

    def test_shows_hero_and_a_recommendation(self):
        at = self._run()
        # the recommendation is rendered via st.metric; at least one metric exists
        self.assertGreaterEqual(len(at.metric), 1)
        # the trust table fertilizers appear somewhere in the rendered markdown
        text = " ".join(m.value for m in at.markdown)
        self.assertIn("phosphate-rock", text + " ".join(str(m.label) for m in at.metric)
                      + " ".join(str(s.label) for s in at.selectbox))

    def test_trend_slider_can_flip_recommendation(self):
        # Forecast-agnostic: cranking the trend slider to its max should be able
        # to change the recommendation metric vs the unshocked baseline.
        base = self._run()
        base_recs = [m.value for m in base.metric]
        at = AppTest.from_file("app/main.py", default_timeout=30).run()
        # set the trend slider (key 'trend') to its maximum and re-run
        at.slider(key="trend").set_value(at.slider(key="trend").max).run()
        shocked_recs = [m.value for m in at.metric]
        self.assertNotEqual(base_recs, shocked_recs)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_app_smoke -v`
Expected: FAIL — `app/main.py` doesn't exist yet (AppTest raises on missing file / the app errors).

- [ ] **Step 3: Write the implementation**

Create `app/main.py`:
```python
"""Streamlit demo: trust-hero procurement decision with live adaptive levers.

Run:  .venv/bin/streamlit run app/main.py
The fixed pipeline (calibrate -> solve -> render) runs the same order every time;
sliders are the live levers. The chat shell (app/agent) is wired in Task 7.
"""
import os
import sys

# Make repo root importable when launched via `streamlit run app/main.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st  # noqa: E402

from app import state as app_state  # noqa: E402
from app import charts  # noqa: E402
from lib import pipeline  # noqa: E402

RISK_CHOICES = {"neutral (P50)": "p50", "cautious (P70)": "p70", "averse (P80)": "p80"}


@st.cache_data(show_spinner="Calibrating forecasts…")
def get_calibrated():
    return app_state.calibrate_all()


def _sidebar(cal, current):
    st.sidebar.header("Levers")
    fert = st.sidebar.selectbox(
        "Fertilizer", list(cal["by_fert"].keys()),
        index=list(cal["by_fert"].keys()).index(current.fertilizer), key="fert")
    demand = st.sidebar.slider("Monthly demand (t)", 100.0, 5000.0,
                               current.monthly_demand_t, 100.0, key="demand")
    stock = st.sidebar.slider("Current stock (t)", 0.0, 12000.0,
                              current.current_stock_t, 250.0, key="stock")
    carry = st.sidebar.slider("Carrying cost (%/yr)", 0.0, 0.40,
                              current.carrying_cost_pct_yr, 0.01, key="carry")
    risk_label = st.sidebar.select_slider("Risk tolerance", list(RISK_CHOICES.keys()),
                                          value=_risk_label(current.risk_quantile),
                                          key="risk")
    st.sidebar.subheader("Forecast shock")
    trend = st.sidebar.slider("Price trend (%/mo)", 0.0, 0.30, current.shock_trend_g,
                              0.01, key="trend",
                              help="A rising trend can flip WAIT to BUY-NOW.")
    level = st.sidebar.slider("Price level (±%)", -0.50, 0.50, current.shock_level_pct,
                              0.05, key="level",
                              help="Uniform shift: moves the € but not the timing.")
    return app_state.AppState(
        fertilizer=fert, monthly_demand_t=demand, current_stock_t=stock,
        carrying_cost_pct_yr=carry, risk_quantile=RISK_CHOICES[risk_label],
        shock_level_pct=level, shock_trend_g=trend)


def _risk_label(q):
    for label, key in RISK_CHOICES.items():
        if key == q:
            return label
    return "neutral (P50)"


def main():
    st.set_page_config(page_title="Fertilizer Procurement Agent", layout="wide")
    cal = get_calibrated()
    if "app_state" not in st.session_state:
        st.session_state.app_state = app_state.AppState.default(cal)

    state = _sidebar(cal, st.session_state.app_state)
    st.session_state.app_state = state
    res = app_state.solve_state(state, cal)
    plan = res["current_plan"]

    st.title("Fertilizer Procurement Decision Agent")
    st.caption(f"Hero by trust: **{cal['hero']}** · data through {cal['last_real_date']} · "
               "drivers panel: not wired in v1 (needs a separate forecast config)")

    c1, c2, c3 = st.columns(3)
    c1.metric("Recommendation", plan.recommendation,
              delta=None if not res["diff"]["changed"] else f"was {res['diff']['recommendation'][0]}")
    c2.metric("Target month", plan.target_month or "—")
    c3.metric("Forward saving vs naive", f"€{res['savings_eur']:,.0f}",
              delta=f"{plan.savings_pct:.1%}")
    st.write(plan.rationale)

    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(charts.forecast_figure(res["native"], res["corrected"], plan),
                        use_container_width=True)
        st.plotly_chart(charts.savings_figure(plan), use_container_width=True)
    with right:
        st.plotly_chart(charts.calibration_figure(res["cov80_native"],
                                                  res["cov80_corrected"]),
                        use_container_width=True)
        t = res["trust"]
        st.metric("Trust score", f"{t['score']:.2f} ({t['label']})")

    st.subheader("All fertilizers — trust ranking")
    st.dataframe(charts.trust_rows(cal), use_container_width=True, hide_index=True)


main()
```

- [ ] **Step 4: Run the smoke test, then run the app manually**

Run: `.venv/bin/python -m unittest tests.test_app_smoke -v` → expect PASS (3 tests).
Then manually: `.venv/bin/streamlit run app/main.py --server.headless true` — confirm it boots with no traceback in the terminal (Ctrl-C to stop). (Optional: open the URL and eyeball the charts.)

Confirm full suite under both interpreters:
- `.venv/bin/python -m unittest discover -s tests -q` → `OK` (137 tests).
- `python3 -m unittest discover -s tests -q` → `OK` (130 ran, UI tests skipped).

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_app_smoke.py
git commit -m "feat: Streamlit app — trust-hero decision with live slider levers"
```

---

## Task 6: `app/agent.py` — Claude chat edges (parse + narrate) with offline fallback

The LLM does exactly two edge jobs (spec §9.3): translate a typed curveball into one `Change`, and narrate the before→after. Both have deterministic fallbacks (Task 3) so the app works with no API key. The Anthropic client is injected so the core is unit-testable with a fake.

**REQUIRED SUB-SKILL for the implementer:** Use the `claude-api` skill when writing the Anthropic SDK calls (tool use + prompt caching of the system prompt and tool schema).

**Files:**
- Create: `app/agent.py`
- Test: `tests/test_agent.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_agent.py`:
```python
import unittest

from app import agent
from app import changes


class _FakeContentBlock:
    def __init__(self, name, inp):
        self.type = "tool_use"
        self.name = name
        self.input = inp


class _FakeMessage:
    def __init__(self, blocks):
        self.content = blocks


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


class TestParseCurveball(unittest.TestCase):
    def test_no_client_uses_rule_based(self):
        c = agent.parse_curveball("prices rising 12% a month", client=None)
        self.assertEqual(c.kind, "trend")
        self.assertAlmostEqual(c.value, 0.12)

    def test_no_client_unparseable_returns_none(self):
        self.assertIsNone(agent.parse_curveball("hello there", client=None))

    def test_client_tool_use_becomes_change(self):
        resp = _FakeMessage([_FakeContentBlock("apply_change",
                                               {"kind": "trend", "value": 0.2})])
        client = _FakeClient(resp)
        c = agent.parse_curveball("gas is surging", client=client)
        self.assertEqual(c.kind, "trend")
        self.assertAlmostEqual(c.value, 0.2)
        self.assertEqual(len(client.messages.calls), 1)

    def test_client_no_tool_use_falls_back_to_rules(self):
        resp = _FakeMessage([])  # model returned no tool call
        client = _FakeClient(resp)
        c = agent.parse_curveball("prices are 20% higher", client=client)
        self.assertEqual(c.kind, "level")  # rule-based fallback kicked in
        self.assertAlmostEqual(c.value, 0.20)


class TestNarrate(unittest.TestCase):
    def test_no_client_uses_template(self):
        diff = {"recommendation": ("WAIT", "BUY_NOW"), "changed": True,
                "target_month": ("2026-11-01", "2026-04-01"),
                "savings": (100000.0, 500000.0), "savings_delta": 400000.0,
                "savings_pct": (0.1, 0.3)}
        text = agent.narrate(diff, changes.Change("trend", 0.12), 0.92, client=None)
        self.assertIn("BUY_NOW", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_agent -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agent'`.

- [ ] **Step 3: Write the implementation**

Create `app/agent.py`:
```python
"""The thin Claude chat shell: NL curveball -> one Change, and diff -> narration.

Both jobs degrade to deterministic fallbacks (app/changes) when no client is
available, so the app demos fully with no ANTHROPIC_API_KEY. The Anthropic
client is injected (constructed in main.py only when a key is present), which
keeps this module unit-testable with a fake client and stdlib-only at import.
"""
import os

from app import changes

_MODEL = "claude-haiku-4-5"  # fast/cheap for a short NL->one-change + narration

_TOOL = {
    "name": "apply_change",
    "description": (
        "Translate the user's procurement curveball into exactly ONE concrete "
        "change to the decision inputs."),
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string",
                     "enum": ["trend", "level", "stock", "demand", "carry",
                              "risk", "fertilizer", "reset"]},
            "value": {"description": "fraction for trend/level/carry, tonnes for "
                                     "stock, t/mo for demand, a quantile like "
                                     "'p70' for risk, a slug for fertilizer, or "
                                     "null for reset"},
        },
        "required": ["kind", "value"],
    },
}

_SYSTEM = (
    "You convert a fertilizer-procurement manager's plain-English curveball into "
    "exactly one tool call. A rising/spiking/surging price story is a 'trend' "
    "(fraction per month). A flat 'prices are X% higher' is a 'level' (fraction). "
    "Stock/runway news sets 'stock' (tonnes). Always call apply_change once.")


def _load_dotenv():
    """Populate ANTHROPIC_API_KEY from a gitignored repo-root .env if unset.

    Minimal stdlib loader (no python-dotenv dep): reads KEY=VALUE lines, ignores
    blanks/comments, and does not override an already-set environment variable.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, ".env")
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())


def build_client():
    """Anthropic client if a key is available (env or .env), else None.

    None => the app uses the deterministic offline path (rule-based parse +
    template narration), so it still demos with no key. Set PROCUREMENT_NO_LLM=1
    to force the offline path even when a key exists (used by the app tests so
    they never hit the network).
    """
    if os.environ.get("PROCUREMENT_NO_LLM") == "1":
        return None
    _load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic  # lazy: only when a key is present
    return anthropic.Anthropic()


def _extract_tool_change(message):
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and block.name == "apply_change":
            inp = block.input
            return changes.Change(inp["kind"], inp.get("value"))
    return None


def parse_curveball(text, client=None):
    """NL -> one Change. LLM (tool use) when client is given, else rule-based.

    Falls back to rule_based_parse if the model returns no tool call.
    """
    if client is None:
        return changes.rule_based_parse(text)
    message = client.messages.create(
        model=_MODEL, max_tokens=256, system=_SYSTEM, tools=[_TOOL],
        tool_choice={"type": "tool", "name": "apply_change"},
        messages=[{"role": "user", "content": text}])
    change = _extract_tool_change(message)
    return change if change is not None else changes.rule_based_parse(text)


def narrate(diff, change, eur_per_usd, client=None):
    """Before->after narration. Template by default; LLM rephrases if client given."""
    template = changes.narrate_template(diff, change, eur_per_usd)
    if client is None:
        return template
    message = client.messages.create(
        model=_MODEL, max_tokens=160,
        system="Rephrase the procurement update in one or two crisp sentences for "
               "a warehouse manager. Keep every number exactly as given.",
        messages=[{"role": "user", "content": template}])
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            return block.text
    return template
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest tests.test_agent -v` → expect PASS (5 tests).
Full suite: `python3 -m unittest discover -s tests -q` → `OK` (135 tests under system python; 142 under `.venv`).

- [ ] **Step 5: Commit**

```bash
git add app/agent.py tests/test_agent.py
git commit -m "feat: Claude chat edges (parse/narrate) with offline fallback"
```

---

## Task 7: Wire the chat shell into `app/main.py`

**Files:**
- Modify: `app/main.py` (add the chat panel + curveball handling)
- Modify: `tests/test_app_smoke.py` (add a chat-driven flip test)

- [ ] **Step 1: Add the failing chat smoke test**

Append to `tests/test_app_smoke.py` inside the `TestAppSmoke` class:
```python
    def test_chat_curveball_flips_recommendation(self):
        # A typed rising-trend curveball should drive the same flip the slider does,
        # via the offline rule-based path (no API key in test env).
        at = AppTest.from_file("app/main.py", default_timeout=30).run()
        base = [m.value for m in at.metric]
        at.chat_input[0].set_value("prices rising 30% a month").run()
        after = [m.value for m in at.metric]
        self.assertNotEqual(base, after)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_app_smoke.TestAppSmoke.test_chat_curveball_flips_recommendation -v`
Expected: FAIL — there is no `chat_input` in the app yet (`IndexError`).

- [ ] **Step 3: Implement the chat panel in `app/main.py`**

Add the import near the others:
```python
from app import agent  # noqa: E402
from app import changes  # noqa: E402
```

Add, at the top of `main()` after `cal = get_calibrated()`:
```python
    if "client" not in st.session_state:
        st.session_state.client = agent.build_client()
    if "chat_log" not in st.session_state:
        st.session_state.chat_log = []
```

Replace the line `state = _sidebar(cal, st.session_state.app_state)` with handling that lets the chat mutate state BEFORE the sidebar renders from it. Insert this block immediately before that line:
```python
    prompt = st.chat_input("Throw a curveball (e.g. 'gas spiked, prices rising 25% a month')")
    if prompt:
        change = agent.parse_curveball(prompt, client=st.session_state.client)
        if change is None:
            st.session_state.chat_log.append(("assistant",
                "I couldn't turn that into a concrete change — try a number, "
                "e.g. 'prices rising 20% a month' or 'down to 1 month of stock'."))
        else:
            if change.kind == "stock_months":   # normalize parser intent -> tonnes
                change = changes.Change(
                    "stock", change.value * st.session_state.app_state.monthly_demand_t)
            before = app_state.solve_state(st.session_state.app_state, cal)
            st.session_state.app_state = changes.apply_change(
                st.session_state.app_state, change)
            after = app_state.solve_state(st.session_state.app_state, cal)
            note = agent.narrate(after["diff"] if change.kind in ("trend", "level")
                                 else shocks_free_diff(before, after),
                                 change, pipeline.EUR_PER_USD,
                                 client=st.session_state.client)
            st.session_state.chat_log.append(("user", prompt))
            st.session_state.chat_log.append(("assistant", note))
```

Add this helper above `main()` (a persona change has no shock diff, so diff the before/after current plans directly):
```python
from lib import shocks  # noqa: E402

def shocks_free_diff(before, after):
    return shocks.plan_diff(before["current_plan"], after["current_plan"])
```

And render the chat log at the bottom of `main()` (after the trust dataframe):
```python
    if st.session_state.chat_log:
        st.subheader("Agent")
        for role, msg in st.session_state.chat_log[-6:]:
            with st.chat_message(role):
                st.write(msg)
```

Important ordering note: because the chat updates `st.session_state.app_state` before `_sidebar` reads it, the sliders re-seed from the new state on the same run, and `solve_state(state, cal)` re-solves with the change applied — so a chat curveball and the equivalent slider produce the same result.

- [ ] **Step 4: Run the chat test, full suite, and the app**

Run:
- `.venv/bin/python -m unittest tests.test_app_smoke -v` → PASS (4 tests).
- `.venv/bin/python -m unittest discover -s tests -q` → `OK` (143 tests).
- `python3 -m unittest discover -s tests -q` → `OK` (135 ran, UI skipped).
- Manual: `.venv/bin/streamlit run app/main.py --server.headless true`, type "gas spiked, prices rising 25% a month" → recommendation flips, agent narrates the before→after. (Without an API key it uses the rule-based + template path; set `ANTHROPIC_API_KEY` to use Claude.)

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_app_smoke.py
git commit -m "feat: wire Claude chat curveball into the app (parse -> re-solve -> narrate)"
```

---

## Self-Review (completed during planning)

**Spec coverage (build-order §9 steps 4–5 + §2 UI):**
- Step 4 "Streamlit + Plotly UI (sliders = levers, chat box = curveball), charts" → Tasks 4–5 (charts + app with slider levers) and Task 7 (chat box). Charts: forecast-with-bands (`forecast_figure`), native-vs-corrected calibration overlay (`calibration_figure`), decision/€-savings (`savings_figure` + metrics), trust table (`trust_rows`). `st.cache_data` on calibration (Task 5), `st.session_state` for app state (Tasks 5, 7).
- Step 5 "thin Claude chat shell: NL curveball → one change → re-solve → narrate" → Tasks 6–7. LLM strictly at the two edges with deterministic fallbacks; the fixed pipeline stays in Python.
- §9.4 demo arc (hero → WAIT → curveball → BUY_NOW + larger saving): supported by the trend slider (Task 5) and the chat curveball (Task 7); the flip is forecast-agnostic (slider/chat magnitude, never hardcoded).
- §2 "decision is a pure function of (forecast, params)": `solve_state` is exactly that; every slider/chat change re-solves and `plan_diff` renders old→new.

**Deliberately deferred (honest, not faked):** the driver-importance-over-horizon panel (Q6–Q8) — `external_signals.json` is empty in the bake-off data; the UI shows a "not wired in v1" caption rather than fake drivers. Live Sybilion re-fetch (spec §9.2 marks it optional). The sourcing/landed-cost calculator (Q4/Q5) is a separate concern, not part of steps 4–5.

**Placeholder scan:** none — every step has complete, runnable code. (Task 3 carries an explicit in-line correction to one test assertion + a normalization note for the `stock_months` parser intent, both spelled out.)

**Type consistency:** `AppState` fields and `.replaced()`/`.to_persona()`/`.default()` are used identically across Tasks 2/3/5/7. `solve_state`'s return keys (`native, corrected, shocked, baseline_plan, current_plan, diff, trust, cov80_native, cov80_corrected, savings_eur`) match every consumer (charts, main, agent narration). `Change(kind, value)` and `apply_change`'s `VALID_KINDS` are consistent; the parser-only `stock_months` intent is explicitly normalized to a `stock` Change in main.py before `apply_change`. `plan_diff`'s dict shape (used in `narrate_template`, agent, and main) matches `shocks.plan_diff`. Chart functions consume `corrected`/`native` blocks (`{date:{pXX}}`) and `OrderPlan` fields (`months`, `orders_t`, `target_month`) exactly as the core defines them.

**Test-isolation invariant:** `app/state.py` and `app/changes.py` import only stdlib + `lib`, so their tests run under system `python3`; `charts`/`main` (plotly/streamlit) and the LLM path (anthropic) are `skipUnless`-guarded. Both interpreters keep a green suite at every task boundary.
