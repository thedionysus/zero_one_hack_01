#!/usr/bin/env python3
"""Convert the World Bank fertilizer benchmark CSV into a Sybilion-ready series.

Input : dataset1_worldbank_benchmark_USDperKG.csv  (columns: product, date, price_usd_per_kg, ...)
Output: urea_sybilion.csv  (columns the kwopt engine reads: date,value)

Usage:  python convert_urea.py <input_csv> [--product Urea] [--out urea_sybilion.csv]
"""
import argparse, csv, sys
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_csv")
    ap.add_argument("--product", default="Urea")
    ap.add_argument("--out", default="urea_sybilion.csv")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.input_csv)))
    series = {}
    for r in rows:
        if r.get("product", "").strip() != a.product:
            continue
        d = str(r["date"]).strip()[:10]
        d = d[:8] + "01"                       # snap to first-of-month
        v = float(r["price_usd_per_kg"])
        series[d] = v
    series = dict(sorted(series.items()))

    if not series:
        sys.exit(f"ERROR: no rows for product={a.product!r}. Check the product name.")

    # write date,value
    with open(a.out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["date", "value"])
        for d, v in series.items(): w.writerow([d, v])

    # quality report (Sybilion needs monthly, first-of-month, >=40/60/120 pts, strictly_positive)
    dates = list(series)
    vals = list(series.values())
    # month-gap check
    def ym(s): return int(s[:4]) * 12 + int(s[5:7])
    gaps = [(dates[i-1], dates[i]) for i in range(1, len(dates)) if ym(dates[i]) - ym(dates[i-1]) != 1]
    print(f"product           : {a.product}")
    print(f"points            : {len(series)}  ({dates[0]} -> {dates[-1]})")
    print(f"value range       : {min(vals):.4f} .. {max(vals):.4f}  USD/kg")
    print(f"all strictly > 0  : {all(v > 0 for v in vals)}")
    print(f"month gaps        : {len(gaps)}" + ("" if not gaps else f"  e.g. {gaps[:3]}"))
    print(f"last 6 values     : {vals[-6:]}")
    print(f"wrote             : {a.out}")
    print("\nSybilion-ready    :", "YES" if (len(series) >= 120 and all(v > 0 for v in vals) and not gaps) else "CHECK ABOVE")

if __name__ == "__main__":
    main()
