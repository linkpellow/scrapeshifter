"""
USHA DNC Scrub Module
Checks phone numbers against Do-Not-Call registry

Token Priority:
1. Redis (auth:usha:token) - Set by Auth Worker, refreshed automatically
2. Environment variable (USHA_JWT_TOKEN) - Static fallback
3. Cognito refresh - If refresh token available (TODO)
"""
import os
import re
import requests
from typing import Dict, Any, Optional
from loguru import logger

# Redis for dynamic token (set by Auth Worker)
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Static fallbacks from environment
USHA_JWT_TOKEN = os.getenv("USHA_JWT_TOKEN")
COGNITO_REFRESH_TOKEN = os.getenv("COGNITO_REFRESH_TOKEN")
USHA_AGENT_NUMBER = os.getenv("USHA_AGENT_NUMBER", "00044447")
REDIS_URL = os.getenv("REDIS_URL") or os.getenv("APP_REDIS_URL")

def scrub_dnc(phone: str, agent_number: str = None) -> Dict[str, Any]:
    """
    Check phone against USHA DNC registry
    
    Args:
        phone: Phone number to scrub
        agent_number: USHA agent number (defaults to env var or "00044447")
        
    Returns:
        Dictionary with status, can_contact, reason
    """
    agent_number = agent_number or USHA_AGENT_NUMBER
    
    # Get USHA token
    token = get_usha_token()
    if not token:
        # print("⚠️  USHA token not available, skipping DNC scrub")
        return {
            'status': 'UNKNOWN',
            'can_contact': True,  # Fail open if token unavailable
            'reason': 'Token not available'
        }
    
    try:
        # Clean phone number (digits only)
        cleaned_phone = re.sub(r'\D', '', phone)
        if cleaned_phone.startswith('1') and len(cleaned_phone) == 11:
            cleaned_phone = cleaned_phone[1:]  # Remove country code
        
        if len(cleaned_phone) != 10:
            return {
                'status': 'INVALID',
                'can_contact': False,
                'reason': 'Invalid phone number format'
            }
        
        # Call USHA API
        url = "https://api-business-agent.ushadvisors.com/Leads/api/leads/scrubphonenumber"
        headers = get_usha_headers()
        params = {
            'phone': cleaned_phone,
            'currentContextAgentNumber': agent_number
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Parse response
        is_dnc = (
            data.get('isDoNotCall') == True or
            data.get('contactStatus', {}).get('canContact') == False
        )
        
        reason = (data.get('reason') or 
                 data.get('contactStatus', {}).get('reason') or
                 data.get('message'))
        
        return {
            'status': 'YES' if is_dnc else 'NO',
            'can_contact': not is_dnc,
            'reason': reason
        }
        
    except requests.RequestException as e:
        logger.error(f"❌ USHA DNC scrub API error: {e}")
        # On API error, allow to proceed (fail open)
        # In production, you might want to retry or fail closed
        return {
            'status': 'ERROR',
            'can_contact': True,
            'reason': f'API error: {str(e)}'
        }
    except Exception as e:
        logger.error(f"❌ DNC scrub error: {e}")
        return {
            'status': 'ERROR',
            'can_contact': True,
            'reason': str(e)
        }

def get_usha_token() -> Optional[str]:
    """
    Get USHA JWT token with automatic fallback.
    
    Priority:
    1. Redis (auth:usha:token) - Dynamic, refreshed by Auth Worker
    2. Environment (USHA_JWT_TOKEN) - Static fallback
    3. Cognito refresh - If available (TODO)
    
    Returns:
        JWT token string or None if unavailable
    """
    # Priority 1: Redis (dynamic token from Auth Worker)
    if REDIS_AVAILABLE and REDIS_URL:
        try:
            r = redis.from_url(REDIS_URL, decode_responses=True)
            token = r.get("auth:usha:token")
            if token:
                logger.debug("🔑 Using USHA token from Redis (Auth Worker)")
                return token
        except Exception as e:
            logger.warning(f"⚠️ Failed to get token from Redis: {e}")
    
    # Priority 2: Static environment variable
    if USHA_JWT_TOKEN:
        logger.debug("🔑 Using static USHA_JWT_TOKEN from environment")
        return USHA_JWT_TOKEN
    
    # Priority 3: Cognito refresh (TODO)
    if COGNITO_REFRESH_TOKEN:
        # logger.warning("⚠️ Cognito refresh token available but refresh logic not implemented")
        # TODO: Implement Cognito token refresh
        return None
    
    # logger.warning("⚠️ No USHA token available - set USHA_EMAIL/USHA_PASSWORD for Auth Worker")
    return None


def get_usha_headers() -> Dict[str, str]:
    """
    Get headers for USHA API requests.
    
    Automatically pulls token from Redis or environment.
    
    Returns:
        Headers dict with Authorization if token available
    """
    token = get_usha_token()
    
    headers = {
        'Origin': 'https://agent.ushadvisors.com',
        'Referer': 'https://agent.ushadvisors.com',
        'Content-Type': 'application/json'
    }
    
    if token:
        headers['Authorization'] = f'Bearer {token}'
    
    return headers
