# V2 Pilot – Railway & Codebase Alignment

Use this with the CLI to confirm everything is aligned so https://brainscraper.io/v2-pilot returns data.

**CLI variable commands:** `railway variable list --service <name>`, `railway variable set --service <name> KEY=value`

---

## 1. Redis keys (must match across services)

| Key / pattern      | Producer                          | Consumer                              |
|--------------------|-----------------------------------|----------------------------------------|
| `leads_to_enrich`  | BrainScraper (queue-csv, redisBridge), Scrapegoat (dlq retry) | Scrapegoat /worker/process-one, redis_queue_worker |
| `failed_leads`     | Scrapegoat redis_queue_worker     | Scrapegoat /dlq, BrainScraper queue-status (LLEN) |
| `chimera:missions` | BrainScraper fire-swarm, Scrapegoat ChimeraStation | Chimera Core (BRPOP)       |
| `chimera:results:{id}` | Chimera Core                   | Scrapegoat ChimeraStation (BRPOP)      |
| `mission:{id}`     | BrainScraper fire-swarm, Scrapegoat ChimeraStation, Chimera Core main | BrainScraper mission-status, telemetry |

---

## 2. Env vars by service

### BrainScraper (Railway)

| Var | Required | Used by |
|-----|----------|---------|
| `REDIS_URL` or `APP_REDIS_URL` | Yes | queue-csv (redisBridge), queue-status, fire-swarm, debug-info ping, mission-status, telemetry |
| `SCRAPEGOAT_API_URL` or `SCRAPEGOAT_URL` | Yes | process-one, debug-info /health, pipeline/status, pipeline/dlq |
| `DATABASE_URL` or `APP_DATABASE_URL` | For /enriched | load-enriched-results (Postgres merge) |

### Scrapegoat (Railway)

| Var | Required | Used by |
|-----|----------|---------|
| `REDIS_URL` or `APP_REDIS_URL` | Yes | /worker/process-one, /queue/status, redis_queue_worker, ChimeraStation, DLQ, dnc_scrub, etc. |
| `DATABASE_URL` or `APP_DATABASE_URL` | Yes | DatabaseSaveStation, init_db |
| `CHIMERA_BRAIN_HTTP_URL` or `CHIMERA_BRAIN_ADDRESS` | For ChimeraStation | ChimeraStation _hive_predict_path, _hive_store_pattern |

### Chimera Core (Railway)

| Var | Required | Used by |
|-----|----------|---------|
| `REDIS_URL` or `APP_REDIS_URL` | Yes | BRPOP chimera:missions, LPUSH chimera:results, mission:{id} updates, SYSTEM_STATE:PAUSED |
| `CHIMERA_BRAIN_ADDRESS` | Yes | gRPC to Brain |
| `BRAINSCRAPER_URL` | For telemetry | telemetry_client → POST /api/v2-pilot/telemetry |

### Chimera Brain (Railway)

| Var | Required | Used by |
|-----|----------|---------|
| `REDIS_URL` or `APP_REDIS_URL` | For Hive Mind | vision_service, server |
| `CHIMERA_BRAIN_PORT` | Optional | gRPC port (default 50051) |

---

## 3. API → backend mapping

| BrainScraper route | Backend | Notes |
|--------------------|---------|-------|
| `GET /api/v2-pilot/debug-info` | Redis PING, `getScrapegoatBase()/health` | Pre-flight Redis ✓/✗, Scrapegoat ✓/✗ |
| `GET /api/v2-pilot/mission-status` | Redis `KEYS mission:*`, `HGETALL` | TOTAL MISSIONS, QUEUED, PROCESSING, COMPLETED, FAILED, Mission Log |
| `GET /api/enrichment/queue-status` | Redis `LLEN leads_to_enrich`, `LLEN failed_leads` | In queue, Failed (DLQ); no Scrapegoat call |
| `POST /api/enrichment/process-one` | Scrapegoat `POST /worker/process-one` | BRPOP leads_to_enrich, run pipeline |
| `POST /api/enrichment/queue-csv` | Redis `LPUSH leads_to_enrich` (redisBridge) | Needs REDIS_URL |
| `POST /api/v2-pilot/fire-swarm` | Redis `LPUSH chimera:missions`, `HSET mission:{id}` | Needs REDIS_URL |
| `POST /api/v2-pilot/telemetry` | Redis `HSET mission:{id}` | Chimera Core when BRAINSCRAPER_URL set |
| `GET /api/load-enriched-results` | Postgres + `enriched-all-leads.json` | /enriched; needs DATABASE_URL for queue-based results |

