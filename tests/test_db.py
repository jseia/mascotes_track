from pathlib import Path
from scraper.db import Database, Position
from scraper.config import Tracker

def test_init_creates_schema(tmp_path: Path):
    db = Database(tmp_path / "x.sqlite")
    db.init_schema()
    # opening again should be a no-op
    db.init_schema()

def test_seed_trackers_idempotent(tmp_path: Path):
    db = Database(tmp_path / "x.sqlite")
    db.init_schema()
    ts = [Tracker(id="a", name="One", color="#fff")]
    db.seed_trackers(ts)
    db.seed_trackers(ts)  # second call must not raise / duplicate
    rows = db.list_trackers()
    assert rows == [("a", "One", "#fff")]

def test_insert_positions_idempotent(tmp_path: Path):
    db = Database(tmp_path / "x.sqlite")
    db.init_schema()
    db.seed_trackers([Tracker(id="a", name="One", color="#fff")])
    p = Position(tracker_id="a", ts=1000, lat=1.0, lon=2.0, accuracy_m=10.0)
    db.insert_positions([p])
    db.insert_positions([p])  # same (tracker_id, ts) → ignored
    assert db.count_positions() == 1

def test_recent_positions_returns_sorted(tmp_path: Path):
    db = Database(tmp_path / "x.sqlite")
    db.init_schema()
    db.seed_trackers([Tracker(id="a", name="One", color="#fff")])
    db.insert_positions([
        Position("a", 2000, 0.0, 0.0, None),
        Position("a", 1000, 0.0, 0.0, None),
        Position("a", 3000, 0.0, 0.0, None),
    ])
    rows = db.positions_for("a")
    assert [r.ts for r in rows] == [1000, 2000, 3000]
