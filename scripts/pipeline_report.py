"""Headless end-to-end report: trust table, hero pick, backtest, adaptive flip.

Run from the repo root:  python3 -m scripts.pipeline_report

A manual-verification artifact that exercises pipeline + impact + shocks together.
Not imported anywhere; no tests.
"""
import json
import os

from lib import pipeline
from lib import impact
from lib import shocks
from lib import decision as dc


def _load_traj(champ):
    ref = os.path.join(pipeline.DATA_DIR, champ["backtest_trajectories_ref"])
    with open(ref) as f:
        return json.load(f)


def _first_flip(corrected, persona, baseline_rec, g_max=0.60, step=0.02):
    """Smallest monthly trend g whose re-solve changes the recommendation.

    Forecast-agnostic: searches a range and returns the first g that flips, or
    None if nothing in range does. No magnitude is assumed.
    """
    g = step
    while g <= g_max + 1e-9:
        plan = dc.solve(shocks.trend_shift(corrected, g), persona)
        if plan.recommendation != baseline_rec:
            return g, plan
        g += step
    return None, None


def main():
    run = pipeline.run_all()
    persona = pipeline.AUSTRIAN_UREA_PERSONA
    champions = pipeline.load_champions()

    print(f"last_real_date = {run['last_real_date']}   hero = {run['hero']}\n")

    print(f"{'fertilizer':16}{'trust':>7}{'label':>8}{'rec':>9}"
          f"{'target':>12}{'fwd_eur':>12}")
    ranked = sorted(run["results"].values(),
                    key=lambda r: r["trust"]["score"], reverse=True)
    for r in ranked:
        plan = r["plan"]
        print(f"{r['fertilizer']:16}{r['trust']['score']:7.3f}"
              f"{r['trust']['label']:>8}{plan.recommendation:>9}"
              f"{(plan.target_month or '-'):>12}{r['savings_eur']:12.0f}")

    hero = run["results"][run["hero"]]
    cal = hero["calibration"]
    print(f"\nHero {run['hero']}: 80% band coverage "
          f"{cal['cov80_native']:.1%} -> {cal['cov80_corrected']:.1%} after recalibration")

    bt = impact.backtest(_load_traj(champions[run["hero"]]),
                         run["last_real_date"], persona)
    print(f"\nBacktest ({bt['n_windows']} non-stale windows): "
          f"total saving ${bt['total_saving']:,.0f} "
          f"({bt['total_saving_pct']:.1%} vs buy-as-you-go)")
    for w in bt["per_window"]:
        print(f"  {w['forecast_start']}->{w['forecast_end']}: "
              f"{w['recommendation']:8} saving ${w['saving']:,.0f} "
              f"capture {w['capture_ratio']:.0%}")

    corrected = cal["corrected"]
    base = dc.solve(corrected, persona)
    print(f"\nAdaptive demo (rising-trend curveball):")
    print(f"  baseline: {base.recommendation} (target {base.target_month or '-'}, "
          f"saving ${base.savings:,.0f})")
    g, flipped = _first_flip(corrected, persona, base.recommendation)
    if flipped is None:
        print("  no monthly trend in the searched range changed the recommendation")
    else:
        diff = shocks.plan_diff(base, flipped)
        rb, ra = diff["recommendation"]
        tb, ta = diff["target_month"]
        print(f"  +{g*100:.0f}%/mo trend -> {rb} -> {ra} "
              f"(target {tb or '-'} -> {ta or '-'}, "
              f"saving ${diff['savings'][0]:,.0f} -> ${diff['savings'][1]:,.0f})")


if __name__ == "__main__":
    main()
