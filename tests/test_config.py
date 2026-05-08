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
