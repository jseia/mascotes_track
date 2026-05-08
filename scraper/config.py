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
