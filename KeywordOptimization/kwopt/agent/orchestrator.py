"""The loop: propose -> hash -> (cache) -> cheap screen -> shortlist -> PARALLEL full-forecast -> stop.

v0.2 additions vs spec:
- No-keyword (similarity-only) BASELINE forecast computed first => the floor + keyword LIFT.
- Parallel forecast dispatch bounded by Budget.max_concurrency (unlimited credit; latency is the cost).
- skip_screen mode: with credit free, optionally forecast all candidates (still cached, still parallel).
- Robust-driver tracking across screened sets (noise-reduction signal).
- Result exposes best keyword set AND its critical driver names.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

from ..clients.sybilion import SybilionClient, build_forecast_body
from ..config import Settings
from ..core.hashing import canonical_key
from ..core.scoring import mape_12m, parse_candidates, parse_signals, robust_drivers, screen_candidates
from ..core.validate import validate_keywords
from ..cache.store import Store
from ..schemas import ForecastResult, Metadata, ScreenResult, TargetSpec
from .budget import Budget


@dataclass
class OptResult:
    best_keywords: Optional[list[str]]
    best_mape: Optional[float]
    baseline_mape: Optional[float]      # no-keyword similarity-only floor
    lift_pp: Optional[float]            # baseline_mape - best_mape (percentage points improved)
    best_drivers: list[str] = field(default_factory=list)  # critical driver names of the winner
    robust: list[tuple] = field(default_factory=list)       # drivers recurring across sets
    budget: dict = field(default_factory=dict)
    screened: int = 0
    forecast_scored: int = 0


def _screen_one(client, store, target: TargetSpec, keywords: list[str], cfg: Settings) -> ScreenResult:
    keywords = validate_keywords(keywords)
    key = canonical_key(target.target_id, keywords, target.recency_factor, target.filters)
    cached = store.get_driver(key)
    if cached is not None:
        return screen_candidates(parse_candidates(cached), cfg.lam_c)
    payload = client.drivers(
        Metadata(target.title, target.description, keywords),
        recency=target.recency_factor, filters=target.filters, series=target.timeseries,
    )
    sr = screen_candidates(parse_candidates(payload), cfg.lam_c)
    store.put_driver(key, target.target_id, keywords, payload, sr)
    return sr


def _forecast_one(client, store, target: TargetSpec, keywords: list[str], cfg: Settings) -> ForecastResult:
    key = canonical_key(target.target_id, keywords, target.recency_factor, target.filters)
    cached = store.get_forecast(key)
    if cached is not None:
        return ForecastResult(cached["job_id"], cached["mape_12m"], cached["eur_cents"], cached["artifacts"])
    body = build_forecast_body(target, keywords)
    res = client.wait_forecast(body)
    mape = mape_12m(res["artifacts"]["backtest_metrics.json"])
    fr = ForecastResult(res["job_id"], mape, res["eur_cents"], res["artifacts"])
    store.put_forecast(key, target.target_id, keywords, fr)
    return fr


def _score_parallel(client, store, target, keyword_sets: list[list[str]], cfg: Settings, budget: Budget):
    """Full-forecast several keyword sets concurrently (bounded by max_concurrency)."""
    sets = keyword_sets[: budget.remaining_forecasts()]
    results: list[tuple[list[str], ForecastResult]] = []
    if not sets:
        return results
    with ThreadPoolExecutor(max_workers=max(1, budget.max_concurrency)) as ex:
        futs = {ex.submit(_forecast_one, client, store, target, kws, cfg): kws for kws in sets}
        for fut in as_completed(futs):
            kws = futs[fut]
            try:
                fr = fut.result()
            except Exception as exc:
                print(f"  forecast skip: {exc}")
                continue
            budget.record_forecast(fr.eur_cents, fr.mape_12m)
            store.log_attempt(target.target_id, kws, None, fr.mape_12m)
            print(f"  [forecast] MAPE={fr.mape_12m:6.3f}%  €{fr.eur_cents/100:.2f}  ({len(kws)} kw)")
            results.append((kws, fr))
    return results


def optimize(target: TargetSpec, proposer, client: SybilionClient, store: Store, cfg: Settings,
             rounds: int = 2) -> OptResult:
    budget = Budget(cfg.max_forecasts, cfg.max_concurrency,
                    (cfg.max_wall_minutes * 60) or None, cfg.target_mape, cfg.no_improve_patience)
    best_keywords: Optional[list[str]] = None
    best_fr: Optional[ForecastResult] = None
    screens: list[ScreenResult] = []
    screened = scored = 0

    # --- Baseline: no keywords => similarity-only floor (transcript: similarity works without keywords) ---
    baseline_mape = None
    try:
        base_fr = _forecast_one(client, store, target, [], cfg)
        baseline_mape = base_fr.mape_12m
        budget.record_forecast(base_fr.eur_cents, base_fr.mape_12m)
        store.log_attempt(target.target_id, [], None, base_fr.mape_12m)
        print(f"  [baseline no-kw] MAPE={baseline_mape:.3f}%")
    except Exception as exc:
        print(f"  baseline skip: {exc}")

    for rnd in range(rounds):
        candidates = proposer.propose_batch(target, store.history(target.target_id), best_keywords)
        if not candidates:
            break

        ranked: list[tuple[float, list[str]]] = []
        if cfg.skip_screen:
            # credit-rich path: forecast everything (still cached + parallel), no screen gate
            ranked = [(0.0, ks.keywords) for ks in candidates]
        else:
            for ks in candidates:
                try:
                    sr = _screen_one(client, store, target, ks.keywords, cfg)
                except Exception as exc:
                    print(f"  screen skip ({ks.origin}): {exc}")
                    continue
                screened += 1
                screens.append(sr)
                store.log_attempt(target.target_id, ks.keywords, sr.score, None)
                print(f"  [screen] S={sr.score:8.1f} cand={sr.n_returned} mean_score={sr.mean_score:.3f} "
                      f"cov={sr.coverage} sources={sr.source_diversity} ({ks.origin})")
                ranked.append((sr.score, ks.keywords))
            ranked.sort(key=lambda t: t[0], reverse=True)

        shortlist = [kws for _s, kws in ranked[: cfg.shortlist_m]]
        for kws, fr in _score_parallel(client, store, target, shortlist, cfg, budget):
            scored += 1
            if best_fr is None or fr.mape_12m < best_fr.mape_12m:
                best_fr, best_keywords = fr, kws

        if budget.should_stop():
            print(f"  stop: {budget.summary()}")
            break

    best_mape = best_fr.mape_12m if best_fr else None
    lift = (baseline_mape - best_mape) if (baseline_mape is not None and best_mape is not None) else None
    best_drivers: list[str] = []
    if best_fr and "external_signals.json" in best_fr.artifacts:
        ds = sorted(parse_signals(best_fr.artifacts["external_signals.json"]),
                    key=lambda d: d.importance, reverse=True)
        best_drivers = [f"{d.name}{' (INV)' if d.inverted else ''}" for d in ds if d.used][:10]

    return OptResult(
        best_keywords=best_keywords, best_mape=best_mape, baseline_mape=baseline_mape,
        lift_pp=lift, best_drivers=best_drivers,
        robust=robust_drivers(screens) if screens else [],
        budget=budget.summary(), screened=screened, forecast_scored=scored,
    )
