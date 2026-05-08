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
