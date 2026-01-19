# People-Search Enrichment — Execution Record

**Sites:** ThatsThem, SearchPeopleFree, ZabaSearch, FastPeopleSearch, TruePeopleSearch, AnyWho.

This doc records what the lead executes and what runs automatically. It is not an operator to‑do list.

---

## 1. Chimera Core

- **Running:** `railway service status chimera-core` or Dashboard.
- **Start:** `chimera-core/main.py` via `python main.py`; mission loop BRPOPs `chimera:missions`.

---

## 2. Same Redis (Scrapegoat + Chimera Core)

- **Verified via CLI:** `railway variable list -s scrapegoat` and `-s chimera-core` both show `REDIS_URL` → `redis.railway.internal:6379`.
- **Code:** Both use `REDIS_URL` or `APP_REDIS_URL`.

---

## 3. Seed blueprints (6 Magazine domains)

- **Automatic:** `SEED_MAGAZINE_ON_STARTUP=1` set on Scrapegoat via `railway variable set -s scrapegoat SEED_MAGAZINE_ON_STARTUP=1`. Scrapegoat startup seeds `blueprint:{domain}` for all 6. Log: `Seed-magazine on startup: done (6 Magazine domains)`.
- **Manual (when Scrapegoat is up):** `curl -s -X POST "https://<SCRAPEGOAT_PUBLIC_DOMAIN>/api/blueprints/seed-magazine"` → `{"status":"ok","seeded":[...],"count":6}`. `railway run -s scrapegoat -- python scrapegoat/scripts/seed_magazine_blueprints.py` cannot reach `redis.railway.internal` from a local shell; use the API.
- **Code:** `scrapegoat/main.py` startup, `POST /api/blueprints/seed-magazine`, `scrapegoat/scripts/seed_magazine_blueprints.py`, `app/enrichment/blueprint_commit.commit_blueprint_impl`.

---

## 4. CapSolver on Chimera Core

- **Verified via CLI:** `railway variable list -s chimera-core` includes `CAPSOLVER_API_KEY`.
- **Code:** `chimera-core/capsolver.py`, `workers._detect_and_solve_captcha`.

---

## 5. Decodo (or proxy) on Chimera Core

- **Verified via CLI:** `railway variable list -s chimera-core` includes `DECODO_API_KEY`.
- **Code:** `chimera-core/network.get_proxy_config`, `workers` context.

---

## 6. Chimera Brain

- **Verified via CLI:** `railway variable list -s chimera-core` includes `CHIMERA_BRAIN_ADDRESS` → `chimera-brain-v1.railway.internal:50051`.
- **Code:** `chimera-core/main.py`, `PhantomWorker`, `process_vision`, `_deep_search_extract_via_vision`.

---

## Lead input (queue/CSV)

Leads in `leads_to_enrich` must include **`name`** (or **`fullName`**) or **`firstName`** and **`lastName`**, and **`linkedinUrl`**. Pipeline normalizes `name`; ChimeraStation returns FAIL if no searchable name.

---

## Commands the lead runs (from repo root, Railway linked)

```bash
# Variables
railway variable list -s scrapegoat
railway variable list -s chimera-core

# Ensure Scrapegoat seeds on startup
railway variable set -s scrapegoat SEED_MAGAZINE_ON_STARTUP=1

# Redeploy Scrapegoat so startup runs (seeds when up)
railway redeploy -s scrapegoat -y

# Optional: seed via API when Scrapegoat is reachable
# curl -s -X POST "https://<SCRAPEGOAT_PUBLIC_DOMAIN>/api/blueprints/seed-magazine"
```

---

## References

- **Env by service:** `V2_PILOT_RAILWAY_ALIGNMENT.md` §5 and §8.
- **Flow:** `V2_PILOT_RAILWAY_ALIGNMENT.md` §8 (people-search).
