#!/usr/bin/env python3
"""kwopt CLI.

  probe     Phase-0: /drivers for a set; optionally diff vs a forecast's external_signals.json.
  screen    Cheap-screen keyword sets via /drivers; print S(K). No forecasts.
  ablate    Attribute keywords by ablation on /drivers. No forecasts.
  optimize  Full loop (baseline + propose -> screen -> shortlist -> PARALLEL forecast -> best).
  harvest   Run optimize across a diverse manifest; accumulate the engine's own best results.
  export    Export {context -> best_keywords} pairs (few-shot corpus / future fine-tune set).
  eval      Leave-one-out: does the engine's self-proposed keywords beat the no-keyword baseline?

Examples:
  export SYBILION_API_TOKEN=sk_...
  python -m kwopt.cli screen
  python -m kwopt.cli optimize --proposer static --rounds 2
  KWOPT_SKIP_SCREEN=1 KWOPT_CONCURRENCY=6 KWOPT_MAX_FORECASTS=30 python -m kwopt.cli optimize
  python -m kwopt.cli harvest --manifest targets.json
  python -m kwopt.cli export  --manifest targets.json --out pairs.json
  python -m kwopt.cli optimize --proposer experience --pairs pairs.json
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .config import SETTINGS
from .clients.sybilion import SybilionClient
from .core.scoring import parse_candidates, parse_signals, screen_candidates
from .cache.store import Store
from .schemas import Filters, Metadata, TargetSpec
from .agent.proposer import StaticProposer, LLMProposerAdapter, ExperienceProposer
from .agent.ablation import ablate
from .agent.orchestrator import optimize

ROBOT_TITLE = "Monthly U.S. Industrial Robot Imports"
ROBOT_DESC = ("Monthly U.S. imports for consumption of industrial robots, HTS 8479.50.0000, "
              "customs value in actual U.S. dollars.")


def read_timeseries(p: Path) -> dict[str, float]:
    out = {}
    with p.open() as f:
        for row in csv.DictReader(f):
            d = str(row["date"]).strip()[:10]
            out[d[:8] + "01"] = float(row["value"])
    return dict(sorted(out.items()))


def load_sets(p: Path) -> dict[str, list[str]]:
    return {n: v["keywords"] for n, v in json.loads(p.read_text()).items()}


def make_target(a) -> TargetSpec:
    return TargetSpec(a.target_id, a.title, a.description, read_timeseries(Path(a.csv)),
                      Filters(limit=SETTINGS.driver_limit), SETTINGS.recency_factor,
                      SETTINGS.horizon, SETTINGS.strictly_positive)


def _proposer(args, store, target):
    kind = getattr(args, "proposer", SETTINGS.proposer)
    if kind == "llm":
        from .clients.llm import LLMProposer
        return LLMProposerAdapter(LLMProposer(SETTINGS.llm_model))
    if kind == "experience":
        pairs = json.loads(Path(args.pairs).read_text())
        return ExperienceProposer(pairs, k=3, fallback=StaticProposer(load_sets(Path(args.sets))))
    return StaticProposer(load_sets(Path(args.sets)))


def cmd_screen(a):
    c, t = SybilionClient(), make_target(a)
    for name, kws in load_sets(Path(a.sets)).items():
        sr = screen_candidates(parse_candidates(c.drivers(Metadata(t.title, t.description, kws),
                               recency=t.recency_factor, filters=t.filters, series=t.timeseries)), SETTINGS.lam_c)
        print(f"\n=== {name} ({len(kws)} kw) ===")
        print(f"S={sr.score:.1f} candidates={sr.n_returned} mean_score={sr.mean_score:.3f} "
              f"coverage={sr.coverage} sources={sr.source_diversity}")
        for d in sr.drivers[:8]:
            print(f"   score={d.score:.3f} {d.category:12s} {d.name}  [{d.source}]")


def cmd_ablate(a):
    c, t = SybilionClient(), make_target(a)
    kws = load_sets(Path(a.sets))[a.set]
    for r in ablate(c, t, kws, SETTINGS.lam_w, SETTINGS.lam_c, group_by_cluster=not a.single):
        print(f"  ΔS={r['delta_S']:+8.1f}  {r['verdict']:24s}  removed: {r['removed']}")


def cmd_probe(a):
    c, t = SybilionClient(), make_target(a)
    kws = load_sets(Path(a.sets))[a.set]
    payload = c.drivers(Metadata(t.title, t.description, kws), recency=t.recency_factor,
                        filters=t.filters, series=t.timeseries)
    cand = parse_candidates(payload)
    sr = screen_candidates(cand, SETTINGS.lam_c)
    print(f"/drivers returned {sr.n_returned} candidates; mean_score={sr.mean_score:.3f}; "
          f"coverage={sr.coverage}; sources={sr.source_diversity}; S={sr.score:.1f}")
    print("payload top-level keys:", list(payload.keys()))
    if a.external:
        sig = parse_signals(json.loads(Path(a.external).read_text()))
        cand_names = {d.name for d in cand}
        used_names = {d.name for d in sig if d.used}
        inter = cand_names & used_names
        print(f"\ncandidate names: {len(cand_names)}; forecast USED drivers: {len(used_names)}; overlap: {len(inter)}")
        print(f"  used drivers also surfaced as candidates: {sorted(inter)}")
        print(f"  used by forecast but NOT in candidates:   {sorted(used_names - cand_names)}")
        print("\nHigh overlap => /drivers relevance is a decent proxy for what the model uses.")
        print("Low overlap  => screen is weak; with unlimited credit, prefer KWOPT_SKIP_SCREEN=1 and forecast more sets.")


def cmd_optimize(a):
    c, t = SybilionClient(), make_target(a)
    store = Store(SETTINGS.db_path)
    res = optimize(t, _proposer(a, store, t), c, store, SETTINGS, rounds=a.rounds)
    print("\n=== RESULT ===")
    print(json.dumps({"best_mape": res.best_mape, "baseline_mape": res.baseline_mape,
                      "lift_pp": res.lift_pp, "budget": res.budget,
                      "screened": res.screened, "forecast_scored": res.forecast_scored,
                      "best_keywords": res.best_keywords, "best_drivers": res.best_drivers,
                      "robust_drivers": res.robust[:8]}, indent=2))


def cmd_harvest(a):
    from .corpus.harvest import harvest
    out = harvest(Path(a.manifest), load_sets(Path(a.sets)), SETTINGS, rounds=a.rounds)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(f"\nHarvested {len(out)} targets -> {a.out}")


def cmd_export(a):
    from .distill.export import export_pairs
    pairs = export_pairs(Store(SETTINGS.db_path),
                         Path(a.manifest) if a.manifest else None, Path(a.out))
    print(f"Exported {len(pairs)} pairs -> {a.out}")


def cmd_eval(a):
    from .distill.eval import evaluate
    rows = evaluate(Path(a.manifest), Path(a.pairs), SETTINGS)
    print(json.dumps(rows, indent=2))


def main():
    p = argparse.ArgumentParser(prog="kwopt")
    p.add_argument("--csv", default="robot_imports_sybilion.csv")
    p.add_argument("--sets", default="keyword_sets.json")
    p.add_argument("--target-id", default="robot_imports_us")
    p.add_argument("--title", default=ROBOT_TITLE)
    p.add_argument("--description", default=ROBOT_DESC)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("screen")
    pa = sub.add_parser("ablate"); pa.add_argument("--set", default="labor_aware"); pa.add_argument("--single", action="store_true")
    pp = sub.add_parser("probe");  pp.add_argument("--set", default="labor_aware"); pp.add_argument("--external", default=None)
    po = sub.add_parser("optimize")
    po.add_argument("--rounds", type=int, default=2)
    po.add_argument("--proposer", default=SETTINGS.proposer, choices=["static", "llm", "experience"])
    po.add_argument("--pairs", default="pairs.json")
    ph = sub.add_parser("harvest"); ph.add_argument("--manifest", required=True); ph.add_argument("--rounds", type=int, default=2); ph.add_argument("--out", default="harvest.json")
    pe = sub.add_parser("export");  pe.add_argument("--manifest", default=None); pe.add_argument("--out", default="pairs.json")
    pv = sub.add_parser("eval");    pv.add_argument("--manifest", required=True); pv.add_argument("--pairs", default="pairs.json")

    a = p.parse_args()
    {"screen": cmd_screen, "ablate": cmd_ablate, "probe": cmd_probe, "optimize": cmd_optimize,
     "harvest": cmd_harvest, "export": cmd_export, "eval": cmd_eval}[a.cmd](a)


if __name__ == "__main__":
    main()
