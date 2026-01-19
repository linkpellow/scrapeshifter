"""
Capsolver integration for Chimera Core.
Detect and solve reCAPTCHA v2. Pause-on-failure: if balance < $1, set SYSTEM_STATE:PAUSED.
Optional WEBHOOK_URL for zero-balance and high-latency alerts.
"""
import asyncio
import os
from typing import Optional

import httpx

CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY")
CAPSOLVER_URL = "https://api.capsolver.com"
PAUSED_KEY = "SYSTEM_STATE:PAUSED"
MIN_BALANCE = 1.0

_redis = None


def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    url = os.getenv("REDIS_URL") or os.getenv("APP_REDIS_URL")
    if not url:
        return None
    try:
        import redis
        _redis = redis.from_url(url, decode_responses=True)
        return _redis
    except Exception:
        return None


def is_available() -> bool:
    return bool(CAPSOLVER_API_KEY)


async def get_balance() -> float:
    if not CAPSOLVER_API_KEY:
        return 0.0
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{CAPSOLVER_URL}/getBalance",
                json={"clientKey": CAPSOLVER_API_KEY},
            )
            r.raise_for_status()
            data = r.json()
        return float(data.get("balance", 0.0))
    except Exception:
        return 0.0


def _set_system_paused(reason: str) -> None:
    r = _get_redis()
    if r:
        try:
            r.set(PAUSED_KEY, reason or "1")
        except Exception:
            pass


async def _fire_webhook_async(reason: str, balance: Optional[float] = None) -> None:
    url = os.getenv("WEBHOOK_URL")
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(
                url,
                json={"reason": reason, "balance": balance, "event": "system_paused"},
            )
    except Exception:
        pass


async def _require_balance() -> None:
    bal = await get_balance()
    if bal < MIN_BALANCE:
        reason = f"capsolver_balance_below_{MIN_BALANCE}"
        _set_system_paused(reason)
        try:
            asyncio.create_task(_fire_webhook_async(reason, balance=bal))
        except Exception:
            pass
        raise RuntimeError(f"Capsolver balance ${bal:.2f} < ${MIN_BALANCE}; SYSTEM_STATE:PAUSED set")


async def solve_recaptcha_v2(website_url: str, site_key: str) -> str:
    if not CAPSOLVER_API_KEY:
        raise RuntimeError("CAPSOLVER_API_KEY not set")
    await _require_balance()
    payload = {
        "clientKey": CAPSOLVER_API_KEY,
        "task": {
            "type": "ReCaptchaV2TaskProxyLess",
            "websiteURL": website_url,
            "websiteKey": site_key,
        },
    }
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{CAPSOLVER_URL}/createTask", json=payload)
        r.raise_for_status()
        data = r.json()
    if data.get("errorId") != 0:
        raise RuntimeError(data.get("errorDescription", "Capsolver createTask failed"))
    task_id = data.get("taskId")
    if not task_id:
        raise RuntimeError("No taskId from Capsolver")
    for _ in range(60):
        await asyncio.sleep(2)
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{CAPSOLVER_URL}/getTaskResult",
                json={"clientKey": CAPSOLVER_API_KEY, "taskId": task_id},
            )
            r.raise_for_status()
            res = r.json()
        if res.get("status") == "ready":
            return res.get("solution", {}).get("gRecaptchaResponse", "")
        if res.get("status") == "failed":
            raise RuntimeError(res.get("errorDescription", "Capsolver solve failed"))
    raise RuntimeError("Capsolver solve timeout")


