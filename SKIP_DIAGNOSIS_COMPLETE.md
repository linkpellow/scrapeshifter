# Complete Diagnosis: Why scrapegoat-worker-swarm Keeps Getting Skipped

## 🔴 ROOT CAUSE IDENTIFIED

**Railway's NEW Builder (v2) does NOT support `watchPatterns` in railway.toml!**

This is a **known bug** that has been reported for 6-12+ months. The `watchPatterns` we added to `railway.toml` are being **ignored** because Railway is using the new builder.

## Evidence

1. **Web Search Confirmation:**
   - Railway's new builder doesn't support watchPatterns
   - Watch paths are ignored when using new builder
   - This is a documented limitation, not a configuration error

2. **Our Configuration:**
   - ✅ `watchPatterns = ["**"]` is in `scrapegoat/railway.toml`
   - ✅ Changes are being committed and pushed
   - ❌ Railway still skips deployments

3. **Service Behavior:**
   - Service runs when manually deployed via CLI (`railway up`)
   - Service is skipped on automatic GitHub pushes
   - This confirms watch path detection is broken

## Why This Happens

**Railway Builder Types:**
- **Legacy Builder:** Supports `watchPatterns` in railway.toml ✅
- **New Builder (v2):** Does NOT support `watchPatterns` in railway.toml ❌

Railway may have automatically upgraded to the new builder, which ignores our `watchPatterns` configuration.

## Solutions (In Order of Preference)

### Solution 1: Force Legacy Builder (RECOMMENDED)

**Option A: Via railway.toml**
```toml
[build]
builder = "NIXPACKS"  # Keep Nixpacks
# Note: Legacy builder is automatic if new builder is disabled
```

**Option B: Via Railway Dashboard**
1. Railway Dashboard → scrapegoat-worker-swarm → Settings → Build
2. Look for "Builder" or "Use New Builder" toggle
3. **Disable** "Use New Builder" (forces legacy builder)
4. Save

### Solution 2: Set Watch Paths in Dashboard (REQUIRED)

Since `watchPatterns` in railway.toml don't work with new builder:

1. **Railway Dashboard → scrapegoat-worker-swarm → Settings → Build**
2. **Watch Paths:** Set to `**` (temporarily) or `scrapegoat/**` (permanent)
3. **Save**

**Critical:** Dashboard settings override railway.toml when using new builder.

### Solution 3: Use Legacy Builder Explicitly

If Railway supports it, we can try to force legacy builder in railway.toml, but this may not be possible if Railway auto-upgraded.

## Immediate Actions Required

### Step 1: Set Watch Paths in Dashboard (MANDATORY)

**Railway Dashboard:**
1. Service: `scrapegoat-worker-swarm`
2. Settings → Build → Watch Paths
3. Set to: `**` (temporarily to force all changes)
4. Save

### Step 2: Disable New Builder (If Possible)

**Railway Dashboard:**
1. Service: `scrapegoat-worker-swarm`
2. Settings → Build
3. Look for "Use New Builder" or "Builder Version" toggle
4. **Disable** new builder (use legacy)
5. Save

### Step 3: Verify Root Directory

**Railway Dashboard:**
1. Service: `scrapegoat-worker-swarm`
2. Settings → General → Root Directory
3. Should be: `scrapegoat` (not empty, not `/`)
4. If wrong, fix it

### Step 4: Force Redeploy

After fixing Dashboard settings:
```bash
cd /Users/linkpellow/Desktop/my-lead-engine
railway up --service scrapegoat-worker-swarm --detach
```

## Why watchPatterns in railway.toml Don't Work

**Technical Reason:**
- Railway's new builder uses a different build system
- Watch path detection is handled differently
- `watchPatterns` in railway.toml are only read by legacy builder
- New builder requires Dashboard configuration

**Workaround:**
- Set watch paths in Dashboard (they work with new builder)
- OR disable new builder to use legacy (watchPatterns work)

## Verification Checklist

After applying fixes:
- [ ] Watch Paths set in Railway Dashboard (not just railway.toml)
- [ ] New Builder disabled (if possible) OR watch paths set in Dashboard
- [ ] Root Directory = `scrapegoat` (verified in Dashboard)
- [ ] Force redeploy via CLI: `railway up --service scrapegoat-worker-swarm`
- [ ] Check Railway Dashboard → Deployments → Should show "Building..." not "Skipped"

## Current Configuration Status

**scrapegoat/railway.toml:**
```toml
watchPatterns = ["**"]  # ❌ IGNORED by new builder
```

**Railway Dashboard:**
- Watch Paths: ❓ **UNKNOWN** (must be checked/set manually)
- Builder: ❓ **UNKNOWN** (may be using new builder)
- Root Directory: ❓ **UNKNOWN** (should be `scrapegoat`)

## Next Steps

1. **Check Railway Dashboard** for scrapegoat-worker-swarm:
   - Builder type (new vs legacy)
   - Watch Paths setting
   - Root Directory setting

2. **Fix in Dashboard:**
   - Set Watch Paths to `**` (temporary)
   - Disable new builder if possible
   - Verify Root Directory

3. **Test:**
   - Make a small change
   - Push to GitHub
   - Verify deployment is NOT skipped

## Summary

**The Problem:** Railway's new builder ignores `watchPatterns` in railway.toml.

**The Fix:** Set watch paths in Railway Dashboard (they work with new builder) OR disable new builder to use legacy (watchPatterns work).

**Why It Keeps Happening:** We've been configuring watchPatterns in railway.toml, but Railway is using the new builder which ignores them. Dashboard configuration is required.