---

## 4. CLI checks (run from repo root)

```bash
# Confirm project link and list variables per service
railway status
railway variable list --service brainscraper
railway variable list --service scrapegoat
railway variable list --service chimera-core
railway variable list --service chimera-brain-v1

# BrainScraper build
cd brainscraper && npm run build && cd ..

# BrainScraper v2-pilot + enrichment routes exist
test -f brainscraper/app/api/v2-pilot/debug-info/route.ts && \
test -f brainscraper/app/api/v2-pilot/fire-swarm/route.ts && \
test -f brainscraper/app/api/v2-pilot/mission-status/route.ts && \
test -f brainscraper/app/api/v2-pilot/telemetry/route.ts && \
test -f brainscraper/app/api/v2-pilot/quick-search/route.ts && \
test -f brainscraper/app/api/enrichment/process-one/route.ts && \
test -f brainscraper/app/api/enrichment/queue-status/route.ts && \
test -f brainscraper/app/api/enrichment/queue-csv/route.ts && \
echo "BrainScraper v2-pilot + enrichment routes OK"

# Scrapegoat /worker/process-one
python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, str(Path('scrapegoat').resolve()))
import main
paths = [r.path for r in main.app.routes if hasattr(r,'path')]
assert '/worker/process-one' in paths, paths
print('Scrapegoat /worker/process-one OK')
"

# Chimera Core mission queue name
grep -q "chimera:missions" chimera-core/main.py && echo "Chimera mission queue chimera:missions OK"

# Redis key alignment
grep -l "leads_to_enrich" brainscraper/utils/redisBridge.ts brainscraper/app/api/enrichment/queue-status/route.ts scrapegoat/main.py scrapegoat/app/workers/redis_queue_worker.py >/dev/null && echo "leads_to_enrich alignment OK"
grep -l "chimera:missions" brainscraper/app/api/v2-pilot/fire-swarm/route.ts chimera-core/main.py scrapegoat/app/pipeline/stations/enrichment.py >/dev/null && echo "chimera:missions alignment OK"
```

---

## 5. Railway env checklist (CLI-verified against codebase)

**How to verify:** `railway variable list --service <name>` (run from repo root; project linked).

### BrainScraper

| Var | Required | Code ref | CLI verified |
|-----|----------|----------|--------------|
| `REDIS_URL` or `APP_REDIS_URL` | Yes | `redisBridge.ts`, `queue-status`, `fire-swarm`, `debug-info`, `mission-status`, `telemetry` | ✓ both set |
| `SCRAPEGOAT_API_URL` or `SCRAPEGOAT_URL` | Yes | `scrapegoatClient.getScrapegoatBase()`, `process-one`, `debug-info` | ✓ both set |
| `DATABASE_URL` or `APP_DATABASE_URL` | For /enriched | `load-enriched-results/route.ts` (Postgres merge) | ✓ both set |

Optional (informational in debug-info only): `CHIMERA_BRAIN_HTTP_URL`, `CHIMERA_BRAIN_ADDRESS`.

### Scrapegoat

