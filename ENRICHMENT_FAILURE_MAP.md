# Why It’s Failing: Mechanisms vs. What’s Actually Breaking

You’ve added CAPTCHA, honeypots, rate limiting, DOM parsing, OCR, etc. Those apply at the **site/protocol** layer. The current failures are mostly **before** we get to that layer, or in **different** layers.

---

## 0. AbortError (BodyStreamBuffer was aborted) – The 330s Fix

**Symptom:** `AbortError: BodyStreamBuffer was aborted` or stream closing before the run finishes.

**Cause:** The **client** (browser/Cursor) or **load balancer / reverse proxy** stops waiting while the backend is still processing. Enrichment can run 6×90s Chimera + overhead; the connection must stay open.

**Fix (infrastructure, not code):**

1. **Railway** – Brainscraper service → Settings → set **request/response timeout** to **330–360 seconds**.
2. **Proxy (Cloudflare)** – In front of Brainscraper, set timeout to **330–360 seconds**.

The route `process-one-stream` already uses `maxDuration = 330` and a 330s fetch timeout. If **Railway** or **Proxy (Cloudflare)** uses a lower value, it will close the connection first.

**Redis Alignment:** REDIS_URL must match between **Scrapegoat** and **Chimera Core**. If they differ, Core never sees `chimera:missions` → **queued but never processed**. Run `./scripts/railway-people-search-align.sh` to copy Scrapegoat’s REDIS_URL to chimera-core and redeploy.

**Chimera "black hole" (waiting_core, no LPUSH):**  
If `bottleneck_hint` shows `chimera_timeout_or_fail_count=0` and `processed=false`, the request reaches the enrichment station but Chimera Core never LPUSHes. Usually:

- **REDIS_URL mismatch** (queued but never processed) – chimera-core must use the **same** Redis as Scrapegoat. Run `./scripts/railway-people-search-align.sh`.
- **Core exits before listening** – Check chimera-core logs for crashes during **CreepJS**, **worker init**, or DB startup.

---

## 1. What each mechanism is for

| Mechanism | What it handles | Where it runs |
|-----------|-----------------|---------------|
| **CAPTCHA solving** (CapSolver, etc.) | reCAPTCHA, Turnstile, Cloudflare challenge, etc. | HTTP: `_make_request` on 403/503. **Chimera Core:** `_detect_and_solve_captcha`. **Browser (TruePeopleSearch):** wired in `_search_with_browser` via `_try_solve_captcha_in_browser`. |
| **Honeypots** | Form traps, fake fields | Form fill (Chimera pivot, etc.). Doesn’t help if we never load the form. |
| **Rate limiting** | 429, Retry-After, backoff | `_make_request`, circuit breaker, `RateLimitState`. Doesn’t help if the request fails in our client before we get a response. |
| **DOM parsing / selectors** | Changing layouts, extraction | BlueprintExtractor, TruePeopleSearch card selectors, LLM parse. Doesn’t help if we never get valid HTML (block, empty, or client error). |
| **OCR** | Image CAPTCHA, scanned content | Used where we explicitly call it. Doesn’t help if we fail earlier. |
| **verify_page_content** | Soft blocks, “empty” pages | Block indicators + success keywords + vision. **TruePeopleSearch browser path:** now uses `detect_captcha_in_html`, CAPTCHA solver, and `_verify_with_vision`. |
| **Vision verify** | “Is this a real results page or block/empty?” | `_verify_with_vision` in base. **TruePeopleSearch:** `verify_page_content(..., use_vision=True, screenshot_path=...)` in `_search_with_browser`. |

So: we have a lot of **site‑facing** logic. The issues below are either **upstream** of that, or in **browser‑specific** wiring.

---

## 2. What’s actually failing (and where the gap is)

| Observed failure | Mechanism that *could* help | Why it doesn’t | Real cause / gap |
|------------------|----------------------------|----------------|------------------|
| **Chimera: `waiting_core`, no LPUSH** | CAPTCHA, pivot, DOM, etc. in Chimera Core | Core often never runs the mission (no consume or crash before pivot). | **Infra:** REDIS_URL, Core not running, or exit in DB/CreepJS/worker init. Not a site-defense problem. |
| **Scraper HTTP: “impersonate chrome119 is not supported”** | Rate limit, CAPTCHA, DOM | Request fails in `curl_cffi` **before** we get a response. No status, no HTML. | **Our stack:** `curl_cffi` 0.5.x doesn’t support chrome116/119/120. IMPERSONATE_PROFILES was using those. Fixed to chrome101–110. |
| **Scraper HTTP: “object NoneType can’t be used in ‘await’ expression”** | — | Follows from the impersonate error in the client. | Same as above; fixing impersonate fixes this. |
| **Scraper browser: “No success keywords found – page may be empty or blocked”** | CAPTCHA, block detection, vision | 1) `verify_page_content` does **not** call `detect_captcha_in_html`. 2) Vision verify is never used (`use_vision`/`screenshot_path` not passed). 3) If the page is a soft block with different copy, block_indicators can miss it. | **Gap:** In **browser/Playwright** flows we never run CAPTCHA detection or solving on the fetched HTML. Success keywords can also be wrong or too strict for “no results” or changed layout. |
| **Skip-trace: 404 on alternative API** | — | Wrong host/path. | **Config:** `skip-tracing-api.p.rapidapi.com` was wrong. Fallback now uses `skip-tracing-working-api.p.rapidapi.com` like the primary. |

