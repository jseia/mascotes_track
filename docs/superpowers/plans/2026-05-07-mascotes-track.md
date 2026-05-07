# Mascotes Track Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local scraper + static web visualization that polls Google Find Hub every ~15 min for three Bluetooth trackers and renders their movement on a Leaflet map with fading trails.

**Architecture:** A long-lived Python process drives Playwright/Chromium against `google.com/find` (with a persisted login session), extracts location XHR responses, upserts into SQLite, then exports a compact `web/data.json`. A static HTML+JS page reads that JSON and renders animated dots + trails on Leaflet/OSM.

**Tech Stack:** Python 3.11+, `uv`, Playwright (Chromium), `playwright-stealth`, SQLite (stdlib), PyYAML, pytest, vanilla JS, Leaflet 1.9, OpenStreetMap tiles.

---

## File Structure

| Path | Purpose |
|------|---------|
| `pyproject.toml` | uv project + dependencies |
| `.gitignore` | exclude `data.sqlite`, `auth_state.json`, `logs/`, `web/data.json`, `.venv/`, `__pycache__/` |
| `config.yaml` | interval, jitter, fade window, paths |
| `trackers.yaml` | per-mascot id, name, color (hand-edited) |
| `scraper/__init__.py` | empty package marker |
| `scraper/db.py` | SQLite schema + upserts |
| `scraper/config.py` | load `config.yaml` and `trackers.yaml` |
| `scraper/parser.py` | decode Find Hub XHR response → list of positions |
| `scraper/setup_login.py` | one-time interactive login, saves `auth_state.json` |
| `scraper/scrape.py` | one full scrape cycle (Playwright + parser + db) |
| `scraper/run_loop.py` | 15-min loop with jitter, calls scrape + export |
| `export.py` | SQLite → `web/data.json` |
| `web/index.html` | page skeleton, header, map div, controls |
| `web/style.css` | styles for header, map, timeline, toggles |
| `web/app.js` | data fetch, Leaflet rendering, live + replay logic |
| `tests/test_db.py` | DB schema + upsert idempotency |
| `tests/test_config.py` | config loaders |
| `tests/test_parser.py` | parser given a captured fixture |
| `tests/test_export.py` | export shape from a fixture DB |
| `tests/fixtures/find_hub_response.json` | captured Find Hub response (created during discovery task) |
| `README.md` | quickstart, troubleshooting |
| `logs/` | rotating logs (gitignored, created at runtime) |

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `config.yaml`, `trackers.yaml`, `scraper/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "mascotes-track"
version = "0.1.0"
description = "Track three Bluetooth trackers via Google Find Hub and visualize them on a map."
requires-python = ">=3.11"
dependencies = [
  "playwright>=1.45",
  "playwright-stealth>=1.0.6",
  "pyyaml>=6.0",
]

[dependency-groups]
dev = [
  "pytest>=8.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 2: Write `.gitignore`**

```gitignore
.venv/
__pycache__/
*.pyc
data.sqlite
data.sqlite-journal
auth_state.json
logs/
web/data.json
.pytest_cache/
```

- [ ] **Step 3: Write `config.yaml`**

```yaml
interval_seconds: 900          # 15 min
jitter_seconds: 120            # ±2 min
db_path: data.sqlite
auth_state_path: auth_state.json
web_data_path: web/data.json
log_dir: logs
fade_window_seconds: 21600     # 6h trail fade
find_hub_url: https://www.google.com/android/find
response_url_substring: locations  # used to match XHR; refine in Task 6
scrape_timeout_seconds: 60
```

- [ ] **Step 4: Write `trackers.yaml` with placeholder entries**

```yaml
# Replace `id` with the device id from Find Hub once known (Task 6).
trackers:
  - id: REPLACE_ME_1
    name: Mascot 1
    color: "#e74c3c"
  - id: REPLACE_ME_2
    name: Mascot 2
    color: "#3498db"
  - id: REPLACE_ME_3
    name: Mascot 3
    color: "#2ecc71"
```

- [ ] **Step 5: Create empty `scraper/__init__.py` and `tests/__init__.py`**

Both empty files.

- [ ] **Step 6: Initialize uv environment**

Run: `uv sync`
Expected: creates `.venv/`, installs deps. No errors.

- [ ] **Step 7: Install Playwright Chromium**

Run: `uv run playwright install chromium`
Expected: download succeeds.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock .gitignore config.yaml trackers.yaml scraper/__init__.py tests/__init__.py
git commit -m "scaffold: initial project layout and dependencies"
```

---

## Task 2: Config loader (TDD)