| Var | Required | Code ref | CLI verified |
|-----|----------|----------|--------------|
| `REDIS_URL` or `APP_REDIS_URL` | Yes | `main.py`, `redis_queue_worker` (uses both; fixed to fallback to APP_REDIS_URL), `enrichment.ChimeraStation`, `dnc_scrub`, `validator`, `blueprint_loader`, `router`, `stats`, `memory`, `spider_worker`, `auth_worker`, `cookie_store`, `truepeoplesearch_spider` | ✓ both set |
| `DATABASE_URL` or `APP_DATABASE_URL` | Yes | `database.py`, `init_db.py`, `blueprint_commit.py` | ✓ both set |
| `CHIMERA_BRAIN_HTTP_URL` or `CHIMERA_BRAIN_ADDRESS` | For ChimeraStation | `enrichment._get_chimera_brain_http_url()` → `/api/hive-mind/predict-path`, `store-pattern` | ✓ `CHIMERA_BRAIN_HTTP_URL` added |

Also used (already set): `OPENAI_API_KEY`, `CENSUS_API_KEY`, `RAPIDAPI_KEY`, `TELNYX_API_KEY`, `CAPSOLVER_API_KEY`, `USHA_JWT_TOKEN`, `CHIMERA_STATION_TIMEOUT`, `PORT` (8080), `DECODO_API_KEY`.

If you run a **separate Scrapegoat Worker** service (`start_redis_worker.py`), give it the same vars as Scrapegoat (REDIS, DATABASE, CHIMERA_BRAIN_HTTP_URL, and the API keys above).

### Chimera Core

| Var | Required | Code ref | CLI verified |
|-----|----------|----------|--------------|
| `REDIS_URL` or `APP_REDIS_URL` | Yes | `main.py` (REDIS_URL, APP_REDIS_URL, REDIS_BRIDGE_URL, REDIS_CONNECTION_URL), `workers.py`, `capsolver.py`, `visibility_check.py` | ✓ REDIS_URL |
| `CHIMERA_BRAIN_ADDRESS` | Yes | `main.py` gRPC (default `http://chimera-brain.railway.internal:50051`) | ✓ set |
| `BRAINSCRAPER_URL` | For telemetry | `main.py`, `telemetry_client` → `POST /api/v2-pilot/telemetry` | ✓ set |
| `SCRAPEGOAT_URL` or `DOJO_TRAUMA_URL` | Optional | `workers._report_trauma`, `_report_coordinate_drift` → Dojo `/api/dojo/trauma`, `/api/dojo/coordinate-drift` | ✓ `SCRAPEGOAT_URL` added |
| `CAPSOLVER_API_KEY` | For people-search | `capsolver` (reCAPTCHA, Turnstile, hCaptcha on ThatsThem, TruePeopleSearch, etc.) | ✓ set (same as Scrapegoat) |
| `DECODO_API_KEY` | For people-search | `network.get_proxy_config` → sticky mobile IP; Cloudflare-heavy sites | ✓ set (same as Scrapegoat) |

### Chimera Brain

| Var | Required | Code ref | CLI verified |
|-----|----------|----------|--------------|
| `REDIS_URL` or `APP_REDIS_URL` | For Hive Mind | `server.py`, `vision_service.py` | ✓ REDIS_URL |
| `PORT` | Yes (Railway) | `server.py` health HTTP (default 8080) | ✓ 8080 |
| `CHIMERA_BRAIN_PORT` | Optional | `server.py` gRPC (default 50051) | ✓ 50051 |

`DATABASE_URL` is optional for Chimera Brain; may be empty.

---

### 5b. Optional / when-used (codebase audit — none required for v2-pilot)

Variables the code reads that have defaults or are only needed for specific features. No need to set for v2-pilot unless you use that feature.

