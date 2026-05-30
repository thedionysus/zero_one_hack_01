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

def load_series():
    """product -> {'YYYY-MM-DD': price_usd_per_kg (full precision)}."""
    series = {p: {} for p in PRODUCT_SLUGS}
    with open(RAW, newline="") as fh:
        for r in csv.DictReader(fh):
            product = r["product"]
            if product not in series:
                continue
            series[product][r["date"]] = float(r["price_usd_per_tonne"]) / 1000.0
    return series


def fill_gaps(series_for_product):
    """Linear-interpolate every missing interior month on a COPY.

    detect_gaps only returns interior gaps (between min and max), so
    linear_interpolate_gap always has a neighbour on each side here.
    Returns (new_series, filled_dates).
    """
    s = dict(series_for_product)
    filled = []
    for missing in ts_utils.detect_gaps(list(s.keys())):
        s[missing] = ts_utils.linear_interpolate_gap(s, missing)
        filled.append(missing)
    return s, filled


def build():
    os.makedirs(OUT, exist_ok=True)
    raw = load_series()
    quality_rows = []
    detailed = {}

    for product, slug in PRODUCT_SLUGS.items():
        s, filled = fill_gaps(raw[product])
        ordered = {d: s[d] for d in sorted(s, key=ts_utils.month_index)}
        last_data_month = max(ordered)

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
            "last_data_month": last_data_month,
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