async def solve_hcaptcha(website_url: str, site_key: str) -> str:
    """Solve HCaptcha via Capsolver (HCaptchaTaskProxyLess)."""
    if not CAPSOLVER_API_KEY:
        raise RuntimeError("CAPSOLVER_API_KEY not set")
    await _require_balance()
    payload = {
        "clientKey": CAPSOLVER_API_KEY,
        "task": {
            "type": "HCaptchaTaskProxyLess",
            "websiteURL": website_url,
            "websiteKey": site_key,
        },
    }
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{CAPSOLVER_URL}/createTask", json=payload)
        r.raise_for_status()
        data = r.json()
    if data.get("errorId") != 0:
        raise RuntimeError(data.get("errorDescription", "Capsolver HCaptcha createTask failed"))
    task_id = data.get("taskId")
    if not task_id:
        raise RuntimeError("No taskId from Capsolver")
    for _ in range(60):
        await asyncio.sleep(2)
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{CAPSOLVER_URL}/getTaskResult",
                json={"clientKey": CAPSOLVER_API_KEY, "taskId": task_id},
            )
            r.raise_for_status()
            res = r.json()
        if res.get("status") == "ready":
            return res.get("solution", {}).get("gRecaptchaResponse", res.get("solution", {}).get("token", ""))
        if res.get("status") == "failed":
            raise RuntimeError(res.get("errorDescription", "Capsolver HCaptcha solve failed"))
    raise RuntimeError("Capsolver HCaptcha solve timeout")


async def solve_recaptcha_v3(website_url: str, site_key: str, page_action: str = "verify") -> str:
    """Solve reCAPTCHA v3 (token-only; no image challenge)."""
    if not CAPSOLVER_API_KEY:
        raise RuntimeError("CAPSOLVER_API_KEY not set")
    await _require_balance()
    payload = {
        "clientKey": CAPSOLVER_API_KEY,
        "task": {
            "type": "ReCaptchaV3TaskProxyLess",
            "websiteURL": website_url,
            "websiteKey": site_key,
            "pageAction": page_action,
        },
    }
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{CAPSOLVER_URL}/createTask", json=payload)
        r.raise_for_status()
        data = r.json()
    if data.get("errorId") != 0:
        raise RuntimeError(data.get("errorDescription", "Capsolver ReCaptchaV3 createTask failed"))
    task_id = data.get("taskId")
    if not task_id:
        raise RuntimeError("No taskId from Capsolver")
    for _ in range(60):
        await asyncio.sleep(2)
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{CAPSOLVER_URL}/getTaskResult", json={"clientKey": CAPSOLVER_API_KEY, "taskId": task_id})
            r.raise_for_status()
            res = r.json()
        if res.get("status") == "ready":
            return res.get("solution", {}).get("gRecaptchaResponse", "")
        if res.get("status") == "failed":
            raise RuntimeError(res.get("errorDescription", "Capsolver ReCaptchaV3 solve failed"))
    raise RuntimeError("Capsolver ReCaptchaV3 solve timeout")


async def solve_turnstile(website_url: str, site_key: str) -> str:
    """Solve Cloudflare Turnstile (token-only)."""
    if not CAPSOLVER_API_KEY:
        raise RuntimeError("CAPSOLVER_API_KEY not set")
    await _require_balance()
    payload = {
        "clientKey": CAPSOLVER_API_KEY,
        "task": {
            "type": "AntiTurnstileTaskProxyLess",
            "websiteURL": website_url,
            "websiteKey": site_key,
        },
    }
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{CAPSOLVER_URL}/createTask", json=payload)
        r.raise_for_status()
        data = r.json()
    if data.get("errorId") != 0:
        raise RuntimeError(data.get("errorDescription", "Capsolver Turnstile createTask failed"))
    task_id = data.get("taskId")
    if not task_id:
        raise RuntimeError("No taskId from Capsolver")
    for _ in range(60):
        await asyncio.sleep(2)
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{CAPSOLVER_URL}/getTaskResult", json={"clientKey": CAPSOLVER_API_KEY, "taskId": task_id})
            r.raise_for_status()
            res = r.json()
        if res.get("status") == "ready":
            sol = res.get("solution", {})
            return sol.get("token", sol.get("gRecaptchaResponse", ""))
        if res.get("status") == "failed":
            raise RuntimeError(res.get("errorDescription", "Capsolver Turnstile solve failed"))
    raise RuntimeError("Capsolver Turnstile solve timeout")
