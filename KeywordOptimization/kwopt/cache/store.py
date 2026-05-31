"""SQLite cache — single source of truth on disk (sheet 6). Thread-safe for parallel forecasts.

Tables: driver_cache (cheap tier), forecast_cache (expensive tier), attempts (log fed to LLM).
To move to PostgreSQL, reimplement this class against psycopg with the same signatures.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from typing import Optional

from ..schemas import ForecastResult, ScreenResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS driver_cache (
  key TEXT PRIMARY KEY, target_id TEXT NOT NULL, keywords TEXT NOT NULL, drivers_json TEXT NOT NULL,
  used_mass REAL, dead_count INTEGER, coverage INTEGER, screen_score REAL,
  created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS forecast_cache (
  key TEXT PRIMARY KEY, target_id TEXT NOT NULL, keywords TEXT NOT NULL, job_id TEXT,
  mape_12m REAL, eur_cents INTEGER, artifacts TEXT, created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS attempts (
  target_id TEXT NOT NULL, attempt_no INTEGER NOT NULL, keywords TEXT NOT NULL,
  screen_score REAL, mape_12m REAL, created_at TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (target_id, attempt_no));
"""


class Store:
    def __init__(self, db_path: str):
        # check_same_thread=False + a lock => safe use from ThreadPoolExecutor workers.
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    def get_driver(self, key: str) -> Optional[dict]:
        with self._lock:
            row = self.db.execute("SELECT drivers_json FROM driver_cache WHERE key=?", (key,)).fetchone()
        return json.loads(row["drivers_json"]) if row else None

    def put_driver(self, key, target_id, keywords, drivers_payload, sr: ScreenResult) -> None:
        with self._lock:
            self.db.execute(
                "INSERT OR REPLACE INTO driver_cache "
                "(key,target_id,keywords,drivers_json,used_mass,dead_count,coverage,screen_score) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (key, target_id, json.dumps(keywords), json.dumps(drivers_payload),
                 sr.used_mass, sr.dead_count, sr.coverage, sr.score))
            self.db.commit()

    def get_forecast(self, key: str) -> Optional[dict]:
        with self._lock:
            row = self.db.execute(
                "SELECT job_id,mape_12m,eur_cents,artifacts FROM forecast_cache WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        return {"job_id": row["job_id"], "mape_12m": row["mape_12m"],
                "eur_cents": row["eur_cents"], "artifacts": json.loads(row["artifacts"] or "{}")}

    def put_forecast(self, key, target_id, keywords, fr: ForecastResult) -> None:
        with self._lock:
            self.db.execute(
                "INSERT OR REPLACE INTO forecast_cache "
                "(key,target_id,keywords,job_id,mape_12m,eur_cents,artifacts) VALUES (?,?,?,?,?,?,?)",
                (key, target_id, json.dumps(keywords), fr.job_id, fr.mape_12m, fr.eur_cents,
                 json.dumps(fr.artifacts)))
            self.db.commit()

    def log_attempt(self, target_id, keywords, screen_score, mape_12m) -> int:
        with self._lock:
            row = self.db.execute("SELECT MAX(attempt_no) AS n FROM attempts WHERE target_id=?",
                                  (target_id,)).fetchone()
            no = (row["n"] or 0) + 1
            self.db.execute(
                "INSERT INTO attempts (target_id,attempt_no,keywords,screen_score,mape_12m) VALUES (?,?,?,?,?)",
                (target_id, no, json.dumps(keywords), screen_score, mape_12m))
            self.db.commit()
        return no

    def history(self, target_id: str) -> list[dict]:
        with self._lock:
            rows = self.db.execute(
                "SELECT attempt_no,keywords,screen_score,mape_12m FROM attempts WHERE target_id=? ORDER BY attempt_no",
                (target_id,)).fetchall()
        return [{"attempt": r["attempt_no"], "keywords": json.loads(r["keywords"]),
                 "screen_score": r["screen_score"], "mape": r["mape_12m"]} for r in rows]

    def best_for_target(self, target_id: str) -> Optional[dict]:
        with self._lock:
            row = self.db.execute(
                "SELECT keywords,mape_12m FROM forecast_cache WHERE target_id=? AND mape_12m IS NOT NULL "
                "ORDER BY mape_12m ASC LIMIT 1", (target_id,)).fetchone()
        return {"keywords": json.loads(row["keywords"]), "mape_12m": row["mape_12m"]} if row else None

    def all_best(self) -> list[dict]:
        with self._lock:
            rows = self.db.execute(
                "SELECT target_id, keywords, MIN(mape_12m) AS mape FROM forecast_cache "
                "WHERE mape_12m IS NOT NULL GROUP BY target_id", ()).fetchall()
        return [{"target_id": r["target_id"], "keywords": json.loads(r["keywords"]), "mape_12m": r["mape"]}
                for r in rows]