| Service | Var | Code ref | Note |
|---------|-----|----------|------|
| **BrainScraper** | `RAPIDAPI_KEY` | `linkedin-sales-navigator/route` | ✓ set. Required for LinkedIn search. |
| | `RAPIDAPI_RATE_LIMIT_MAX` | `LinkedInLeadGenerator` | Default 5. |
| | `OPENAI_API_KEY` | `dojo/translate` | Dojo: if unset, `DOJO_MOCK_AI` or mock. |
| | `DOJO_MOCK_AI` | `dojo/translate` | Dojo mock. |
| | `NEXT_PUBLIC_SCRAPEGOAT_URL` | `spiders/page` (client) | ✓ set. |
| | `CHIMERA_BRAIN_HTTP_URL`, `CHIMERA_BRAIN_ADDRESS` | `debug-info` | Informational only; not used for calls. |
| **Scrapegoat** | `COGNITO_REFRESH_TOKEN` | `dnc_scrub` | Alternative to USHA_JWT_TOKEN. |
| | `USHA_AGENT_NUMBER` | `dnc_scrub` | Default `00044447`. |
| | `CHIMERA_BRAIN_ADDRESS` | `enrichment` | Can derive HTTP from 50051→8080; `CHIMERA_BRAIN_HTTP_URL` preferred. |
| | `PROXY_URL`, `ROTATING_PROXY_URL` | `base`, `browser_mode`, `start_auth_worker` | Proxies. |
| | `DECODO_USER` | `base`, `network` (chimera-core) | Default `user`. |
| | `ENABLE_COGNITIVE_FEATURES` | `base` | Default `true`. |
| | `ENABLE_BROWSER_WARMUP` | `base` | Default off. |
| | `WEBHOOK_URL` | `validator` | Progress webhooks. |
| | `PIPELINE_NAME`, `PIPELINE_BUDGET_LIMIT` | `redis_queue_worker` | Override pipeline / budget. |
| | `LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD`, `FACEBOOK_EMAIL`, `FACEBOOK_PASSWORD`, `USHA_EMAIL`, `USHA_PASSWORD` | `main`, `start_auth_worker`, `auth_worker` | Auth worker / cookie refresh. |
| | `AUTH_REFRESH_INTERVAL_HOURS` | `main`, `start_auth_worker` | Default 6. |
| | `SPIDER_FORWARD_TO_ENRICHMENT` | `spider_worker` | Default `false`. |
| **Chimera Core** | `APP_REDIS_URL`, `REDIS_BRIDGE_URL`, `REDIS_CONNECTION_URL` | `main` | Fallbacks when REDIS_URL unset; REDIS_URL set. |
| | `CHIMERA_MISSION_QUEUE`, `CHIMERA_MISSION_DLQ` | `main` | Defaults `chimera:missions`, `chimera:missions:failed`. |
| | `CHIMERA_SKIP_BOOTSTRAP`, `ENVIRONMENT`, `RAILWAY_ENVIRONMENT` | `main` | Bootstrap / prod check. |
| | `NUM_WORKERS` | `main` | Default 1. |
| | `DOJO_TRAUMA_URL` | `workers` | Alternative to SCRAPEGOAT_URL; ✓ SCRAPEGOAT_URL set. |
| | `CHROMIUM_CHANNEL`, `CHROMIUM_USE_NATIVE_TLS`, `CHROME_UA_VERSION`, `CHROME_UA_PLATFORM` | `workers`, `stealth` | Browser/build overrides. |
| | `CAPSOLVER_API_KEY`, `WEBHOOK_URL` | `capsolver` | ✓ CAPSOLVER_API_KEY set for people-search CAPTCHAs. |
| | `TRACE_STORAGE_DIR`, `UPLOAD_TRACES_TO_CLOUD`, `CLOUD_STORAGE_URL` | `storage_bridge` | Trace storage. |
| | `PROXY_URL`, `ROTATING_PROXY_URL`, `DECODO_API_KEY`, `DECODO_USER` | `network` | ✓ DECODO_API_KEY set for people-search proxy (sticky IP). |
| | `NETWORK_MTU_TARGET`, `NETWORK_TTL_TARGET` | `network` | Defaults 1500, 64. |
| | `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` | `db_bridge` | Alternative to DATABASE_URL. |
| | `DB_CONNECT_TIMEOUT`, `DB_POOL_MAX` | `db_bridge` | Defaults 5, 10. |
| **Chimera Brain** | `APP_REDIS_URL` | `server`, `vision_service` | Fallback; REDIS_URL set. |
| | `CHIMERA_VISION_MODEL`, `CHIMERA_VISION_DEVICE` | `server` | ✓ CHIMERA_VISION_DEVICE set. |
| | `CHIMERA_USE_SIMPLE` | `server` | ✓ set. |
| | `USE_2026_VISION`, `VLM_TIER_2026`, `USE_LOCAL_VLM`, `VLM_MODEL` | `vision_service` | VLM toggles; defaults. |
| | `WEBHOOK_URL` | `vision_service` | Webhooks. |
| | `VRAM_DEEPSEEK_FRACTION`, `VRAM_OLMOCR_FRACTION`, `VRAM_KV_INT8` | `vram_manager` | Local model VRAM. |

