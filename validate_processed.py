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