---

## 3. “We’ve covered every base” – what’s actually covered

- **HTTP path (BlueprintExtractor, `_make_request`):**  
  - CAPTCHA: ✅ on 403/503 we run `detect_captcha_in_html` and `get_captcha_solver()`.  
  - Rate limits, circuit breaker, retries: ✅.  
  - Impersonate: ✅ **after** the chrome101–110 fix and redeploy.

- **Chimera Core (when it runs):**  
  - CAPTCHA, pivot, VLM: ✅ in workers.  
  - **But:** if Core never gets the mission or exits earlier, none of this runs. That’s infra/Redis/startup, not “one more CAPTCHA.”

- **Browser path (TruePeopleSearch, Playwright):**  
  - `verify_page_content`: block_indicators + success_keywords + **`_verify_with_vision`** (screenshot).  
  - **Wired:** `detect_captcha_in_html`, CAPTCHA solver via `_try_solve_captcha_in_browser` on invalid/blocked; retry and re-verify after solve.

---

## 4. What’s left to do

1. **Chimera not LPUSHing**  
   - Fix: `railway-people-search-align.sh`, REDIS_URL on chimera-core, check Core logs for exits before missions.

2. **Impersonate / client_error**  
   - Fix: already in code (chrome101–110). Redeploy Scrapegoat.

3. **Browser “empty or blocked”**  
   - Options:  
     - In `verify_page_content` (or the caller): when we would return False, run `detect_captcha_in_html(html)`; if CAPTCHA, try solver and retry (needs solver wired to Playwright or to a “solve then reload” flow).  
     - Start passing `use_vision=True` and a screenshot into `verify_page_content` so `_verify_with_vision` runs.  
     - Relax or extend success_keywords / block_indicators for TruePeopleSearch’s current copy.

4. **Which site works**  
   - Use **`GET /probe/sites`** (and `?site=fastpeoplesearch.com` for one).  
   - It uses the same HTTP/stealth stack as production. After the impersonate fix and redeploy, `ok` means we got a non‑blocked, “success‑like” page; `block` / `empty` / `client_error` / `timeout` narrow it down.

---

## 5. Verification Command: GET /probe/sites → whitelist CHIMERA_PROVIDERS by ok

Use **GET /probe/sites** to see which people-search sites return `ok`. **Whitelist only `ok` sites in CHIMERA_PROVIDERS**; exclude `block`, `empty`, `client_error`, `timeout`. After Scrapegoat redeploy, re-run to refresh.

After Scrapegoat is redeployed (with the impersonate fix):

```bash
# All Scraper sites
curl -s "https://<SCRAPEGOAT_URL>/probe/sites"

# One site
curl -s "https://<SCRAPEGOAT_URL>/probe/sites?site=fastpeoplesearch.com"
```

Example:

```json
{
  "fastpeoplesearch.com": "ok",
  "thatsthem.com": "block",
  "truepeoplesearch.com": "client_error"
}
```

- **`ok`** – reached the page and it looks like a normal people-search page (good candidate to focus on).  
- **`block`** – block-like text (Cloudflare, “blocked”, etc.).  
- **`empty`** – no block phrases, no success keywords (soft block or “no results” style page).  
- **`client_error`** – our client failed (e.g. impersonate, connection).  
- **`timeout`** – request timed out.  
- **`http_403`** etc. – HTTP 4xx/5xx.

Use `ok` to choose `CHIMERA_PROVIDERS` or to prioritize which Scraper site to fix first (e.g. selectors, browser, or CAPTCHA for that domain).

---

## 6. How to verify it's actually fixed

1. **AbortError / 330s:** Set **Railway** and **Proxy (Cloudflare)** request timeouts to 330–360s. Run an enrichment from v2-pilot; the stream should complete without `BodyStreamBuffer was aborted`.

2. **Redis Alignment / Chimera black hole:** Run `./scripts/railway-people-search-align.sh` so REDIS_URL matches between Scrapegoat and Chimera Core (prevents *queued but never processed*). Redeploy chimera-core and scrapegoat; check chimera-core logs for `CreepJS`, `worker init`—no exit before "listening" or "BRPOP".

3. **Verification Command – GET /probe/sites:**  
   ```bash
   curl -s "https://<SCRAPEGOAT_URL>/probe/sites"
   ```  
   Whitelist only sites with status `ok` in `CHIMERA_PROVIDERS`. Exclude `block`, `empty`, `client_error`, `timeout`. After Scrapegoat redeploy, re-run to refresh.
