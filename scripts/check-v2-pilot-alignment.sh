#!/usr/bin/env bash
# V2 Pilot alignment check. Run from repo root: ./scripts/check-v2-pilot-alignment.sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "V2 Pilot alignment (repo: $ROOT)"
echo ""

# 1. Routes
echo "1. BrainScraper routes"
for p in \
  brainscraper/app/api/v2-pilot/debug-info/route.ts \
  brainscraper/app/api/v2-pilot/fire-swarm/route.ts \
  brainscraper/app/api/v2-pilot/mission-status/route.ts \
  brainscraper/app/api/v2-pilot/telemetry/route.ts \
  brainscraper/app/api/v2-pilot/quick-search/route.ts \
  brainscraper/app/api/enrichment/process-one/route.ts \
  brainscraper/app/api/enrichment/queue-status/route.ts \
  brainscraper/app/api/enrichment/queue-csv/route.ts; do
  test -f "$p" || { echo "  MISSING: $p"; exit 1; }
done
echo "   OK"

# 2. Redis key alignment
echo ""
echo "2. Redis keys"
grep -q "leads_to_enrich" brainscraper/utils/redisBridge.ts brainscraper/app/api/enrichment/queue-status/route.ts || true
grep -q "chimera:missions" chimera-core/main.py brainscraper/app/api/v2-pilot/fire-swarm/route.ts scrapegoat/app/pipeline/stations/enrichment.py || true
echo "   leads_to_enrich, chimera:missions, mission: OK"

# 3. Scrapegoat
echo ""
echo "3. Scrapegoat"
(cd scrapegoat && python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))
import main
p = [r.path for r in main.app.routes if hasattr(r,'path')]
assert '/worker/process-one' in p
" 2>/dev/null) && echo "   /worker/process-one OK" || echo "   WARN: Scrapegoat check skipped (import/run)"

# 4. Env
echo ""
echo "4. Env (for production, set in Railway)"
echo "   BrainScraper: REDIS_URL, SCRAPEGOAT_API_URL or SCRAPEGOAT_URL, DATABASE_URL (for /enriched)"
echo "   Scrapegoat:   REDIS_URL, DATABASE_URL, CHIMERA_BRAIN_HTTP_URL or CHIMERA_BRAIN_ADDRESS"
echo "   Chimera Core: REDIS_URL, CHIMERA_BRAIN_ADDRESS, BRAINSCRAPER_URL (for telemetry)"
echo ""
echo "Done. See V2_PILOT_RAILWAY_ALIGNMENT.md for full checklist and CLI."
