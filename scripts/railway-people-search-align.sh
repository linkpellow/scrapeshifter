#!/usr/bin/env bash
# One-time alignment for Chimera people-search: same Redis as Scrapegoat, 90s timeouts, redeploys.
# Run from repo root with Railway project linked: ./scripts/railway-people-search-align.sh
#
# 1) chimera-core: REDIS_URL same as Scrapegoat (needed for BRPOP chimera:missions, LPUSH chimera:results)
# 2) Scrapegoat: CHIMERA_STATION_TIMEOUT=90 (Dashboard may override railway.toml; this forces 90)
# 3) Redeploy chimera-core and scrapegoat
# 4) AbortError/330s: Railway and any proxy must allow long-lived streams (see below)
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "People-search alignment (Chimera Core + Scrapegoat)"
echo ""

# --- 0) AbortError Fix: Railway and Proxy (Cloudflare) timeouts 330–360s ---
echo "--- AbortError Fix: Railway + Proxy timeouts (330–360 seconds) ---"
echo "   If you see 'BodyStreamBuffer was aborted' or stream closing before runs finish:"
echo "   • Railway: Brainscraper service → Settings → request/response timeout = 330–360 seconds."
echo "   • Proxy (Cloudflare): In front of Brainscraper, set timeout to 330–360 seconds."
echo "   (Enrichment runs 6×90s Chimera + overhead; platform/proxy must not kill the connection first.)"
echo ""

# Require Railway CLI and project link
if ! command -v railway >/dev/null 2>&1; then
  echo "railway CLI not found. Install: https://docs.railway.app/develop/cli"
  exit 1
fi
if ! railway whoami >/dev/null 2>&1; then
  echo "railway not linked or not logged in. Run: railway login && railway link"
  exit 1
fi

# --- 1) Redis Alignment: REDIS_URL must match (Scrapegoat ↔ Chimera Core) ---
echo "--- Redis Alignment: prevent 'queued but never processed' ---"
echo "   Scrapegoat LPUSHes chimera:missions; Chimera Core BRPOPs and LPUSHes chimera:results."
echo "   If REDIS_URL differs, Core never sees missions → queued but never processed. Aligning below."
echo ""
REDIS_VAL=""
for v in REDIS_URL APP_REDIS_URL; do
  REDIS_VAL=$(railway run -s scrapegoat -- printenv "$v" 2>/dev/null || true)
  REDIS_VAL=$(printf '%s' "$REDIS_VAL" | tr -d '\n\r')
  if [ -n "$REDIS_VAL" ]; then break; fi
done
# Fallback: allow caller to pass REDIS_URL (e.g. REDIS_URL='redis://...' ./scripts/railway-people-search-align.sh)
if [ -z "$REDIS_VAL" ] && [ -n "$REDIS_URL" ]; then REDIS_VAL=$REDIS_URL; fi

if [ -n "$REDIS_VAL" ]; then
  railway variable set "REDIS_URL=$REDIS_VAL" -s chimera-core
  echo "   chimera-core: REDIS_URL set (from Scrapegoat or REDIS_URL env)"
else
  echo "   Could not read REDIS_URL/APP_REDIS_URL from Scrapegoat (railway run may not expose values)."
  echo "   Set chimera-core REDIS_URL manually: Railway Dashboard → chimera-core → Variables → REDIS_URL."
  echo "   Use the same value as Scrapegoat (redis.railway.internal) or a Variable Reference to your Redis service."
  echo "   Then: railway redeploy -s chimera-core -y"
  echo ""
  read -r -p "   Continue without setting REDIS_URL? Redeploys will still run. [y/N] " ans
  case "$ans" in [yY]|[yY][eE][sS]) ;; *) exit 1; esac
fi

# --- 2) Scrapegoat: CHIMERA_STATION_TIMEOUT=90 ---
railway variable set "CHIMERA_STATION_TIMEOUT=90" -s scrapegoat
echo "   scrapegoat: CHIMERA_STATION_TIMEOUT=90"

# --- 3) Redeploys ---
echo ""
echo "Redeploying chimera-core (picks up REDIS_URL, MISSION_TIMEOUT_SEC=90)..."
CORE_SKIP=0
if ! railway redeploy -s chimera-core -y; then
  CORE_SKIP=1
  echo "   chimera-core: redeploy skipped (service may be building or deploying). Run when idle: railway redeploy -s chimera-core -y"
fi

echo "Redeploying scrapegoat (picks up CHIMERA_STATION_TIMEOUT=90)..."
GOAT_SKIP=0
if ! railway redeploy -s scrapegoat -y; then
  GOAT_SKIP=1
  echo "   scrapegoat: redeploy skipped (service may be building or deploying). Run when idle: railway redeploy -s scrapegoat -y"
fi

echo ""
echo "Done. Chimera Core will BRPOP chimera:missions and LPUSH chimera:results; Scrapegoat will wait 90s per provider."
if [ "$CORE_SKIP" = "1" ] || [ "$GOAT_SKIP" = "1" ]; then
  echo "Reminder — run when each service is idle:"
  [ "$CORE_SKIP" = "1" ] && echo "  railway redeploy -s chimera-core -y   # pick up REDIS_URL"
  [ "$GOAT_SKIP" = "1" ] && echo "  railway redeploy -s scrapegoat -y     # pick up CHIMERA_STATION_TIMEOUT=90"
fi
echo "Verify: railway variable list -s chimera-core --kv | grep REDIS_URL"
echo "        railway variable list -s scrapegoat --kv | grep CHIMERA_STATION_TIMEOUT"
echo ""
echo "--- Chimera 'black hole' (waiting_core, no LPUSH) ---"
echo "   If bottleneck_hint shows chimera_timeout_or_fail_count=0 and processed=false:"
echo "   • Core may not be getting missions (REDIS_URL mismatch → queued but never processed) or may crash before listening."
echo "   • Check chimera-core logs for exits during 'CreepJS', 'worker init', or DB startup."
echo "   • Run this script to align REDIS_URL; then: railway redeploy -s chimera-core -y"
echo ""
echo "--- IMPERSONATE_PROFILES ---"
echo "   Do NOT set IMPERSONATE_PROFILES in env. Code uses chrome101–chrome110 only (curl_cffi 0.5.x)."
echo ""
echo "--- Verification Command: GET /probe/sites → whitelist CHIMERA_PROVIDERS by ok ---"
echo "   curl -s \"https://<SCRAPEGOAT_URL>/probe/sites\""
echo "   Use only sites with status 'ok' in CHIMERA_PROVIDERS. block/empty/client_error/timeout = exclude."
echo "   After Scrapegoat redeploy, re-run to refresh. Example: {\"fastpeoplesearch.com\":\"ok\",\"thatsthem.com\":\"block\"}."
