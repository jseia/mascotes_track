# Session Handoff — 2026-05-08

This document captures the brainstorm, decisions, and current progress so
work can continue on a local laptop. The full design lives in
`docs/superpowers/specs/2026-05-07-mascotes-track-design.md`; the full
implementation plan lives in
`docs/superpowers/plans/2026-05-07-mascotes-track.md`. This file is the
short version you read first.

## Project goal

Track three Bluetooth Android trackers (Amazon-bought, work via Google
Find Hub) around a city during a weekend-long game. Scrape their
positions every ~15 min, store in SQLite, render a static web page
with three colored dots animating over a Leaflet map and leaving
fading trails. Local-only for v1; web layer designed to be hosted
publicly later.

## Decisions locked in during brainstorming

- **Data source:** Google Find Hub web UI scraped with
  Playwright/Chromium. No public API exists.
- **Anti-flagging:** dedicated Google account (not main), one
  interactive login persisted as `auth_state.json`, real Chromium with
  `playwright-stealth`, stable UA + viewport, single fixed IP, 15-min
  interval with ±2 min jitter, exponential back-off on failures, no
  parallel sessions.
- **Storage:** SQLite, schema in
  `docs/superpowers/specs/2026-05-07-mascotes-track-design.md`.
- **Visualization:** Leaflet + OpenStreetMap (no API key). Vanilla JS,
  no build step. Live mode + replay scrub bar + per-mascot toggles +
  fading polyline trails.
- **Hosting (now):** localhost only, organizer-only viewer.
- **Hosting (future):** static-host friendly — `web/` is a static
  page reading `web/data.json`, can be lifted to Netlify / GitHub
  Pages / S3 with no scraper changes.

## What is done (commits on `main`)

| # | Commit | Task |
|---|--------|------|
| 1 | `369cbd6` | Design spec |
| 2 | `b8e76f4` | Implementation plan |
| 3 | `1ca396d` | Task 1 — project scaffold (`pyproject.toml`, `.gitignore`, `config.yaml`, `trackers.yaml`, packages) |
| 4 | `058d7ae` | Task 1 — `uv.lock` |
| 5 | `b942f85` | Task 2 — `scraper/config.py` typed loaders + tests |
| 6 | `d6efcd4` | Task 3 — `scraper/db.py` SQLite layer + tests |
| 7 | `b9ee9d4` | Task 4 step 1 — `scraper/setup_login.py` (file written, NOT yet run) |

All tests (`uv run pytest`) pass at this point: 6 passed.

`uv sync` and `uv run playwright install chromium` were both run on the
methinks NAS server; on a fresh clone you must re-run them locally.

## Why we stopped

Task 4 step 2 needs an interactive Chromium window. The methinks NAS
server is headless (no X server / `$DISPLAY`), so running
`uv run python -m scraper.setup_login` failed with
`Missing X server or $DISPLAY`. Decision: continue on a local laptop
with a real desktop session.

## Resume on the laptop

```bash
git clone https://github.com/jseia/mascotes_track.git
cd mascotes_track
uv sync
uv run playwright install chromium
uv run pytest          # sanity check: 6 tests pass
```

### Pre-login prep

1. Create or pick a **dedicated Google account** (not your main one).
2. On a real Android phone, install **Google Find My Device / Find
   Hub** while logged into that dedicated account.
3. Pair the 3 trackers to that account.
4. Confirm in the Android app that all 3 trackers report a location.

### Run the one-time login (Task 4 step 2)

```bash
uv run python -m scraper.setup_login
```

A Chromium window opens at `https://www.google.com/android/find`. In
that window:

- Log in with the dedicated account.
- Wait until **all 3 trackers** appear on the map with locations.
- Return to the terminal and press **Enter**.

The script prints `Saved storage state to auth_state.json`. That file
is gitignored — never commit it.

Then commit the file change (none expected — `setup_login.py` was
already committed; only `auth_state.json` was created and is ignored):

```bash
git status   # should be clean
```

## Next: Task 5 — Discovery (collaborative)

Goal: identify which XHR carries the device locations, capture a
real response as `tests/fixtures/find_hub_response.json` (or `.bin` if
protobuf), and document its field-to-meaning mapping in
`tests/fixtures/README.md`.

Open `docs/superpowers/plans/2026-05-07-mascotes-track.md` → Task 5.

The plan tells you to write a throwaway `scraper/_discover.py` that
logs every XHR while Find Hub loads and dumps candidate bodies to
`tests/fixtures/`. Run it with the `auth_state.json` you just created.
Then with Claude (or by hand), pick the response that contains 3
lat/lon pairs and document its structure.

When that fixture is captured, Tasks 6–14 can resume normally:

| # | Task |
|---|------|
| 6 | Parser (TDD against the captured fixture) |
| 7 | One scrape cycle |
| 8 | Exporter (TDD) |
| 9 | Run loop with jitter + rotating logs |
| 10 | Web — page skeleton |
| 11 | Web — data fetch + dots |
| 12 | Web — fading trails |
| 13 | Web — replay mode |
| 14 | README + end-to-end manual verification |

Tasks 6, 8 are pure TDD (unit-testable). Tasks 7, 9, 10–14 are
integration / UI (manual verification per the plan).

## Useful commands

```bash
uv run pytest -v                              # run all tests
uv run python -m scraper.setup_login          # one-time interactive login
uv run python -m scraper.scrape               # (after Task 7) one scrape cycle
uv run python -m scraper.run_loop             # (after Task 9) the 15-min loop
uv run python export.py                       # (after Task 8) regenerate web/data.json
python -m http.server -d web 8000             # (after Task 10) serve the page

sqlite3 data.sqlite \
  "SELECT tracker_id, datetime(ts,'unixepoch'), lat, lon FROM positions
   ORDER BY ts DESC LIMIT 10;"
```

## Files / paths quick reference

```
mascotes_track/
├── docs/
│   ├── session-handoff.md                    # this file
│   └── superpowers/
│       ├── specs/2026-05-07-mascotes-track-design.md
│       └── plans/2026-05-07-mascotes-track.md
├── scraper/
│   ├── config.py            # done
│   ├── db.py                # done
│   ├── setup_login.py       # done (not yet run)
│   ├── parser.py            # Task 6
│   ├── scrape.py            # Task 7
│   └── run_loop.py          # Task 9
├── tests/
│   ├── test_config.py       # done
│   ├── test_db.py           # done
│   ├── test_parser.py       # Task 6
│   ├── test_export.py       # Task 8
│   └── fixtures/            # Task 5 (collaborative)
├── web/                     # Tasks 10–13
├── export.py                # Task 8
├── config.yaml              # done
├── trackers.yaml            # done (placeholder ids — replace in Task 5)
├── pyproject.toml           # done
└── README.md                # Task 14
```

## Open questions / things to revisit later

- **Hosting decision.** Once the system is working, decide where the
  scrape loop runs during the actual game weekend (laptop, Pi, the NAS
  with `xvfb-run` for headless headed mode, or a small VPS — note that
  datacenter IPs are higher flag-risk for Google).
- **`response_url_substring`** in `config.yaml` is a placeholder
  (`locations`); Task 5 must replace it with a unique substring of the
  real Find Hub locations endpoint URL.
- **Tracker device ids** in `trackers.yaml` are placeholders; Task 5
  must replace them with the real ids from the captured response.
