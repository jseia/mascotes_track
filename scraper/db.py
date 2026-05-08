from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
import sqlite3

from scraper.config import Tracker

SCHEMA = """
CREATE TABLE IF NOT EXISTS trackers (
  id    TEXT PRIMARY KEY,
  name  TEXT NOT NULL,
  color TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
  tracker_id  TEXT NOT NULL REFERENCES trackers(id),
  ts          INTEGER NOT NULL,
  lat         REAL    NOT NULL,
  lon         REAL    NOT NULL,
  accuracy_m  REAL,
  PRIMARY KEY (tracker_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_positions_ts ON positions(ts);
"""

@dataclass(frozen=True)
class Position:
    tracker_id: str
    ts: int
    lat: float
    lon: float
    accuracy_m: Optional[float]

class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path)
        c.execute("PRAGMA foreign_keys = ON")
        return c

    def init_schema(self) -> None:
        with self._conn() as c:
            c.executescript(SCHEMA)

    def seed_trackers(self, trackers: Iterable[Tracker]) -> None:
        with self._conn() as c:
            c.executemany(
                "INSERT OR REPLACE INTO trackers(id,name,color) VALUES (?,?,?)",
                [(t.id, t.name, t.color) for t in trackers],
            )

    def list_trackers(self) -> List[Tuple[str, str, str]]:
        with self._conn() as c:
            return list(c.execute("SELECT id,name,color FROM trackers ORDER BY id"))

    def insert_positions(self, positions: Iterable[Position]) -> int:
        rows = [(p.tracker_id, p.ts, p.lat, p.lon, p.accuracy_m) for p in positions]
        with self._conn() as c:
            cur = c.executemany(
                "INSERT OR IGNORE INTO positions(tracker_id,ts,lat,lon,accuracy_m) "
                "VALUES (?,?,?,?,?)",
                rows,
            )
            return cur.rowcount

    def count_positions(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM positions").fetchone()[0]

    def positions_for(self, tracker_id: str) -> List[Position]:
        with self._conn() as c:
            return [
                Position(*row)
                for row in c.execute(
                    "SELECT tracker_id,ts,lat,lon,accuracy_m FROM positions "
                    "WHERE tracker_id=? ORDER BY ts ASC",
                    (tracker_id,),
                )
            ]

    def all_positions(self) -> List[Position]:
        with self._conn() as c:
            return [
                Position(*row)
                for row in c.execute(
                    "SELECT tracker_id,ts,lat,lon,accuracy_m FROM positions "
                    "ORDER BY tracker_id, ts ASC"
                )
            ]
