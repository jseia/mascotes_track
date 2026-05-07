# Mascotes Track — Design

**Date:** 2026-05-07
**Status:** Approved (brainstorming)

## Goal

Track three Bluetooth Android trackers (sold via Amazon, working through
Google's Find Hub network) around a city during a weekend-long game.
Persist their positions every ~15 minutes and visualize their movement
on a local web page with three colored dots animating over a city map
and leaving fading trails behind them.

The system runs locally for the first iteration (the organizer's Linux
box or laptop). The web layer must be host-portable so it can later be
deployed to a public site without changes to the data pipeline.

## Constraints

- **No public API for Google Find Hub.** Location data must be obtained
  by automating the Find Hub web UI with a browser.
- **Account flagging is the dominant risk.** Anti-detection measures
  must be designed in from the start.
- **15-minute resolution** is sufficient — no real-time requirement.
- **One organizer-only viewer** for v1; public access is a future goal.
- **Hosting decision deferred:** design for local execution, but keep
  the web output as a static page + JSON file so it can be hosted
  anywhere later.

## Architecture

```
[ Google Find Hub web UI ]
            │  (Playwright + persisted login session)
            ▼
   scraper.py  ──writes──▶  data.sqlite
                                │
                                ▼
                          export.py  ──writes──▶  web/data.json
                                                       │
                                                       ▼
                                              web/  (static HTML+JS,
                                                     Leaflet + OSM)
```

Three loosely coupled parts:

1. **Scraper** — Playwright-driven Chromium that opens Find Hub, captures
   the XHR responses containing device locations, and appends rows to
   SQLite. Runs in a long-lived loop with jittered ~15 min interval.
2. **Exporter** — after each successful scrape, regenerates a compact
   `web/data.json` from SQLite.
3. **Web** — static HTML + vanilla JS + Leaflet + OpenStreetMap tiles,
   served locally by `python -m http.server` for now.

A one-time **interactive login** script seeds Playwright's
`auth_state.json` so the loop never has to log in again unless Google
invalidates the session.

## Anti-Flagging Measures

These are explicit requirements, not nice-to-haves:

- A **dedicated Google account** paired with the trackers — never the
  organizer's main account.
- **Single interactive login**, then reuse the persisted browser
  storage state (cookies + localStorage) on every cycle so the session
  looks continuous.
- **Real Chromium** (not headless-detectable). Apply
  `playwright-stealth` patches: hide `navigator.webdriver`, normalize
  WebGL/UA fingerprints.
- **Stable user-agent and viewport**, persisted.
- **15-minute interval with ±2 minute random jitter** — no perfect cron
  heartbeat.
- **Single fixed IP** (the organizer's machine). No VPN/datacenter.
- **Graceful failure on challenge:** if a login challenge or CAPTCHA
  appears, log it, skip the cycle, and back off (longer wait before
  retry). Never hammer.
- **No parallel sessions.** One browser at a time.
- **Realistic navigation:** open `google.com/find`, let it settle,
  then read responses — never call internal endpoints directly.

## Scraper Internals

Cycle:

1. Launch Chromium with `storage_state=auth_state.json`.
2. Register `page.on("response", ...)` matching the Find Hub locations
   endpoint URL pattern.
3. Navigate to `google.com/find` (or whichever URL Find Hub resolves to).
4. Wait until the handler captures responses for all 3 trackers, with
   a 60-second timeout.
5. Parse `{tracker_id, lat, lon, accuracy_m, ts}` per device.
6. Upsert into SQLite (idempotent on `(tracker_id, ts)`).
7. Close browser.

**Caveat — first-run discovery step.** The exact request URL and
response format are not publicly documented and may be a protobuf. The
first time the system is built, the developer (with the user) will
manually open Find Hub with DevTools, identify the right XHR, and
decode its payload. The matching pattern and decoder live in a single
small module (`scraper/parser.py`) so future format changes are
contained to one file.

### Schema

```sql
CREATE TABLE trackers (
  id    TEXT PRIMARY KEY,   -- Google's device id
  name  TEXT NOT NULL,      -- friendly name ("Mascot 1")
  color TEXT NOT NULL       -- hex for the map dot
);

CREATE TABLE positions (
  tracker_id  TEXT NOT NULL REFERENCES trackers(id),
  ts          INTEGER NOT NULL,   -- unix seconds, UTC
  lat         REAL    NOT NULL,
  lon         REAL    NOT NULL,
  accuracy_m  REAL,
  PRIMARY KEY (tracker_id, ts)
);
```

`trackers.yaml` (hand-edited config) seeds the `trackers` table on
first run.

### Scheduling

Long-lived foreground Python loop:

```python
while True:
    try:
        scrape_once()
        export_json()
    except Exception:
        log.exception("cycle failed")
    sleep(15*60 + random.uniform(-120, 120))
```

Run under `tmux` or `systemd --user` so it survives terminal close.

## Web Visualization

Vanilla JS + Leaflet + OpenStreetMap tiles. No build step. Static page
served by `python -m http.server -d web`.

### Layout

```
┌─────────────────────────────────────────────────┐
│  🐾 Mascot Tracker          [● LIVE]  [↻ Replay]│
├─────────────────────────────────────────────────┤
│                                                 │
│              [ Leaflet map ]                    │
│       ●━━━━ trail (Mascot 1, red)               │
│         ●━━━━ trail (Mascot 2, blue)            │
│           ●━━━━ trail (Mascot 3, green)         │
│                                                 │
├─────────────────────────────────────────────────┤
│  ◀◀  ▶  ▶▶    [━━━━━●━━━━━━━━━]  Sat 14:32     │
│  Mascot 1 ✓   Mascot 2 ✓   Mascot 3 ✓           │
└─────────────────────────────────────────────────┘
```

### Behavior

- Page fetches `data.json` on load and again every 30 seconds.
- **Live mode (default):** latest position of each mascot as a pulsing
  colored dot; fading polyline trail behind (older points more
  transparent, fully fades after a configurable window — default 6h).
- **Replay mode:** play/pause button + scrub bar replays the whole
  weekend; dots animate along recorded paths at 1×, 4×, 16× speed.
- Per-mascot toggle to hide/show trail.
- Map auto-fits bounds on first load; user pan/zoom is preserved on
  subsequent fetches.
- Click a dot → popup: `name · last seen X min ago · ±Ym`.

### `data.json` shape

```json
{
  "generated_at": 1736251200,
  "trackers": [
    {
      "id": "abc",
      "name": "Mascot 1",
      "color": "#e74c3c",
      "positions": [
        [1736000000, 40.4168, -3.7038, 12]
      ]
    }
  ]
}
```

Position rows are `[ts, lat, lon, accuracy_m]` — compact for a
weekend's worth of data.

## Repo Layout

```
mascotes_track/
├── scraper/
│   ├── __init__.py
│   ├── setup_login.py        # one-time interactive login
│   ├── scrape.py             # one scrape cycle (importable + CLI)
│   ├── run_loop.py           # the 15-min loop
│   ├── parser.py             # Find Hub response decoding (isolated)
│   └── db.py                 # SQLite helpers
├── export.py                 # SQLite → web/data.json
├── trackers.yaml             # id, name, color per mascot
├── config.yaml               # interval, jitter, paths, fade window
├── data.sqlite               # gitignored
├── auth_state.json           # gitignored
├── logs/                     # gitignored, rotating logs
├── web/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── data.json             # regenerated each cycle
├── tests/
│   ├── test_parser.py
│   ├── test_db.py
│   └── test_export.py
├── docs/superpowers/specs/   # this document lives here
├── pyproject.toml            # uv / pip
├── .gitignore
└── README.md
```

## Operations

### Quickstart

```bash
uv sync
uv run playwright install chromium
uv run python -m scraper.setup_login   # opens Chromium, log in once
uv run python -m scraper.run_loop      # starts the 15-min loop
python -m http.server -d web 8000      # other terminal → localhost:8000
```

### Logging

Rotating file logs under `logs/`. Each cycle records: start time,
devices captured, anomalies (login challenge, missing tracker, parse
failure). Tail during the game.

### Tests

Unit tests cover:

- `parser.py` — given a saved sample Find Hub response, parses the
  expected positions.
- `db.py` — upserts are idempotent on `(tracker_id, ts)`.
- `export.py` — produces the documented `data.json` shape from a
  fixture SQLite database.

Playwright/Find Hub interaction is **not** unit-tested — too brittle to
mock usefully. Verified manually during the first-run discovery step.

## Out of Scope (v1)

- Public hosting / authentication / multi-viewer access.
- Real-time (sub-15 min) updates.
- Mobile-optimized UI.
- Heatmaps, 3D visualization, deck.gl effects.
- Reverse-engineered direct API (may be revisited if Find Hub UI
  changes break the scraper repeatedly).

## Future Considerations

- Hosting `web/` on a static host (Netlify, GitHub Pages, S3) with the
  scraper pushing `data.json` via SFTP/S3.
- Auth wall on the public page if location data should not be fully
  public.
- Migration to an unofficial direct API if web-UI scraping becomes too
  fragile.