---

## 6. Flow that must return data

1. **Pre-flight (Check)**  
   - `GET /api/v2-pilot/debug-info` → Redis ✓, Scrapegoat ✓ if `REDIS_URL` and `SCRAPEGOAT_API_URL`/`SCRAPEGOAT_URL` are set and reachable.

2. **In queue / Failed (DLQ)**  
   - `GET /api/enrichment/queue-status` → numbers from Redis. If `REDIS_URL` is unset or Redis down → 0, 0, `redis_connected: false`.

3. **Queue CSV → Enrich (Process 1)**  
   - Queue CSV: `LPUSH leads_to_enrich` (needs `REDIS_URL`).  
   - Enrich: `POST /api/enrichment/process-one` → Scrapegoat `POST /worker/process-one` → `BRPOP leads_to_enrich` → pipeline (ChimeraStation pushes to `chimera:missions` if used) → Postgres.  
   - Requires: BrainScraper `REDIS_URL`, `SCRAPEGOAT_API_URL`/`SCRAPEGOAT_URL`; Scrapegoat same `REDIS_URL`, `DATABASE_URL`, and Chimera Brain if ChimeraStation runs; Chimera Core running and same Redis for `chimera:missions` when pipeline uses Chimera.

4. **Fire Swarm / Quick Search → Fire**  
   - `POST /api/v2-pilot/fire-swarm` → `LPUSH chimera:missions`, `HSET mission:{id}`.  
   - Chimera Core `BRPOP chimera:missions` → `execute_mission` (mission_type `enrichment` or `instruction=deep_search`) → `HSET mission:{id}` status.  
   - `GET /api/v2-pilot/mission-status` reads `mission:*`.  
   - Requires: BrainScraper `REDIS_URL`; Chimera Core same `REDIS_URL`, `CHIMERA_BRAIN_ADDRESS`, and running.

5. **View results in /enriched**  
   - `GET /api/load-enriched-results` merges Postgres + `enriched-all-leads.json`.  
   - Queue-based enrichment appears only if BrainScraper has `DATABASE_URL`/`APP_DATABASE_URL` and Scrapegoat writes to the same Postgres.

---

## 7. Common reasons “it doesn’t return data”