**Files:**
- Create: `scraper/config.py`, `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:

```python
from pathlib import Path
import textwrap
from scraper.config import load_config, load_trackers

def test_load_config(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text(textwrap.dedent("""\
        interval_seconds: 900
        jitter_seconds: 120
        db_path: data.sqlite
        auth_state_path: auth_state.json
        web_data_path: web/data.json
        log_dir: logs
        fade_window_seconds: 21600
        find_hub_url: https://example
        response_url_substring: locations
        scrape_timeout_seconds: 60
    """))
    cfg = load_config(p)
    assert cfg.interval_seconds == 900
    assert cfg.fade_window_seconds == 21600
    assert cfg.find_hub_url == "https://example"

def test_load_trackers(tmp_path: Path):
    p = tmp_path / "t.yaml"
    p.write_text(textwrap.dedent("""\
        trackers:
          - id: abc
            name: Mascot 1
            color: "#e74c3c"
    """))
    ts = load_trackers(p)
    assert len(ts) == 1
    assert ts[0].id == "abc"
    assert ts[0].color == "#e74c3c"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: scraper.config`.

- [ ] **Step 3: Implement `scraper/config.py`**

```python
from dataclasses import dataclass
from pathlib import Path
from typing import List
import yaml

@dataclass(frozen=True)
class Config:
    interval_seconds: int
    jitter_seconds: int
    db_path: str
    auth_state_path: str
    web_data_path: str
    log_dir: str
    fade_window_seconds: int
    find_hub_url: str
    response_url_substring: str
    scrape_timeout_seconds: int

@dataclass(frozen=True)
class Tracker:
    id: str
    name: str
    color: str

def load_config(path: Path | str = "config.yaml") -> Config:
    data = yaml.safe_load(Path(path).read_text())
    return Config(**data)

def load_trackers(path: Path | str = "trackers.yaml") -> List[Tracker]:
    data = yaml.safe_load(Path(path).read_text())
    return [Tracker(**t) for t in data["trackers"]]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scraper/config.py tests/test_config.py
git commit -m "feat(config): typed loaders for config.yaml and trackers.yaml"
```

---

## Task 3: SQLite layer (TDD)

**Files:**
- Create: `scraper/db.py`, `tests/test_db.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_db.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `scraper/db.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scraper/db.py tests/test_db.py
git commit -m "feat(db): SQLite schema with idempotent upserts"
```

---

## Task 4: Interactive login script

**Files:**
- Create: `scraper/setup_login.py`

This is **manual** — we cannot unit-test interactive login. Verify by running.

- [ ] **Step 1: Implement `scraper/setup_login.py`**

```python
"""One-time interactive login. Opens a visible Chromium, lets the user log into
their dedicated Google account, then saves storage state to auth_state.json."""
from __future__ import annotations
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright

from scraper.config import load_config


def main() -> int:
    cfg = load_config()
    out = Path(cfg.auth_state_path)

    print("Opening Chromium. Log in to the dedicated Google account, then")
    print("navigate to Find Hub and confirm you can see all 3 trackers.")
    print("When ready, return to this terminal and press <Enter>.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.goto(cfg.find_hub_url)
        input("Press Enter to save the session and exit... ")
        context.storage_state(path=str(out))
        browser.close()

    print(f"Saved storage state to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Manual verification**

Run: `uv run python -m scraper.setup_login`
Expected: Chromium opens, you log in, navigate to Find Hub, see the 3 trackers, return to terminal, press Enter. `auth_state.json` is created.

> **STOP — do not proceed past this task until the user has run the login script and confirmed all 3 trackers are visible in Find Hub. Discovery (Task 5) requires a working session.**

- [ ] **Step 3: Commit**

```bash
git add scraper/setup_login.py
git commit -m "feat(scraper): one-time interactive login that saves storage state"
```

---

## Task 5: Discovery — capture a real Find Hub response

This task is **collaborative with the user**. Goal: identify which XHR carries device locations and capture a real response as a test fixture.

**Files:**
- Create: `tests/fixtures/find_hub_response.json` (or `.bin` if protobuf)
- Create: `tests/fixtures/README.md`
- May modify: `config.yaml` `response_url_substring`, `trackers.yaml` real ids

- [ ] **Step 1: Write a temporary capture script `scraper/_discover.py`**

```python
"""Throwaway: log every XHR response URL while Find Hub loads, dump bodies that
look like locations into tests/fixtures/."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
from scraper.config import load_config

OUT = Path("tests/fixtures")
OUT.mkdir(parents=True, exist_ok=True)

def main() -> None:
    cfg = load_config()
    captured = []

    def on_response(resp):
        url = resp.url
        try:
            ct = resp.headers.get("content-type", "")
        except Exception:
            ct = ""
        try:
            body = resp.body()
        except Exception:
            return
        captured.append((url, ct, len(body)))
        # Heuristic: dump anything with a candidate substring.
        for needle in ("location", "find", "device", "spot"):
            if needle in url.lower():
                safe = url.replace("/", "_").replace(":", "_")[:120]
                (OUT / f"{safe}.bin").write_bytes(body)
                break

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(storage_state=cfg.auth_state_path)
        page = context.new_page()
        page.on("response", on_response)
        page.goto(cfg.find_hub_url)
        input("Wait until all 3 trackers show on the map, then press Enter... ")
        browser.close()

    Path(OUT / "_index.json").write_text(json.dumps(captured, indent=2))
    print(f"Captured {len(captured)} responses; index in {OUT/'_index.json'}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run discovery**

Run: `uv run python -m scraper._discover`
Expected: dumps candidate response bodies into `tests/fixtures/`.

- [ ] **Step 3: With the user, identify the right response**

Inspect dumped files. The right one contains 3 lat/lon pairs and timestamps. If it's JSON, great. If it's a protobuf, decode using `protoc --decode_raw < file` to discover field structure.

- [ ] **Step 4: Capture the chosen fixture and document**

- Save the chosen body as `tests/fixtures/find_hub_response.json` (or `.bin`).
- Create `tests/fixtures/README.md` describing: the URL pattern that returned it, the content-type, and the field-to-meaning mapping (which field is lat, which is lon, which is unix-millis timestamp, which is accuracy in meters, which is the device id).
- Update `config.yaml` `response_url_substring` to a unique substring of the real URL.
- Update `trackers.yaml` with the three real device ids.

- [ ] **Step 5: Delete the discovery script**

```bash
rm scraper/_discover.py
```

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures config.yaml trackers.yaml
git commit -m "discovery: capture Find Hub locations response fixture"
```

---

## Task 6: Parser (TDD against the captured fixture)

**Files:**
- Create: `scraper/parser.py`, `tests/test_parser.py`

The exact field names below are placeholders — the engineer running this task must replace them with the field names documented in `tests/fixtures/README.md` from Task 5. The structure (function signature, test shape) does not change.

- [ ] **Step 1: Write the failing test using the captured fixture**

`tests/test_parser.py`:

```python
from pathlib import Path
from scraper.parser import parse_locations

FIXTURE = Path("tests/fixtures/find_hub_response.json")

def test_parses_three_trackers():
    body = FIXTURE.read_bytes()
    positions = parse_locations(body)
    # The fixture was captured with all 3 trackers visible.
    ids = {p.tracker_id for p in positions}
    assert len(ids) == 3
    for p in positions:
        assert -90 <= p.lat <= 90
        assert -180 <= p.lon <= 180
        assert p.ts > 1_700_000_000  # plausible unix seconds
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_parser.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `scraper/parser.py`**

If the fixture is **JSON**, use this template (adjust field names per `tests/fixtures/README.md`):

```python
"""Decode a Find Hub locations response into Position objects.

The exact field names below MUST match what was documented in
tests/fixtures/README.md during the discovery task. If Find Hub
changes its format, only this file needs updating.
"""
from __future__ import annotations
from typing import List
import json

from scraper.db import Position


def parse_locations(body: bytes) -> List[Position]:
    data = json.loads(body)
    out: List[Position] = []
    # ADAPT: replace `devices`, `id`, `lat`, `lon`, `accuracy`, `ts_ms` with
    # the real field names from tests/fixtures/README.md.
    for entry in data["devices"]:
        out.append(Position(
            tracker_id=entry["id"],
            ts=int(entry["ts_ms"]) // 1000,
            lat=float(entry["lat"]),
            lon=float(entry["lon"]),
            accuracy_m=float(entry["accuracy"]) if "accuracy" in entry else None,
        ))
    return out
```

If the fixture is **protobuf**, use `blackboxprotobuf` (add to deps) to parse the raw bytes; the test shape stays identical.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_parser.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add scraper/parser.py tests/test_parser.py
git commit -m "feat(parser): decode Find Hub locations response"
```

---

## Task 7: One scrape cycle

**Files:**
- Create: `scraper/scrape.py`

Manually verified end-to-end (Playwright integration is not unit-tested per spec).

- [ ] **Step 1: Implement `scraper/scrape.py`**

```python
"""Run one scrape cycle: open Find Hub, capture the locations XHR, parse,
upsert into SQLite. Idempotent — safe to call repeatedly."""
from __future__ import annotations
import logging
from pathlib import Path
from typing import List

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
try:
    from playwright_stealth import stealth_sync
except ImportError:  # older versions
    stealth_sync = None

from scraper.config import Config, Tracker, load_config, load_trackers
from scraper.db import Database, Position
from scraper.parser import parse_locations

log = logging.getLogger(__name__)


class ScrapeError(Exception):
    pass


def scrape_once(cfg: Config | None = None,
                trackers: List[Tracker] | None = None) -> int:
    cfg = cfg or load_config()
    trackers = trackers or load_trackers()

    auth = Path(cfg.auth_state_path)
    if not auth.exists():
        raise ScrapeError(f"No auth_state at {auth}; run scraper.setup_login first")

    db = Database(cfg.db_path)
    db.init_schema()
    db.seed_trackers(trackers)

    captured_bodies: list[bytes] = []

    def on_response(resp):
        if cfg.response_url_substring in resp.url:
            try:
                captured_bodies.append(resp.body())
            except Exception:
                log.warning("could not read body for %s", resp.url)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            storage_state=str(auth),
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        if stealth_sync:
            stealth_sync(page)
        page.on("response", on_response)
        try:
            page.goto(cfg.find_hub_url, timeout=cfg.scrape_timeout_seconds * 1000)
            # Wait up to scrape_timeout_seconds for at least one matching response.
            page.wait_for_timeout(cfg.scrape_timeout_seconds * 1000)
        except PWTimeout as e:
            raise ScrapeError(f"page timeout: {e}") from e
        finally:
            browser.close()

    if not captured_bodies:
        raise ScrapeError(
            "no XHR responses matched response_url_substring="
            f"{cfg.response_url_substring!r}"
        )

    positions: list[Position] = []
    for body in captured_bodies:
        try:
            positions.extend(parse_locations(body))
        except Exception:
            log.exception("failed to parse response body (len=%d)", len(body))

    inserted = db.insert_positions(positions)
    log.info("scrape ok: %d positions parsed, %d new", len(positions), inserted)
    return inserted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    n = scrape_once()
    print(f"Inserted {n} new positions")
```

- [ ] **Step 2: Manual verification**

Run: `uv run python -m scraper.scrape`
Expected: Chromium opens briefly, log says "scrape ok: N positions parsed, M new", and `data.sqlite` is created with rows for all 3 trackers.

Verify with:

```bash
sqlite3 data.sqlite "SELECT tracker_id, datetime(ts,'unixepoch'), lat, lon FROM positions ORDER BY ts DESC LIMIT 10;"
```

Expected: at most 3 rows (one per tracker) with plausible coordinates.

- [ ] **Step 3: Commit**

```bash
git add scraper/scrape.py
git commit -m "feat(scrape): one full scrape cycle with stealth and response capture"
```

---

## Task 8: Exporter (TDD)

**Files:**
- Create: `export.py`, `tests/test_export.py`

- [ ] **Step 1: Write the failing test**

`tests/test_export.py`:

```python
import json
from pathlib import Path
from scraper.config import Tracker
from scraper.db import Database, Position
from export import export_json

def test_export_shape(tmp_path: Path):
    db_path = tmp_path / "x.sqlite"
    out = tmp_path / "data.json"
    db = Database(db_path)
    db.init_schema()
    db.seed_trackers([
        Tracker("a", "Mascot 1", "#e74c3c"),
        Tracker("b", "Mascot 2", "#3498db"),
    ])
    db.insert_positions([
        Position("a", 1000, 40.0, -3.0, 12.0),
        Position("a", 2000, 40.001, -3.001, 8.0),
        Position("b", 1500, 40.5, -3.5, None),
    ])
    export_json(db_path, out, generated_at=9999)
    data = json.loads(out.read_text())
    assert data["generated_at"] == 9999
    by_id = {t["id"]: t for t in data["trackers"]}
    assert by_id["a"]["name"] == "Mascot 1"
    assert by_id["a"]["color"] == "#e74c3c"
    assert by_id["a"]["positions"] == [
        [1000, 40.0, -3.0, 12.0],
        [2000, 40.001, -3.001, 8.0],
    ]
    assert by_id["b"]["positions"] == [[1500, 40.5, -3.5, None]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_export.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `export.py`**

```python
"""Dump SQLite contents into a compact JSON file consumed by web/app.js."""
from __future__ import annotations
from pathlib import Path
import json
import time
from typing import Optional

from scraper.db import Database


def export_json(db_path: Path | str,
                out_path: Path | str,
                generated_at: Optional[int] = None) -> None:
    db = Database(db_path)
    generated_at = int(generated_at if generated_at is not None else time.time())

    trackers_meta = db.list_trackers()  # [(id, name, color), ...]
    payload = {"generated_at": generated_at, "trackers": []}
    for tid, name, color in trackers_meta:
        rows = db.positions_for(tid)
        payload["trackers"].append({
            "id": tid,
            "name": name,
            "color": color,
            "positions": [[p.ts, p.lat, p.lon, p.accuracy_m] for p in rows],
        })

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, separators=(",", ":")))


if __name__ == "__main__":
    from scraper.config import load_config
    cfg = load_config()
    export_json(cfg.db_path, cfg.web_data_path)
    print(f"Wrote {cfg.web_data_path}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_export.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add export.py tests/test_export.py
git commit -m "feat(export): SQLite to compact data.json"
```

---

## Task 9: Run loop with jitter

**Files:**
- Create: `scraper/run_loop.py`

- [ ] **Step 1: Implement `scraper/run_loop.py`**

```python
"""Long-lived loop: scrape every interval ± jitter, export, sleep."""
from __future__ import annotations
import logging
import logging.handlers
import random
import sys
import time
from pathlib import Path

from scraper.config import load_config, load_trackers
from scraper.scrape import scrape_once, ScrapeError
from export import export_json


def configure_logging(log_dir: str) -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        Path(log_dir) / "scrape.log",
        maxBytes=2_000_000,
        backupCount=5,
    )
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)


def main() -> int:
    cfg = load_config()
    trackers = load_trackers()
    configure_logging(cfg.log_dir)
    log = logging.getLogger("run_loop")

    consecutive_failures = 0
    while True:
        try:
            inserted = scrape_once(cfg, trackers)
            export_json(cfg.db_path, cfg.web_data_path)
            log.info("cycle ok: %d new positions", inserted)
            consecutive_failures = 0
        except ScrapeError as e:
            consecutive_failures += 1
            log.warning("scrape failed (%d in a row): %s", consecutive_failures, e)
        except Exception:
            consecutive_failures += 1
            log.exception("unexpected error (%d in a row)", consecutive_failures)

        # Back off on repeated failures: double the wait, cap at 1h.
        base = cfg.interval_seconds * (2 ** min(consecutive_failures, 3))
        base = min(base, 3600)
        jitter = random.uniform(-cfg.jitter_seconds, cfg.jitter_seconds)
        sleep_for = max(60, base + jitter)
        log.info("sleeping %.0fs", sleep_for)
        time.sleep(sleep_for)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Manual smoke test (single cycle)**

Run for 30 seconds then Ctrl-C: `uv run python -m scraper.run_loop`
Expected: log file appears under `logs/`, one cycle runs, sleep begins.

- [ ] **Step 3: Commit**

```bash
git add scraper/run_loop.py
git commit -m "feat(loop): jittered scrape loop with rotating logs and back-off"
```

---

## Task 10: Web — page skeleton

**Files:**
- Create: `web/index.html`, `web/style.css`

- [ ] **Step 1: Write `web/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Mascot Tracker</title>
  <link rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
        crossorigin="" />
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <header>
    <h1>🐾 Mascot Tracker</h1>
    <div class="modes">
      <button id="mode-live" class="active">● Live</button>
      <button id="mode-replay">↻ Replay</button>
    </div>
  </header>
  <main>
    <div id="map"></div>
    <div id="controls">
      <div id="timeline" hidden>
        <button id="play">▶</button>
        <input id="scrub" type="range" min="0" max="100" value="100" />
        <span id="clock">—</span>
        <select id="speed">
          <option value="1">1×</option>
          <option value="4" selected>4×</option>
          <option value="16">16×</option>
        </select>
      </div>
      <div id="toggles"></div>
    </div>
  </main>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
          integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
          crossorigin=""></script>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `web/style.css`**

```css
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; font-family: system-ui, sans-serif; }
body { display: flex; flex-direction: column; }
header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.5rem 1rem; background: #111; color: #fafafa;
}
header h1 { margin: 0; font-size: 1.1rem; }
.modes button {
  background: transparent; color: #ccc; border: 1px solid #333;
  padding: 0.3rem 0.7rem; margin-left: 0.4rem; cursor: pointer;
  border-radius: 3px;
}
.modes button.active { color: #fff; border-color: #fff; }
main { flex: 1; display: flex; flex-direction: column; min-height: 0; }
#map { flex: 1; min-height: 0; }
#controls {
  background: #1c1c1c; color: #fafafa; padding: 0.5rem 1rem;
  display: flex; flex-direction: column; gap: 0.4rem;
}
#timeline { display: flex; align-items: center; gap: 0.6rem; }
#timeline input[type=range] { flex: 1; }
#toggles { display: flex; gap: 0.7rem; flex-wrap: wrap; }
.toggle {
  display: inline-flex; align-items: center; gap: 0.3rem;
  padding: 0.2rem 0.5rem; border: 1px solid #333; border-radius: 3px;
  cursor: pointer; user-select: none;
}
.toggle.off { opacity: 0.4; }
.toggle .swatch {
  width: 12px; height: 12px; border-radius: 50%;
}
.mascot-dot {
  border-radius: 50%; border: 2px solid white;
  box-shadow: 0 0 8px rgba(0,0,0,0.5);
  animation: pulse 2s infinite;
}
@keyframes pulse {
  0% { transform: scale(1); }
  50% { transform: scale(1.15); }
  100% { transform: scale(1); }
}
```

- [ ] **Step 3: Verify it loads**

Run: `python -m http.server -d web 8000 &` then open `http://localhost:8000` (note: this assumes `web/data.json` exists or the page must tolerate absence — Task 11 handles that).

Expected: page renders header and an empty grey map area (Leaflet not initialized yet — fine).

- [ ] **Step 4: Commit**

```bash
git add web/index.html web/style.css
git commit -m "feat(web): page skeleton with Leaflet and controls layout"
```

---

## Task 11: Web — data fetch + dots

**Files:**
- Create: `web/app.js`

- [ ] **Step 1: Write the initial `web/app.js`**

```javascript
const MAP = L.map('map').setView([40.4168, -3.7038], 13);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap'
}).addTo(MAP);

const state = {
  trackers: [],            // [{id, name, color, positions: [[ts,lat,lon,acc], ...]}]
  visible: new Set(),      // tracker ids currently shown
  mode: 'live',            // 'live' | 'replay'
  replay: { ts: null, playing: false, speed: 4 },
  layers: new Map(),       // tracker_id -> { dot, trail }
  fittedOnce: false,
};

function dotIcon(color) {
  return L.divIcon({
    className: '',
    iconSize: [16, 16],
    html: `<div class="mascot-dot" style="width:16px;height:16px;background:${color}"></div>`,
  });
}

function clearLayers() {
  for (const { dot, trail } of state.layers.values()) {
    if (dot) MAP.removeLayer(dot);
    if (trail) MAP.removeLayer(trail);
  }
  state.layers.clear();
}

function renderLive() {
  clearLayers();
  const allPoints = [];
  for (const t of state.trackers) {
    if (!state.visible.has(t.id) || t.positions.length === 0) continue;
    const last = t.positions[t.positions.length - 1];
    const [ts, lat, lon, acc] = last;
    const dot = L.marker([lat, lon], { icon: dotIcon(t.color) }).addTo(MAP);
    const ageMin = Math.round((Date.now() / 1000 - ts) / 60);
    dot.bindPopup(
      `<b>${t.name}</b><br/>seen ${ageMin} min ago` +
      (acc != null ? `<br/>±${Math.round(acc)} m` : ''));
    state.layers.set(t.id, { dot, trail: null });
    allPoints.push([lat, lon]);
  }
  if (!state.fittedOnce && allPoints.length) {
    MAP.fitBounds(allPoints, { padding: [40, 40] });
    state.fittedOnce = true;
  }
}

function renderToggles() {
  const root = document.getElementById('toggles');
  root.innerHTML = '';
  for (const t of state.trackers) {
    const el = document.createElement('span');
    el.className = 'toggle' + (state.visible.has(t.id) ? '' : ' off');
    el.innerHTML = `<span class="swatch" style="background:${t.color}"></span>${t.name}`;
    el.onclick = () => {
      if (state.visible.has(t.id)) state.visible.delete(t.id);
      else state.visible.add(t.id);
      renderToggles();
      render();
    };
    root.appendChild(el);
  }
}

function render() {
  if (state.mode === 'live') renderLive();
  // replay rendering added in Task 13
}

async function fetchData() {
  try {
    const r = await fetch('data.json?_=' + Date.now());
    if (!r.ok) return;
    const data = await r.json();
    const knownIds = new Set(state.trackers.map(t => t.id));
    state.trackers = data.trackers;
    for (const t of state.trackers) if (!knownIds.has(t.id)) state.visible.add(t.id);
    renderToggles();
    render();
  } catch (e) {
    console.warn('fetch failed', e);
  }
}

fetchData();
setInterval(fetchData, 30_000);
```

- [ ] **Step 2: Manual verification**

With `web/data.json` present (run `uv run python export.py` after a successful scrape), serve and open in browser:

```bash
python -m http.server -d web 8000
```

Expected: map auto-fits to the trackers; three pulsing colored dots; clicking a toggle hides/shows a dot.

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat(web): live mode with pulsing dots and per-mascot toggles"
```

---

## Task 12: Web — fading trails

**Files:**
- Modify: `web/app.js`

Trails are rendered as a series of short polyline segments where each segment's opacity is a function of how recent both endpoints are, so older parts fade.

- [ ] **Step 1: Replace `renderLive` and add `renderTrail`**

In `web/app.js`, replace the existing `renderLive` function with:

```javascript
const FADE_WINDOW_S = 6 * 3600;  // 6h, matches config default

function renderTrail(t, nowTs) {
  const segs = [];
  const pts = t.positions;
  for (let i = 1; i < pts.length; i++) {
    const [ts0, lat0, lon0] = pts[i - 1];
    const [ts1, lat1, lon1] = pts[i];
    const ageS = nowTs - ts1;
    if (ageS > FADE_WINDOW_S) continue;
    const opacity = Math.max(0.05, 1 - ageS / FADE_WINDOW_S);
    segs.push(L.polyline([[lat0, lon0], [lat1, lon1]], {
      color: t.color, weight: 4, opacity,
    }));
  }
  return L.layerGroup(segs);
}

function renderLive() {
  clearLayers();
  const nowTs = Math.floor(Date.now() / 1000);
  const allPoints = [];
  for (const t of state.trackers) {
    if (!state.visible.has(t.id) || t.positions.length === 0) continue;
    const trail = renderTrail(t, nowTs).addTo(MAP);
    const last = t.positions[t.positions.length - 1];
    const [ts, lat, lon, acc] = last;
    const dot = L.marker([lat, lon], { icon: dotIcon(t.color) }).addTo(MAP);
    const ageMin = Math.round((Date.now() / 1000 - ts) / 60);
    dot.bindPopup(
      `<b>${t.name}</b><br/>seen ${ageMin} min ago` +
      (acc != null ? `<br/>±${Math.round(acc)} m` : ''));
    state.layers.set(t.id, { dot, trail });
    for (const p of t.positions) allPoints.push([p[1], p[2]]);
  }
  if (!state.fittedOnce && allPoints.length) {
    MAP.fitBounds(allPoints, { padding: [40, 40] });
    state.fittedOnce = true;
  }
}
```

- [ ] **Step 2: Manual verification**

Reload the page. Expected: each tracker has a trail behind its dot. Older portions are more transparent. (May not be visible until at least 2 points exist per tracker — i.e., after the second scrape cycle.)

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat(web): fading polyline trails behind each dot"
```

---

## Task 13: Web — replay mode

**Files:**
- Modify: `web/app.js`

- [ ] **Step 1: Add replay rendering and mode switching**

Append to `web/app.js`:

```javascript
function timeRange() {
  let lo = Infinity, hi = -Infinity;
  for (const t of state.trackers) {
    for (const p of t.positions) {
      if (p[0] < lo) lo = p[0];
      if (p[0] > hi) hi = p[0];
    }
  }
  if (lo === Infinity) return null;
  return [lo, hi];
}

function positionsUpTo(t, ts) {
  const out = [];
  for (const p of t.positions) {
    if (p[0] <= ts) out.push(p);
    else break;
  }
  return out;
}

function renderReplay() {
  clearLayers();
  const ts = state.replay.ts;
  if (ts == null) return;
  for (const t of state.trackers) {
    if (!state.visible.has(t.id)) continue;
    const subset = positionsUpTo(t, ts);
    if (subset.length === 0) continue;
    const fakeT = { ...t, positions: subset };
    const trail = renderTrail(fakeT, ts).addTo(MAP);
    const last = subset[subset.length - 1];
    const dot = L.marker([last[1], last[2]], { icon: dotIcon(t.color) }).addTo(MAP);
    state.layers.set(t.id, { dot, trail });
  }
  document.getElementById('clock').textContent =
    new Date(ts * 1000).toLocaleString();
}

const origRender = render;
render = function () {
  if (state.mode === 'live') renderLive();
  else renderReplay();
};

document.getElementById('mode-live').onclick = () => {
  state.mode = 'live';
  document.getElementById('mode-live').classList.add('active');
  document.getElementById('mode-replay').classList.remove('active');
  document.getElementById('timeline').hidden = true;
  render();
};

document.getElementById('mode-replay').onclick = () => {
  const range = timeRange();
  if (!range) return;
  state.mode = 'replay';
  state.replay.ts = range[1];
  document.getElementById('mode-replay').classList.add('active');
  document.getElementById('mode-live').classList.remove('active');
  document.getElementById('timeline').hidden = false;
  render();
};

document.getElementById('scrub').addEventListener('input', (e) => {
  const range = timeRange();
  if (!range) return;
  const frac = Number(e.target.value) / 100;
  state.replay.ts = Math.round(range[0] + (range[1] - range[0]) * frac);
  render();
});

document.getElementById('speed').addEventListener('change', (e) => {
  state.replay.speed = Number(e.target.value);
});

document.getElementById('play').addEventListener('click', () => {
  state.replay.playing = !state.replay.playing;
  document.getElementById('play').textContent = state.replay.playing ? '⏸' : '▶';
});

setInterval(() => {
  if (state.mode !== 'replay' || !state.replay.playing) return;
  const range = timeRange();
  if (!range) return;
  state.replay.ts = Math.min(range[1], state.replay.ts + 60 * state.replay.speed);
  const frac = (state.replay.ts - range[0]) / (range[1] - range[0]);
  document.getElementById('scrub').value = String(Math.round(frac * 100));
  render();
  if (state.replay.ts >= range[1]) state.replay.playing = false;
}, 1000);
```

- [ ] **Step 2: Manual verification**

Click Replay. Expected: scrub bar appears, dragging it shows historical positions, ▶ animates from start to end at chosen speed, ⏸ pauses.

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat(web): replay mode with scrub and play/pause"
```

---

## Task 14: README and end-to-end manual verification

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# Mascotes Track

Track three Bluetooth tags (Google Find Hub) and visualize their movement
on a local web page.

## Setup

```bash
uv sync
uv run playwright install chromium
```

Edit `trackers.yaml` with your three device ids (filled in during the
discovery step) and chosen colors.

## One-time login

```bash
uv run python -m scraper.setup_login
```

A Chromium window opens. Log in to your dedicated Google account, navigate
to Find Hub, confirm all 3 trackers are visible, return to the terminal,
and press Enter. This writes `auth_state.json`.

## Run the scrape loop

```bash
uv run python -m scraper.run_loop
```

The loop scrapes every ~15 minutes (with ±2 min jitter), upserts into
`data.sqlite`, and rewrites `web/data.json`.

For unattended operation use `tmux` or a `systemd --user` unit.

## View the map

```bash
python -m http.server -d web 8000
```

Open http://localhost:8000 in a browser.

## Troubleshooting

- **`No auth_state at ...`** — run `setup_login` first.
- **`no XHR responses matched ...`** — Find Hub changed its endpoint URL;
  redo the discovery step (re-create `scraper/_discover.py` from git
  history of `docs/superpowers/plans/`), capture a fresh fixture, update
  `config.yaml: response_url_substring` and `scraper/parser.py`.
- **Login challenge / CAPTCHA** — log shows it; the loop backs off and
  retries. If it persists, re-run `setup_login`.

## Layout

- `scraper/` — Playwright-based scraper, parser, DB, run loop
- `export.py` — SQLite → `web/data.json`
- `web/` — static page (Leaflet + OSM)
- `tests/` — unit tests for parser / DB / export / config
- `docs/superpowers/` — design + plan
```

- [ ] **Step 2: End-to-end verification**

Run all tests:

```bash
uv run pytest -v
```

Expected: all green.

Run one cycle:

```bash
uv run python -m scraper.scrape
uv run python export.py
```

Expected: `data.sqlite` has rows; `web/data.json` exists.

Serve and view:

```bash
python -m http.server -d web 8000
```

Open `http://localhost:8000`. Expected: three pulsing dots on a Madrid-area
map (or wherever the trackers are), per-mascot toggles work, replay mode
shows the scrub bar and the play button animates.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup, run, and troubleshooting"
```

---

## Self-review summary

- **Spec coverage:** all spec sections (architecture, anti-flagging, scraper
  internals incl. discovery, schema, scheduling, web layout, data.json
  shape, repo layout, ops) map to tasks 1–14.
- **No placeholders:** every step contains code or an exact command. The
  one acknowledged unknown — Find Hub's response field names — is handled
  by Task 5 (discovery) feeding documented field mappings into Task 6.
- **Type consistency:** `Position`, `Tracker`, `Database`, `parse_locations`,
  `scrape_once`, `export_json`, `clearLayers`, `renderTrail`,
  `renderLive`, `renderReplay` are used consistently across tasks.
