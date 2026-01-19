"""
Commit blueprint to Redis, file, and DB.
Single implementation used by commit-to-swarm and auto_map.
Writes `data` (full JSON) and `updated_at` so BlueprintLoader and Chimera consume correctly.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

from loguru import logger

from app.enrichment.scraper_enrichment import BLUEPRINT_DIR


def commit_blueprint_impl(domain: str, blueprint: Dict[str, Any], r) -> None:
    """
    Write blueprint to Redis (blueprint:{domain}), BLUEPRINT_DIR file, and site_blueprints.
    Sets dojo:active_domain. Removes blueprint:{domain}:pending if present.
    Does not overwrite {field}_x, {field}_y (coordinate-drift keys).
    """
    ext = blueprint.get("extraction") or blueprint.get("extractionPaths") or {}
    # name_selector = search input (Chimera); do NOT use ext["name"] (detail-page selector like h1::text)
    name_sel = str(blueprint.get("name_selector") or ext.get("name_input") or ext.get("search_input") or "")
    result_sel = str(blueprint.get("result_selector") or ext.get("result") or ext.get("result_list") or "")
    mapping = {
        "data": json.dumps(blueprint),
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "name_selector": name_sel,
        "result_selector": result_sel,
        "url": str(blueprint.get("targetUrl") or blueprint.get("url") or ""),
        "extraction": json.dumps(ext),
    }
    key = f"blueprint:{domain}"
    r.hset(key, mapping=mapping)

    BLUEPRINT_DIR.mkdir(parents=True, exist_ok=True)
    blueprint_file = BLUEPRINT_DIR / f"{domain}.json"
    with open(blueprint_file, "w") as f:
        json.dump(blueprint, f, indent=2)

    db_url = os.getenv("DATABASE_URL") or os.getenv("APP_DATABASE_URL")
    if db_url:
        try:
            import psycopg2

            conn = psycopg2.connect(db_url)
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO site_blueprints (domain, blueprint, source, updated_at)
                VALUES (%s, %s, 'dojo', NOW())
                ON CONFLICT (domain) DO UPDATE SET blueprint = EXCLUDED.blueprint, source = EXCLUDED.source, updated_at = NOW()
                """,
                (domain, json.dumps(blueprint)),
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning("Blueprint commit: DB upsert failed (non-fatal): %s", e)

    r.set(f"dojo:active_domain:{domain}", "1", ex=3600)
    r.delete(f"blueprint:{domain}:pending")
    try:
        r.srem("dojo:domains_need_mapping", domain)
    except Exception:
        pass
    logger.info("Blueprint committed: domain=%s redis=ok file=%s", domain, blueprint_file)
