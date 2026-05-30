"""Score the bake-off: rank variants per fertilizer, emit champions + report.

Reads data/forecast_exploration/bakeoff/manifest.json + saved artifacts, scores
each cell with lib.forecast_scoring, picks the lowest-MASE config per fertilizer,
and writes champions.json (agent input contract) + BAKEOFF_RESULTS.md.
"""
import json
import os

from lib import forecast_scoring as fs

PROCESSED = "data/processed/dataset1"
BAKEOFF = "data/forecast_exploration/bakeoff"


def _load(path):
    with open(path) as fh:
        return json.load(fh)


def _score_variant(series, bake_dir, slug, variant, last_real):
    traj_path = os.path.join(bake_dir, slug, variant, "backtest_trajectories.json")
    if not os.path.exists(traj_path):
        return None
    try:
        return fs.score_cell(series, _load(traj_path), last_real)
    except (ValueError, KeyError):
        return None


def assemble(manifest, processed_dir, bake_dir, fertilizers=None):
    """Return (champions_dict, markdown_report). Pure given the inputs/dirs."""
    fertilizers = fertilizers or fs.FERTILIZERS
    last_real = manifest["last_real_date"]
    champions = {}
    rows = []
    for slug in fertilizers:
        series = _load(os.path.join(processed_dir, f"{slug}.json"))
        cells = {v: _score_variant(series, bake_dir, slug, v, last_real)
                 for v in fs.VARIANTS}
        winner, ordered = fs.rank_variants(cells)
        wm = cells[winner]
        if wm is None:
            champions[slug] = {"winner_variant": None,
                               "error": "all variants unscoreable"}
            rows.append((slug, None, ordered, cells, None, False))
            continue
        # Detect ties: variants whose non-None metrics equal the winner's MASE+MAPE
        tied = [v for v, m in cells.items()
                if m is not None and m["mase"] == wm["mase"] and m["mape"] == wm["mape"]]
        tie = len(tied) > 1
        # When tied, prefer OFF (cheapest run; has native forward bands for these series)
        if tie and "OFF" in tied:
            winner = "OFF"
            wm = cells["OFF"]
        fcast = _load(os.path.join(bake_dir, slug, winner, "forecast.json"))
        block = fs.forecast_block(fcast)
        forward_bands_available = all("p95" in row for row in block.values())
        champions[slug] = {
            "winner_variant": winner,
            "job_id": manifest["cells"][slug][winner].get("job_id"),
            "config": {"recency_factor": fs.RECENCY.get(winner),
                       "soft_horizon": 12, "backtest": True,
                       "accept_stale_latest_data": True},
            "forecast": block,
            "forward_bands_available": forward_bands_available,
            "backtest_trajectories_ref":
                f"bakeoff/{slug}/{winner}/backtest_trajectories.json",
            "external_signals_ref":
                f"bakeoff/{slug}/{winner}/external_signals.json",
            "accuracy": {k: wm[k] for k in ("mase", "rmsse", "mape", "n_points",
                                            "n_windows_scored",
                                            "n_windows_excluded_stale")},
            "trust": {"cov80": wm["cov80"], "cov90": wm["cov90"]},
            "beats_naive": wm["mase"] < 1.0,
            "tie": tie,
        }
        rows.append((slug, winner, ordered, cells, forward_bands_available, tie))
    return champions, _render_markdown(rows)


def _render_markdown(rows):
    out = ["# Bake-off results\n",
           "Winner per fertilizer = lowest MASE (tiebreak MAPE), scored from",
           "backtest_trajectories.json with stale windows excluded. MASE/RMSSE < 1",
           "means the config beats a lag-12 seasonal-naive baseline.\n",
           "| fertilizer | winner | MASE | RMSSE | MAPE% | cov80 | cov90 | beats naive? |",
           "|---|---|---|---|---|---|---|---|"]
    for slug, winner, _ordered, cells, _fba, _tie in rows:
        m = cells[winner] if winner is not None else None
        if m is None:
            out.append(f"| {slug} | none | — | — | — | — | — | NO DATA |")
        else:
            out.append(f"| {slug} | {winner} | {m['mase']:.2f} | {m['rmsse']:.2f} | "
                       f"{m['mape']:.1f} | {m['cov80']:.0%} | {m['cov90']:.0%} | "
                       f"{'YES' if m['mase'] < 1.0 else 'no'} |")
    out.append("\n## Per-variant detail\n")
    for slug, winner, ordered, cells, fba, tie in rows:
        bands_note = ("(forward bands: NATIVE)" if fba
                      else "(forward bands: MISSING — derive from hindcast)"
                      if fba is not None else "")
        tie_note = " (TIE — OFF chosen, all variants equal)" if tie else ""
        out.append(f"### {slug} (winner: {winner}){tie_note} {bands_note}".rstrip())
        for v in ordered:
            m = cells[v]
            if m is None:
                out.append(f"- {v}: no data (failed or missing)")
            else:
                out.append(f"- {v}: MASE {m['mase']:.2f}, MAPE {m['mape']:.1f}%, "
                           f"cov80 {m['cov80']:.0%}, "
                           f"{m['n_windows_excluded_stale']} stale windows excluded")
    return "\n".join(out) + "\n"


def main():
    manifest = _load(os.path.join(BAKEOFF, "manifest.json"))
    champions, md = assemble(manifest, PROCESSED, BAKEOFF)
    with open(os.path.join(BAKEOFF, "champions.json"), "w") as fh:
        json.dump(champions, fh, indent=2)
    with open(os.path.join(BAKEOFF, "BAKEOFF_RESULTS.md"), "w") as fh:
        fh.write(md)
    print("Wrote champions.json + BAKEOFF_RESULTS.md")


if __name__ == "__main__":
    main()
