"""
Identity Resolution Module
Resolves raw LinkedIn/Facebook data into verifiable US identity
"""
import re
from typing import Dict, Any, Optional, Tuple


def clean_name(name: str) -> str:
    """Clean and normalize a name string"""
    if not name:
        return ""
    
    # Remove common suffixes/prefixes that interfere with searches
    suffixes = [
        r',?\s*(PhD|Ph\.D|MD|M\.D|MBA|CPA|Esq|Jr|Sr|III|II|IV)\.?$',
        r'\s*\([^)]+\)$',  # Remove parenthetical content like (He/Him)
        r'\s*[\|\-]\s*.+$',  # Remove "| Company" or "- Title"
    ]
    
    cleaned = name.strip()
    for pattern in suffixes:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Remove extra whitespace
    cleaned = ' '.join(cleaned.split())
    
    return cleaned.strip()


def parse_name(name: str) -> Tuple[str, str]:
    """
    Parse full name into first and last name
    
    Handles:
    - "John Smith" -> ("John", "Smith")
    - "John David Smith" -> ("John", "David Smith")
    - "John" -> ("John", "")
    - "" -> ("", "")
    """
    if not name:
        return ("", "")
    
    parts = name.strip().split()
    
    if len(parts) == 0:
        return ("", "")
    elif len(parts) == 1:
        return (parts[0], "")
    elif len(parts) == 2:
        return (parts[0], parts[1])
    else:
        # Multiple parts - first word is first name, rest is last name
        # This handles "Mary Jane Watson" -> ("Mary", "Jane Watson")
        return (parts[0], ' '.join(parts[1:]))

def resolve_identity(lead_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve raw lead data into structured identity
    
    Args:
        lead_data: Raw lead from Redis queue
        
    Returns:
        Structured identity with firstName, lastName, city, state, zipcode
    """
    # Parse name - handle various formats (name/fullName first, then firstName+lastName)
    name = (
        lead_data.get('name', '') or lead_data.get('fullName', '')
        or lead_data.get('Name', '') or lead_data.get('full_name', '')
    )
    if not name:
        name = f"{lead_data.get('firstName') or lead_data.get('first_name') or ''} {lead_data.get('lastName') or lead_data.get('last_name') or ''}".strip()
    name = clean_name(name)
    
    # Split name intelligently
    firstName, lastName = parse_name(name)
    
    # Parse location
    location = lead_data.get('location', '')
    city, state, zipcode = parse_location(location)
    
    # Extract LinkedIn URL
    linkedinUrl = lead_data.get('linkedinUrl', '')
    
    return {
        'firstName': firstName,
        'lastName': lastName,
        'fullName': name,
        'city': city,
        'state': state,
        'zipcode': zipcode,
        'company': lead_data.get('company', ''),
        'title': lead_data.get('title', ''),
        'linkedinUrl': linkedinUrl,
        'platform': lead_data.get('platform', 'linkedin'),
        'email': lead_data.get('email'),  # May be present from source
    }

def parse_location(location: str) -> tuple:
    """
    Parse location string into city, state, zipcode
    
    Examples:
        "Naples, Florida, United States" -> ("Naples", "FL", "")
        "Naples, FL 34101" -> ("Naples", "FL", "34101")
        "Miami, FL" -> ("Miami", "FL", "")
    """
    if not location:
        return ("", "", "")
    
    # Remove "United States" suffix
    location = re.sub(r',\s*United\s+States$', '', location, flags=re.IGNORECASE)
    
    # Try to extract zipcode (5 digits)
    zipcode_match = re.search(r'\b(\d{5})\b', location)
    zipcode = zipcode_match.group(1) if zipcode_match else ""
    
    # Remove zipcode from location string
    location_clean = re.sub(r'\b\d{5}\b', '', location).strip()
    
    # Split by comma
    parts = [p.strip() for p in location_clean.split(',')]
    
    if len(parts) >= 2:
        city = parts[0]
        state_raw = parts[1]
        # Convert full state name to abbreviation if needed
        state = normalize_state(state_raw)
        return (city, state, zipcode)
    elif len(parts) == 1:
        # Try to extract state from single part
        state_match = re.search(r'\b([A-Z]{2})\b', parts[0])
        if state_match:
            state = state_match.group(1)
            city = parts[0].replace(state, '').strip().rstrip(',').strip()
            return (city, state, zipcode)
        return (parts[0], "", zipcode)
    
    return ("", "", zipcode)

def normalize_state(state: str) -> str:
    """Convert state name to abbreviation"""
    state_abbreviations = {
        'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR',
        'california': 'CA', 'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE',
        'florida': 'FL', 'georgia': 'GA', 'hawaii': 'HI', 'idaho': 'ID',
        'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA', 'kansas': 'KS',
        'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
        'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS',
        'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV',
        'new hampshire': 'NH', 'new jersey': 'NJ', 'new mexico': 'NM', 'new york': 'NY',
        'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK',
        'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
        'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT',
        'vermont': 'VT', 'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV',
        'wisconsin': 'WI', 'wyoming': 'WY', 'district of columbia': 'DC'
    }
    
    state_lower = state.lower().strip()
    
    # If already abbreviation (2 uppercase letters)
    if re.match(r'^[A-Z]{2}$', state):
        return state.upper()
    
    # Look up full name
    return state_abbreviations.get(state_lower, state.upper()[:2] if len(state) >= 2 else state)
