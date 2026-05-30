# tests/test_integration.py
import csv
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
        with open(os.path.join(D1, "dataset1_quality.csv")) as fh:
            rows = {r["product"]: r for r in csv.DictReader(fh)}
        self.assertEqual(rows["Phosphate rock"]["data_quality"], "review")
        self.assertIn("stale_flat_tail", rows["Phosphate rock"]["flags"])

    def test_stale_latest_alone_does_not_trigger_review(self):
        with open(os.path.join(D1, "dataset1_quality.csv")) as fh:
            rows = {r["product"]: r for r in csv.DictReader(fh)}
        tsp = rows["Triple superphosphate (TSP)"]
        self.assertEqual(tsp["data_quality"], "ok")
        self.assertEqual(tsp["flags"], "stale_latest_data")


D2 = os.path.join(ROOT, "data", "processed", "dataset2")


class TestDataset2Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["python3", "prepare_dataset2.py"], cwd=ROOT, check=True)

    def _rows(self, name):
        with open(os.path.join(D2, name)) as fh:
            return list(csv.DictReader(fh))

    def test_outputs_exist(self):
        for name in ["dataset2_towns_geo.csv", "urea_country_year.csv",
                     "urea_country_summary.csv", "data_quality_flags.json"]:
            self.assertTrue(os.path.exists(os.path.join(D2, name)), name)

    def test_towns_geo_keeps_all_obs_with_source(self):
        rows = self._rows("dataset2_towns_geo.csv")
        # 6226 raw - 36 named-town duplicate rows collapsed = 6190 observations
        self.assertEqual(len(rows), 6190)
        self.assertIn("source", rows[0])
        sources = {r["source"] for r in rows}
        self.assertEqual(sources, {"Afr", "LSMS"})

    def test_country_year_source_split_is_consistent(self):
        rows = self._rows("urea_country_year.csv")
        self.assertEqual(len(rows), 131)
        total_obs = total_afr = total_lsms = 0
        for r in rows:
            self.assertTrue(r["ISO"] and r["year"] and r["median_price_usd_per_kg_ppp"])
            obs = int(r["obs_count"])
            afr = int(r["n_afr_obs"])
            lsms = int(r["n_lsms_obs"])
            self.assertEqual(obs, afr + lsms)  # split must sum to total
            total_obs += obs
            total_afr += afr
            total_lsms += lsms
        self.assertEqual(total_obs, 6190)
        self.assertEqual(total_afr, 1397)
        self.assertEqual(total_lsms, 4793)

    def test_summary_one_row_per_country_with_recency_flag(self):
        rows = self._rows("urea_country_summary.csv")
        self.assertEqual(len(rows), 18)
        niger = [r for r in rows if r["country"] == "Niger"][0]
        self.assertEqual(niger["data_quality"], "review")  # latest year 2013 < 2016

    def test_low_price_flag_triggers_review(self):
        # A country-year with flagged low-price observations must be data_quality=review.
        rows = self._rows("urea_country_year.csv")
        flagged = [r for r in rows if int(r["flagged_low_price_obs_count"]) > 0]
        self.assertTrue(flagged, "expected at least one country-year with low-price flags")
        for r in flagged:
            self.assertEqual(r["data_quality"], "review")

    def test_small_obs_count_triggers_review(self):
        rows = self._rows("urea_country_year.csv")
        for r in rows:
            if int(r["obs_count"]) < 3:
                self.assertEqual(r["data_quality"], "review")

    def test_sidecar_records_collapsed_named_town_keys(self):
        import json as _json
        with open(os.path.join(D2, "data_quality_flags.json")) as fh:
            side = _json.load(fh)
        # 35 genuine named-town duplicate groups were collapsed (spec section 6.0/6.1).
        self.assertEqual(len(side["collapsed_duplicate_named_town_keys"]), 35)
        self.assertEqual(side["low_price_floor"], 0.10)
        self.assertIn("low_price_observations", side)
