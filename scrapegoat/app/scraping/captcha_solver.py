"""
CAPTCHA Solver Module - CAPSOLVER Integration
Automatically detects and solves CAPTCHAs encountered during scraping

Supported Types:
- reCAPTCHA v2/v3
- hCaptcha
- Cloudflare Turnstile/Challenges
- AWS WAF
- ImageToText (for simple image CAPTCHAs)
"""
import os
import re
import time
import asyncio
import base64
from typing import Dict, Any, Optional, Tuple
import httpx
from loguru import logger  # type: ignore

CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY")
CAPSOLVER_API_URL = "https://api.capsolver.com"

class CaptchaSolver:
    """CAPSOLVER API wrapper for automatic CAPTCHA solving"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or CAPSOLVER_API_KEY
        if not self.api_key:
            logger.warning("⚠️ CAPSOLVER_API_KEY not set - CAPTCHA solving disabled")
        self.timeout = 120  # 2 minutes max for CAPTCHA solving
    
    def is_available(self) -> bool:
        """Check if CAPSOLVER is configured"""
        return bool(self.api_key)
    
    async def _api_request(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make request to CAPSOLVER API"""
        if not self.api_key:
            raise Exception("CAPSOLVER_API_KEY not configured")
        
        url = f"{CAPSOLVER_API_URL}/{endpoint}"
        headers = {"Content-Type": "application/json"}
        payload["clientKey"] = self.api_key
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
    
    async def solve_recaptcha_v2(
        self,
        website_url: str,
        site_key: str,
        proxy: Optional[str] = None
    ) -> str:
        """Solve reCAPTCHA v2"""
        task_type = "ReCaptchaV2TaskProxyLess" if not proxy else "ReCaptchaV2Task"
        
        payload = {
            "task": {
                "type": task_type,
                "websiteURL": website_url,
                "websiteKey": site_key,
            }
        }
        
        if proxy:
            payload["task"]["proxy"] = proxy
        
        return await self._solve_task(payload, "gRecaptchaResponse")
    
    async def solve_recaptcha_v3(
        self,
        website_url: str,
        site_key: str,
        page_action: str = "verify",
        proxy: Optional[str] = None
    ) -> str:
        """Solve reCAPTCHA v3"""
        task_type = "ReCaptchaV3TaskProxyLess" if not proxy else "ReCaptchaV3Task"
        
        payload = {
            "task": {
                "type": task_type,
                "websiteURL": website_url,
                "websiteKey": site_key,
                "pageAction": page_action,
            }
        }
        
        if proxy:
            payload["task"]["proxy"] = proxy
        
        return await self._solve_task(payload, "gRecaptchaResponse")
    
    async def solve_turnstile(
        self,
        website_url: str,
        site_key: str,
        proxy: Optional[str] = None
    ) -> str:
        """Solve Cloudflare Turnstile"""
        task_type = "AntiTurnstileTaskProxyLess" if not proxy else "AntiTurnstileTask"
        
        payload = {
            "task": {
                "type": task_type,
                "websiteURL": website_url,
                "websiteKey": site_key,
            }
        }
        
        if proxy:
            payload["task"]["proxy"] = proxy
        
        return await self._solve_task(payload, "token")

    async def solve_hcaptcha(
        self,
        website_url: str,
        site_key: str,
        proxy: Optional[str] = None
    ) -> str:
        """Solve hCaptcha via Capsolver (HCaptchaTaskProxyLess)."""
        task_type = "HCaptchaTaskProxyLess" if not proxy else "HCaptchaTask"
        task = {"type": task_type, "websiteURL": website_url, "websiteKey": site_key}
        if proxy:
            task["proxy"] = proxy
        create = await self._api_request("createTask", {"task": task})
        if create.get("errorId") != 0:
            raise Exception(create.get("errorDescription", "HCaptcha createTask failed"))
        task_id = create.get("taskId")
        if not task_id:
            raise Exception("No taskId from Capsolver")
        for _ in range(60):
            await asyncio.sleep(2)
            res = await self._api_request("getTaskResult", {"taskId": task_id})
            if res.get("status") == "ready":
                sol = res.get("solution", {})
                return sol.get("gRecaptchaResponse", sol.get("token", ""))
            if res.get("status") == "failed":
                raise Exception(res.get("errorDescription", "HCaptcha solve failed"))
        raise Exception("HCaptcha solve timeout")
    
    async def solve_cloudflare_challenge(
        self,
        website_url: str,
        proxy: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Solve Cloudflare challenge (returns cookies + user agent)"""
        task_type = "AntiCloudflareTask" if proxy else "AntiCloudflareTaskProxyLess"
        
        payload = {
            "task": {
                "type": task_type,
                "websiteURL": website_url,
            }
        }
        
        if proxy:
            payload["task"]["proxy"] = proxy
        
        if metadata:
            payload["task"].update(metadata)
        
        result = await self._solve_task(payload, "cookie", is_dict=True)
        
        # Cloudflare returns cookies + user agent
        return result if isinstance(result, dict) else {"cookie": str(result)}
    
    async def solve_aws_waf(
        self,
        website_url: str,
        proxy: Optional[str] = None
    ) -> str:
        """Solve AWS WAF challenge"""
        task_type = "AntiAwsWafTaskProxyLess" if not proxy else "AntiAwsWafTask"
        
        payload = {
            "task": {
                "type": task_type,
                "websiteURL": website_url,
            }
        }
        
        if proxy:
            payload["task"]["proxy"] = proxy
        
        return await self._solve_task(payload, "cookie")
    
    async def solve_image_captcha(self, image_data: bytes, module: str = "common") -> str:
        """Solve simple image CAPTCHA (ImageToText)"""
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        
        payload = {
            "task": {
                "type": "ImageToTextTask",
                "module": module,
                "body": image_b64,
            }
        }
        
        return await self._solve_task(payload, "text")
    
    async def _solve_task(
        self,
        task_payload: Dict[str, Any],
        result_key: str,
        is_dict: bool = False
    ) -> Any:
        """
        Create task, poll for result, return solution
        
        Args:
            task_payload: Task configuration
            result_key: Key to extract from solution (e.g., "gRecaptchaResponse", "token")
            is_dict: If True, return full solution dict instead of single key
            
        Returns:
            Solution value or dict
        """
        # Create task
        create_response = await self._api_request("createTask", task_payload)
        
        if create_response.get("errorId") != 0:
            error = create_response.get("errorDescription", "Unknown error")
            raise Exception(f"CAPSOLVER task creation failed: {error}")
        
        task_id = create_response.get("taskId")
        if not task_id:
            raise Exception("No taskId in CAPSOLVER response")
        
        logger.info(f"🧩 CAPTCHA task created: {task_id}")
        
        # Poll for result (max 2 minutes)
        max_wait = 120
        poll_interval = 2
        elapsed = 0
        
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            
            result_response = await self._api_request("getTaskResult", {"taskId": task_id})
            
            status = result_response.get("status")
            
            if status == "ready":
                solution = result_response.get("solution", {})
                logger.success(f"✅ CAPTCHA solved: {task_id}")
                
                if is_dict:
                    return solution
                return solution.get(result_key, "")
            
            if status == "failed":
                error = result_response.get("errorDescription", "Solving failed")
                raise Exception(f"CAPTCHA solving failed: {error}")
            
            # Still processing
            if elapsed % 10 == 0:
                logger.debug(f"⏳ CAPTCHA solving... ({elapsed}s)")
        
        raise Exception(f"CAPTCHA solving timeout after {max_wait}s")
    
    async def get_balance(self) -> float:
        """Check CAPSOLVER account balance"""
        try:
            response = await self._api_request("getBalance", {})
            return response.get("balance", 0.0)
        except Exception as e:
            logger.warning(f"Failed to check CAPSOLVER balance: {e}")
            return 0.0


def detect_captcha_in_html(html: str) -> Optional[Dict[str, str]]:
    """
    Detect CAPTCHA type and site key from HTML response
    
    Returns:
        Dict with type and site_key if found, None otherwise
    """
    html_lower = html.lower()
    
    # reCAPTCHA v2
    recaptcha_v2_pattern = r'data-sitekey=["\']([^"\']+)["\']|grecaptcha\.render|recaptcha/api\.js'
    match = re.search(recaptcha_v2_pattern, html, re.IGNORECASE)
    if match:
        site_key = match.group(1) if match.lastindex else ""
        # Try to extract site key more reliably
        site_key_match = re.search(r'["\']([0-9A-Za-z_-]{40})["\']', html)
        if site_key_match:
            site_key = site_key_match.group(1)
        return {"type": "recaptcha_v2", "site_key": site_key}
    
    # reCAPTCHA v3
    recaptcha_v3_pattern = r'recaptcha/api\.js\?render=([^"\'&\s]+)'
    match = re.search(recaptcha_v3_pattern, html, re.IGNORECASE)
    if match:
        return {"type": "recaptcha_v3", "site_key": match.group(1)}
    
    # hCaptcha
    hcaptcha_pattern = r'hcaptcha\.com/1/api\.js|data-sitekey=["\']([^"\']+)["\'].*hcaptcha'
    match = re.search(hcaptcha_pattern, html, re.IGNORECASE)
    if match:
        site_key = match.group(1) if match.lastindex else ""
        return {"type": "hcaptcha", "site_key": site_key}
    
    # Cloudflare Turnstile
    turnstile_pattern = r'challenges\.cloudflare\.com/turnstile|cf-turnstile'
    if re.search(turnstile_pattern, html, re.IGNORECASE):
        site_key_match = re.search(r'["\']sitekey["\']:\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
        site_key = site_key_match.group(1) if site_key_match else ""
        return {"type": "turnstile", "site_key": site_key}
    
    # Cloudflare challenge (generic)
    if "cloudflare" in html_lower and ("challenge" in html_lower or "checking your browser" in html_lower):
        return {"type": "cloudflare_challenge", "site_key": ""}
    
    # AWS WAF
    if "aws-waf" in html_lower or "x-aws-waf" in html_lower:
        return {"type": "aws_waf", "site_key": ""}
    
    return None


def is_cloudflare_challenge(status_code: int, html: str) -> bool:
    """Check if response is a Cloudflare challenge"""
    if status_code not in [403, 503]:
        return False
    
    html_lower = html.lower()
    indicators = [
        "checking your browser",
        "cloudflare",
        "cf-ray",
        "just a moment",
        "challenge-platform",
    ]
    
    return any(indicator in html_lower for indicator in indicators)


# Global solver instance
_solver_instance: Optional[CaptchaSolver] = None

def get_captcha_solver() -> CaptchaSolver:
    """Get global CAPTCHA solver instance"""
    global _solver_instance
    if _solver_instance is None:
        _solver_instance = CaptchaSolver()
    return _solver_instance
