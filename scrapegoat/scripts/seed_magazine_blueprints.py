#!/usr/bin/env python3
"""
Seed Redis + file + DB with minimal blueprints for all 6 Magazine people-search domains.
Aligns with chimera-core workers._MAGAZINE_TARGETS. Idempotent.

Run:
  railway run --service scrapegoat -- python scripts/seed_magazine_blueprints.py
  # or via API: curl -X POST https://<scrapegoat>/api/blueprints/seed-magazine
"""
import os
import sys
from pathlib import Path

# Ensure /data/dojo-blueprints exists before any import that calls get_blueprint_dir
if Path("/data").exists():
    Path("/data/dojo-blueprints").mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import redis
from app.enrichment.blueprint_commit import commit_blueprint_impl

# Must match chimera-core workers._MAGAZINE_TARGETS and main._MAGAZINE_BLUEPRINTS
MAGAZINE = [
    ("fastpeoplesearch.com", {"targetUrl": "https://www.fastpeoplesearch.com/", "name_selector": "input#name-search", "result_selector": "div.search-item", "extraction": {}}),
    ("truepeoplesearch.com", {"targetUrl": "https://www.truepeoplesearch.com/", "name_selector": "input#search-name", "result_selector": "div.card-summary", "extraction": {}}),
    ("zabasearch.com", {"targetUrl": "https://www.zabasearch.com/", "name_selector": "input[name='q']", "result_selector": None, "extraction": {}}),
    ("searchpeoplefree.com", {"targetUrl": "https://www.searchpeoplefree.com/", "name_selector": "input[name='q']", "result_selector": None, "extraction": {}}),
    ("thatsthem.com", {"targetUrl": "https://thatsthem.com/", "name_selector": "input[name='q']", "result_selector": None, "extraction": {}}),
    ("anywho.com", {"targetUrl": "https://www.anywho.com/", "name_selector": "input[name='q']", "result_selector": None, "extraction": {}}),
]


def main() -> None:
    url = os.getenv("REDIS_URL") or os.getenv("APP_REDIS_URL") or "redis://localhost:6379"
    r = redis.from_url(url)
    for domain, bp in MAGAZINE:
        commit_blueprint_impl(domain, bp, r)
        print("Seeded", domain)
    print("Done. Seeded", len(MAGAZINE), "domains.")


if __name__ == "__main__":
    main()
