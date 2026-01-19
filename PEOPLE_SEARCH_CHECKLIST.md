# People-Search Enrichment — Zero-Gaps Checklist

**Sites:** ThatsThem, SearchPeopleFree, ZabaSearch, FastPeopleSearch, TruePeopleSearch, AnyWho.

Use this to verify every requirement. Check off when verified.

---

## 1. Chimera Core running

| Check | Verification |
|-------|--------------|
| [ ] **Railway** | `chimera-core` service is up (not build failed, not crashed). Dashboard → Deployments. |
| [ ] **Local** | `cd chimera-core && python main.py` — no immediate exit; logs show "Swarm Hive consumer online". |

**Code:** `chimera-core/main.py` (mission loop), `railway.toml` startCommand `python main.py`.

---

## 2. Same Redis (Scrapegoat + Chimera Core)

| Check | Verification |
|-------|--------------|
| [ ] **REDIS_URL or APP_REDIS_URL** | Same value for `scrapegoat` and `chimera-core`. `railway variable list --service scrapegoat` and `--service chimera-core`; compare. |
| [ ] **Mission queue** | `redis-cli -u "$REDIS_URL" LLEN chimera:missions` works. Core BRPOPs from it; ChimeraStation LPUSHs. |

**Code:**  
- Scrapegoat: `main.py`, `enrichment.py`, `blueprint_loader.py`, `redis_queue_worker.py` → `REDIS_URL` or `APP_REDIS_URL`.  
- Chimera Core: `main.py` (REDIS_URL, APP_REDIS_URL, REDIS_BRIDGE_URL, REDIS_CONNECTION_URL), `workers.py`, `capsolver.py`.

---

## 3. Seed blueprints (6 Magazine domains)

| Check | Verification |
|-------|--------------|
| [ ] **Auto on Scrapegoat startup** | `SEED_MAGAZINE_ON_STARTUP=1` in Scrapegoat (default in `scrapegoat/railway.toml`). On deploy, Scrapegoat seeds `blueprint:{domain}` for all 6. Log: "Seed-magazine on startup: done (6 Magazine domains)". |
| [ ] **Manual (if needed)** | `curl -X POST "https://<SCRAPEGOAT_URL>/api/blueprints/seed-magazine"` → `{"status":"ok","seeded":[...],"count":6}`. Or `railway run --service scrapegoat -- python scripts/seed_magazine_blueprints.py`. |
| [ ] **Redis** | `redis-cli -u "$REDIS_URL" HGETALL blueprint:fastpeoplesearch.com` returns fields (data, name_selector, result_selector, etc.). |

**Code:** `scrapegoat/main.py` (`startup`, `_MAGAZINE_BLUEPRINTS`, `POST /api/blueprints/seed-magazine`), `scrapegoat/scripts/seed_magazine_blueprints.py`, `app/enrichment/blueprint_commit.commit_blueprint_impl`.

---

## 4. CapSolver on Chimera Core

| Check | Verification |
|-------|--------------|
| [ ] **CAPSOLVER_API_KEY** | Set for `chimera-core` in Railway Dashboard. `railway variable list --service chimera-core` \| grep CAPSOLVER. |
| [ ] **Code path** | `chimera-core/capsolver.py` → `os.getenv("CAPSOLVER_API_KEY")`, `is_available()`. `workers._detect_and_solve_captcha` imports capsolver for reCAPTCHA v2/v3, Turnstile, hCaptcha. |

---

## 5. Decodo (or proxy) on Chimera Core

| Check | Verification |
|-------|--------------|
| [ ] **DECODO_API_KEY or PROXY_URL** | Set for `chimera-core`. `railway variable list --service chimera-core` \| grep -E "DECODO|PROXY_URL". |
| [ ] **Code path** | `chimera-core/network.get_proxy_config` uses `PROXY_URL` or `ROTATING_PROXY_URL`; else if `DECODO_API_KEY`, builds `http://{DECODO_USER}:{DECODO_API_KEY}@gate.decodo.com:7000`. `workers.py` passes `get_proxy_config(sticky_session_id, carrier)` into Playwright context. |

---

## 6. Chimera Brain (required for VLM extract)

| Check | Verification |
|-------|--------------|
| [ ] **CHIMERA_BRAIN_ADDRESS** | Set for `chimera-core` (e.g. `http://chimera-brain.railway.internal:50051`). Default in `chimera-core/railway.toml`. |
| [ ] **Code path** | `chimera-core/main.py` → `brain_address = os.getenv("CHIMERA_BRAIN_ADDRESS", "http://chimera-brain.railway.internal:50051")` → `PhantomWorker(brain_address=...)`. `workers.process_vision` → gRPC. `_deep_search_extract_via_vision` uses it for phone/age/income. |

---

## Quick verification (all 6)

```bash
# From repo root, Railway project linked

# 1) Chimera Core running
railway status  # chimera-core not failed

# 2) Same Redis
railway variable list --service scrapegoat   | grep -E "REDIS_URL|APP_REDIS_URL"
railway variable list --service chimera-core | grep -E "REDIS_URL|APP_REDIS_URL"
# Values must match (or both from same Redis service reference).

# 3) Seed (Scrapegoat logs on deploy: "Seed-magazine on startup: done")
# Or now:
curl -s -X POST "https://<SCRAPEGOAT_URL>/api/blueprints/seed-magazine" | jq .

# 4) CapSolver
railway variable list --service chimera-core | grep CAPSOLVER_API_KEY

# 5) Decodo
railway variable list --service chimera-core | grep -E "DECODO_API_KEY|PROXY_URL"

# 6) Chimera Brain
railway variable list --service chimera-core | grep CHIMERA_BRAIN_ADDRESS
```

---

## Lead input (queue/CSV)

Leads in `leads_to_enrich` must include **`name`** (or **`fullName`**) or **`firstName`** and **`lastName`**, and **`linkedinUrl`**. The pipeline normalizes `name` from `fullName` or `firstName`+`lastName`. ChimeraStation skips and returns FAIL if no searchable name (avoids burning Core missions).

---

## Reference: env by service

| Service | Required for people-search |
|---------|----------------------------|
| **Scrapegoat** | `REDIS_URL` or `APP_REDIS_URL`, `DATABASE_URL` or `APP_DATABASE_URL`, `CHIMERA_BRAIN_HTTP_URL` or `CHIMERA_BRAIN_ADDRESS`, `SEED_MAGAZINE_ON_STARTUP=1` (in railway.toml). |
| **Chimera Core** | `REDIS_URL` or `APP_REDIS_URL` (same as Scrapegoat), `CHIMERA_BRAIN_ADDRESS`, `CAPSOLVER_API_KEY`, `DECODO_API_KEY` or `PROXY_URL`. |

See `V2_PILOT_RAILWAY_ALIGNMENT.md` §5 and §8 for full tables and CLI checks.