| Symptom | Likely cause | Check |
|---------|--------------|-------|
| Pre-flight Redis — or ✗ | `REDIS_URL` / `APP_REDIS_URL` unset or wrong in BrainScraper | `railway variable list --service brainscraper` \| grep REDIS |
| Pre-flight Scrapegoat — or ✗ | `SCRAPEGOAT_API_URL` or `SCRAPEGOAT_URL` unset or Scrapegoat down | `railway variable list --service brainscraper` \| grep SCRAPEGOAT; `curl -s $SCRAPEGOAT_URL/health` |
| In queue always 0 | Same Redis not used, or nothing LPUSHed | Queue a CSV first; `redis-cli -u $REDIS_URL LLEN leads_to_enrich` |
| Enrich: “Queue empty” | `leads_to_enrich` empty or Scrapegoat using different Redis | `redis-cli -u $REDIS_URL LLEN leads_to_enrich`; compare `REDIS_URL` BrainScraper vs Scrapegoat |
| Enrich: timeout / 5xx | Scrapegoat down, wrong `SCRAPEGOAT_*` URL, or ChimeraStation waiting on Chimera Core | Scrapegoat logs; Chimera Core running and same Redis |
| Fire Swarm: missions stay queued | Chimera Core not running or different Redis | `redis-cli -u $REDIS_URL LLEN chimera:missions`; Chimera Core logs |
| Mission Log empty | No `mission:*` keys or `REDIS_URL` wrong in BrainScraper | `redis-cli -u $REDIS_URL KEYS "mission:*"` |
| /enriched no queue-based rows | `DATABASE_URL` unset in BrainScraper or different Postgres | `railway variable list --service brainscraper` \| grep DATABASE; compare with Scrapegoat |

---

## 8. People-search (Magazine) – seamless enrichment

**Sites:** ThatsThem, SearchPeopleFree, ZabaSearch, FastPeopleSearch, TruePeopleSearch, AnyWho.

**Flow:** Lead → IdentityStation → **BlueprintLoaderStation** (Redis `blueprint:{domain}`) → **ChimeraStation** (LPUSH `chimera:missions` with `instruction=deep_search`, `target_provider`) → **Chimera Core** (BRPOP, `_MAGAZINE_TARGETS`, browser, **CapSolver** on CAPTCHA, **Decodo** proxy) → LPUSH `chimera:results:{id}` → ChimeraStation BRPOP → … → DatabaseSaveStation.

**Components leveraged:**
- **BlueprintLoaderStation** + **ChimeraStation** (`scrapegoat/app/pipeline/stations/`)
- **GPS Router** (`router.py`): `select_provider`, `get_next_provider`, Magazine = all 6
- **Chimera Core** `workers._MAGAZINE_TARGETS`, `_run_deep_search`, `get_proxy_config`, `capsolver`
- **Chimera Brain** (gRPC vision; `_hive_predict_path`, `_hive_store_pattern` via CHIMERA_BRAIN_HTTP_URL)
- **Dojo** (trauma, coordinate-drift via SCRAPEGOAT_URL on Chimera Core)

**Final verification (people-search):**

| Check | Command / where |
|-------|-----------------|
| Chimera Core has CAPSOLVER_API_KEY | `railway variable list --service chimera-core` \| grep CAPSOLVER |
| Chimera Core has DECODO_API_KEY | `railway variable list --service chimera-core` \| grep DECODO |
| Scrapegoat has CHIMERA_BRAIN_HTTP_URL | `railway variable list --service scrapegoat` \| grep CHIMERA_BRAIN |
| Pipeline: BlueprintLoader before ChimeraStation | `scrapegoat/app/pipeline/routes.json` → hybrid_smart.stations |
| Chimera Core SCRAPEGOAT_URL for Dojo | `railway variable list --service chimera-core` \| grep SCRAPEGOAT |
| Blueprints for Magazine domains | Redis `blueprint:fastpeoplesearch.com` etc. or Dojo; if missing, `_mapping_required` and Dojo alert |

**No remaining gaps for seamless people-search:** CAPSOLVER and DECODO are set on Chimera Core; CHIMERA_BRAIN_HTTP_URL on Scrapegoat; SCRAPEGOAT_URL on Chimera Core; pipeline order and Magazine targets are in code. Blueprints can be absent (Chimera falls back to built-in selectors + VLM); Dojo can add them over time.

---

## 9. Completing all remaining nuances

To remove the remaining “by design” nuances and run people-search with full coverage:

### 9.1. Seed Magazine blueprints (Redis + file + DB)

