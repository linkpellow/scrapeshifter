# Fix Railway Watch Paths - Force Deployments

## Problem
Railway is skipping 'brainscraper' and 'scrapegoat-worker-swarm' because it doesn't see changes in the expected watch paths.

## Directory Audit Results

**Verified Directory Structure:**
- ✅ `brainscraper/` - Frontend (Next.js)
- ✅ `scrapegoat/` - Worker service (Python)
- ✅ `chimera-core/` - Worker service (Python)
- ✅ `chimera_brain/` - Brain service (Python)

**Railway Service Mapping:**
- **brainscraper** → Root: `brainscraper/`
- **scrapegoat-worker-swarm** → Root: `scrapegoat/` (or possibly watches both `scrapegoat/` and `chimera-core/`)

## Solution: Standardize Watch Paths

### Step 1: Railway Dashboard - brainscraper Service

1. Go to: Railway Dashboard → **brainscraper** service
2. Settings → **Build**
3. Find **"Watch Paths"** field
4. **Change to:** `**` (global - temporarily to force full scan)
5. **Alternative (permanent):** `brainscraper/**`
6. Save changes

### Step 2: Railway Dashboard - scrapegoat-worker-swarm Service

1. Go to: Railway Dashboard → **scrapegoat-worker-swarm** service
2. Settings → **Build**
3. Find **"Watch Paths"** field
4. **Change to include both:**
   ```
   scrapegoat/**
   chimera-core/**
   ```
   Or use comma-separated: `scrapegoat/**,chimera-core/**`
5. Save changes

**Note:** If `scrapegoat-worker-swarm` only watches `scrapegoat/`, Railway won't detect changes in `chimera-core/`. You may need to:
- Create separate services for `scrapegoat` and `chimera-core`, OR
- Set watch paths to include both directories

### Step 3: Force Build via Empty Commit

After updating watch paths in Dashboard, trigger a fresh push event:

```bash
cd /Users/linkpellow/Desktop/my-lead-engine
git commit --allow-empty -m "ops: force redeploy by triggering watch paths"
git push origin main
```

### Step 4: Verify Build Logs

1. Go to: Railway Dashboard → **Deployments** tab
2. Monitor latest deployments for:
   - **brainscraper**: Should show "Building..." (not "Skipped")
   - **scrapegoat-worker-swarm**: Should show "Building..." (not "Skipped")

**Expected Status:**
- ✅ "Building..." - Watch paths detected changes
- ❌ "Skipped" - Watch paths didn't detect changes (needs fix)

## Current Configuration

### brainscraper/railway.toml
```toml
[build]
builder = "DOCKERFILE"

[deploy]
healthcheckPath = "/"
healthcheckTimeout = 180
```

**Watch Paths (Dashboard):** Should be `brainscraper/**` or `**` (temporary)

### scrapegoat/railway.toml
```toml
[build]
builder = "NIXPACKS"
buildCommand = "pip install -r requirements.txt && playwright install chromium"

[deploy]
startCommand = "python3 main.py"
healthcheckPath = "/health"
```

**Watch Paths (Dashboard):** Should be `scrapegoat/**` (or `scrapegoat/**,chimera-core/**` if service watches both)

### chimera-core/railway.toml
```toml
[build]
builder = "NIXPACKS"
buildCommand = "pip install -r requirements.txt && playwright install chromium"

[deploy]
startCommand = "python main.py"
healthcheckPath = "/health"
```

**Watch Paths (Dashboard):** Should be `chimera-core/**` (if separate service) or included in scrapegoat-worker-swarm

## Troubleshooting

### Issue: "Still showing Skipped after watch path change"
**Fix:**
1. Wait 1-2 minutes for Railway to update
2. Make a small change to a file in the watched directory
3. Commit and push: `git commit --allow-empty -m "ops: trigger build" && git push`
4. Check Railway Dashboard → Deployments

### Issue: "scrapegoat-worker-swarm doesn't exist"
**Fix:**
- Check actual service name in Railway Dashboard
- May be named: `scrapegoat`, `scrapegoat-worker`, or separate services for `scrapegoat` and `chimera-core`

### Issue: "Watch Paths field not visible"
**Fix:**
- Watch Paths may be in: Settings → Build → Advanced
- Or: Settings → Source → Watch Paths
- Railway UI may vary by service type

## Verification Checklist

- [ ] brainscraper Watch Paths set to `brainscraper/**` or `**` (temporary)
- [ ] scrapegoat-worker-swarm Watch Paths include `scrapegoat/**` (and `chimera-core/**` if needed)
- [ ] Empty commit created and pushed
- [ ] Railway Dashboard shows "Building..." status (not "Skipped")
- [ ] Build logs show files being detected

## Quick Reference

**Watch Path Syntax:**
- `brainscraper/**` - All files in brainscraper directory
- `**` - All files in repository (use temporarily for debugging)
- `scrapegoat/**,chimera-core/**` - Multiple directories (comma-separated)

**Railway Watch Path Logic:**
- Railway only triggers builds when files in Watch Paths change
- If Watch Paths are too narrow, changes outside those paths are ignored
- If Watch Paths are too broad, unnecessary builds may trigger
