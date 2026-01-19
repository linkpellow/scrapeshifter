"""
Skip-Tracing Module
Finds phone numbers and emails via skip-tracing APIs

Strategy: "Free First, Pay Later"
1. Try free native spider (TruePeopleSearch) - saves $0.15/lead
2. Fallback to paid RapidAPI if free spider fails

This is the "Full Potential" approach that maximizes cost savings.
"""
import os
import requests
import asyncio
from typing import Dict, Any, Optional
from loguru import logger

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

def skip_trace(identity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Find contact information via skip-tracing.
    
    Strategy: "Free First, Pay Later"
    1. Try free native spider (TruePeopleSearch) - saves $0.15/lead
    2. Fallback to paid RapidAPI if free spider fails
    
    Args:
        identity: Resolved identity from identity_resolution module
        
    Returns:
        Dictionary with phone and email (if found)
    """
    # Step 1: Try FREE native spider first
    if identity.get('firstName') and identity.get('lastName') and identity.get('city') and identity.get('state'):
        try:
            logger.info("🎯 [Free] Attempting native phone lookup...")
            result = try_free_phone_lookup(identity)
            if result and result.get('phone'):
                logger.success("🎉 Native Enrichment Success! (Saved $0.15)")
                return result
            else:
                logger.info("ℹ️ Native lookup failed, falling back to RapidAPI...")
        except Exception as e:
            logger.warning(f"⚠️ Native enrichment failed: {e}")
            logger.info("   Falling back to RapidAPI...")
    
    # Step 2: Fallback to paid RapidAPI
    api_key = RAPIDAPI_KEY

    if not api_key:
        logger.warning("⚠️ RAPIDAPI_KEY not set, skipping paid skip-trace")
        return {}
    
    logger.info("💰 [Paid] Using RapidAPI skip-tracing...")
    
    # Try by email first (if available)
    if identity.get('email'):
        result = skip_trace_by_email(identity['email'], api_key)
        if result.get('phone'):
            return {
                'phone': result['phone'],
                'email': identity['email']
            }
    
    # Try by name and address
    if identity.get('firstName') and identity.get('lastName') and identity.get('city'):
        result = skip_trace_by_name_address(identity, api_key)
        if result:
            return result
    
    return {}


def try_free_phone_lookup(identity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Try free phone lookup via TruePeopleSearch spider.
    
    Uses 2026 cognitive capabilities:
    - LLM parsing (no fragile selectors)
    - Smart query mutations (handles nicknames)
    - Vision verification (detects soft blocks)
    
    Args:
        identity: Identity dict with firstName, lastName, city, state
        
    Returns:
        Dict with phone (string) if found, None otherwise
        Note: Converts spider's "phones" list to single "phone" string for compatibility
    """
    try:
        from app.scraping.spiders.truepeoplesearch_spider import TruePeopleSearchSpider
        
        first_name = identity.get('firstName', '')
        last_name = identity.get('lastName', '')
        city = identity.get('city', '')
        state = identity.get('state', '')
        
        if not all([first_name, last_name, city, state]):
            logger.debug("Missing required fields for free lookup")
            return None
        
        # Run async spider in sync context
        spider = TruePeopleSearchSpider()
        result = asyncio.run(spider.run(
            first_name=first_name,
            last_name=last_name,
            city=city,
            state=state
        ))
        
        if result:
            # Convert spider format to enrichment pipeline format
            # Spider returns: {"phones": ["+1234"], "age": 45, "address": "..."}
            # Pipeline expects: {"phone": "+1234", "email": "..."}
            phones = result.get("phones", [])
            if phones:
                # Take first phone number
                phone = phones[0] if isinstance(phones, list) else phones
                return {
                    "phone": phone,
                    # Include additional data if available
                    "age": result.get("age"),
                    "address": result.get("address"),
                }
        
        return None
        
    except ImportError:
        logger.debug("TruePeopleSearch spider not available")
        return None
    except Exception as e:
        logger.debug(f"Free phone lookup error: {e}")
        return None

def skip_trace_by_email(email: str, api_key: str) -> Dict[str, Any]:
    """Skip-trace by email address"""
    try:
        url = "https://skip-tracing-working-api.p.rapidapi.com/search/byemail"
        headers = {
            "x-rapidapi-key": api_key,
            "x-rapidapi-host": "skip-tracing-working-api.p.rapidapi.com"
        }
        params = {
            "email": email,
            "phone": "1"  # Request phone number
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract phone from response (structure may vary)
        phone = None
        if isinstance(data, dict):
            phone = data.get('phone') or data.get('phoneNumber') or data.get('phone_number')
            if isinstance(phone, list) and phone:
                phone = phone[0]
        
        return {'phone': phone} if phone else {}
        
    except Exception as e:
        logger.error(f"❌ Skip-trace by email failed: {e}")
        return {}

def skip_trace_by_name_address(identity: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    """Skip-trace by name and address"""
    try:
        # Build address string
        address_parts = []
        if identity.get('city'):
            address_parts.append(identity['city'])
        if identity.get('state'):
            address_parts.append(identity['state'])
        if identity.get('zipcode'):
            address_parts.append(identity['zipcode'])
        
        address = ", ".join(address_parts)
        name = f"{identity.get('firstName', '')} {identity.get('lastName', '')}".strip()
        
        if not name or not address:
            return {}
        
        # Try primary API
        url = "https://skip-tracing-working-api.p.rapidapi.com/search/bynameaddress"
        headers = {
            "x-rapidapi-key": api_key,
            "x-rapidapi-host": "skip-tracing-working-api.p.rapidapi.com"
        }
        params = {
            "name": name,
            "citystatezip": address
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            phone = extract_phone_from_response(data)
            email = extract_email_from_response(data)
            
            result = {}
            if phone:
                result['phone'] = phone
            if email:
                result['email'] = email
            
            return result
            
        except requests.RequestException:
            # Fallback to alternative API
            return skip_trace_alternative_api(name, address, api_key)
            
    except Exception as e:
        logger.error(f"❌ Skip-trace by name/address failed: {e}")
        return {}

def skip_trace_alternative_api(name: str, address: str, api_key: str) -> Dict[str, Any]:
    """Fallback skip-trace API"""
    try:
        url = "https://skip-tracing-api.p.rapidapi.com/by-name-and-address"
        headers = {
            "x-rapidapi-key": api_key,
            "x-rapidapi-host": "skip-tracing-api.p.rapidapi.com"
        }
        params = {
            "name": name,
            "address": address
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        phone = extract_phone_from_response(data)
        email = extract_email_from_response(data)
        
        result = {}
        if phone:
            result['phone'] = phone
        if email:
            result['email'] = email
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Alternative skip-trace API failed: {e}")
        return {}

def extract_phone_from_response(data: Any) -> Optional[str]:
    """Extract phone number from API response"""
    if isinstance(data, dict):
        # Try common field names
        phone = (data.get('phone') or data.get('phoneNumber') or 
                data.get('phone_number') or data.get('phoneNumber') or
                data.get('mobile') or data.get('cell'))
        
        if phone:
            # Normalize phone format
            if isinstance(phone, str):
                # Remove non-digits
                digits = ''.join(filter(str.isdigit, phone))
                if len(digits) == 10:
                    return f"+1{digits}"
                elif len(digits) == 11 and digits[0] == '1':
                    return f"+{digits}"
                elif phone.startswith('+'):
                    return phone
                else:
                    return f"+1{digits}" if len(digits) >= 10 else None
        
        # Check nested structures
        if 'contact' in data:
            return extract_phone_from_response(data['contact'])
        if 'result' in data:
            return extract_phone_from_response(data['result'])
    
    elif isinstance(data, list) and data:
        return extract_phone_from_response(data[0])
    
    return None

def extract_email_from_response(data: Any) -> Optional[str]:
    """Extract email from API response"""
    if isinstance(data, dict):
        email = (data.get('email') or data.get('emailAddress') or 
                data.get('email_address'))
        
        if email and '@' in str(email):
            return str(email)
        
        # Check nested structures
        if 'contact' in data:
            return extract_email_from_response(data['contact'])
        if 'result' in data:
            return extract_email_from_response(data['result'])
    
    elif isinstance(data, list) and data:
        return extract_email_from_response(data[0])
    
    return None