Ensures `blueprint:{domain}` exists for all 6 Magazine domains so BlueprintLoader does not set `_mapping_required` and Dojo/coordinate-drift can override selectors when sites change.

**Option A – HTTP (recommended):**
```bash
curl -X POST "https://<SCRAPEGOAT_URL>/api/blueprints/seed-magazine"
# e.g. curl -X POST "https://scrapegoat-production-8d0a.up.railway.app/api/blueprints/seed-magazine"
```

**Option B – CLI one-off:**
```bash
railway run --service scrapegoat -- python scripts/seed_magazine_blueprints.py
```

**Result:** `fastpeoplesearch.com`, `truepeoplesearch.com`, `zabasearch.com`, `searchpeoplefree.com`, `thatsthem.com`, `anywho.com` are written to Redis (`blueprint:{domain}`), `BLUEPRINT_DIR` (file), and `site_blueprints` (Postgres). Idempotent.

### 9.2. `/data/dojo-blueprints` on Railway

- **Scrapegoat:** `get_blueprint_dir()` creates `/data/dojo-blueprints` when `/data` exists (e.g. Railway volume mounted at `/data`). No extra code.
- **Volume:** If no volume is mounted at `/data`, `/data` does not exist and the code falls back to `./data/dojo-blueprints` (ephemeral in containers). For persistence, mount a Railway volume at `/data` for the Scrapegoat service.
- To use another path, change `get_blueprint_dir` in `scrapegoat/app/enrichment/scraper_enrichment.py` or set `BLUEPRINT_DIR` via env if you add that. Not currently implemented.

### 9.3. Dojo “mapping required” flow

When a **new** people-search domain (not in the 6 Magazine set) is first used, BlueprintLoader:

1. SADDs it to `dojo:domains_need_mapping`
2. PUBLISHes `dojo:alerts` with `{"type":"mapping_required","domain":"..."}`

**To handle it:**

1. **List domains that need mapping**
   - BrainScraper: `GET /api/dojo/mapping-required` → proxies to Scrapegoat `GET /api/dojo/domains-need-mapping` → `{ domains: ["..."] }`
   - Or: `redis-cli -u $REDIS_URL SMEMBERS dojo:domains_need_mapping`

2. **Map and commit in Dojo**
   - In Dojo (BrainScraper): open the site, define selectors, then **Commit to Swarm** → Scrapegoat `POST /api/blueprints/commit-to-swarm` with `{ domain, blueprint }`.  
   - That runs `commit_blueprint_impl` (Redis + file + `site_blueprints`) and SREMs the domain from `dojo:domains_need_mapping`.

3. **Optional: auto-map**
   - BlueprintLoader calls `attempt_auto_map(domain)` when no blueprint exists. It can create and commit a blueprint from HTML. It is rate-limited and may fail on CAPTCHA/Cloudflare; Dojo remains the reliable way to add new domains.

### 9.4. Chimera Core redeploy

After changing Chimera Core env (e.g. CAPSOLVER, DECODO), a redeploy is required. Railway does this when variables are set via the dashboard or CLI. No extra step.

### 9.5. Checklist to complete nuances

| Step | Action | Verify |
|------|--------|--------|
| 1 | `POST /api/blueprints/seed-magazine` to Scrapegoat | `{ "status": "ok", "seeded": [6 domains], "count": 6 }` |
| 2 | (Optional) Dojo UI: list `GET /api/dojo/mapping-required`, map new domains, commit | `dojo:domains_need_mapping` empty or only non‑Magazine domains you chose to add |
| 3 | Ensure `/data` (or your blueprint volume) is mounted for Scrapegoat on Railway | `get_blueprint_dir()` uses `/data/dojo-blueprints` when `/data` exists |
| 4 | Chimera Core: CAPSOLVER + DECODO set and service redeployed | `railway variable list --service chimera-core` \| grep -E "CAPSOLVER|DECODO" |
