"""
Database Module
Saves enriched leads to PostgreSQL with deduplication.
Golden Record: merge with confidence_age, confidence_income, source_metadata.
Flags for Trauma Center (VLM) when e.g. Junior + $150k income.
"""
import json
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("APP_DATABASE_URL")


def _compute_confidence_income(income: Any, title: str) -> float:
    """0.0–1.0. Low if e.g. Junior + high income → flag for Trauma Center."""
    if not income or not isinstance(title, str):
        return 1.0
    t = title.lower()
    try:
        val = int(str(income).replace("$", "").replace(",", "").replace("k", "000").replace("K", "000"))
    except Exception:
        return 1.0
    if ("junior" in t or "associate" in t or "intern" in t) and val > 100_000:
        return 0.3
    return 1.0


def _compute_confidence_age(age: Any, title: str) -> float:
    """0.0–1.0. Flag when age > 59 but title doesn’t suggest retiree."""
    if age is None:
        return 1.0
    try:
        a = int(age)
    except Exception:
        return 1.0
    if a > 59 and title and "retir" not in (title or "").lower():
        return 0.6
    return 1.0

def save_to_database(enriched_lead: Dict[str, Any]) -> bool:
    """
    Save enriched lead to PostgreSQL with deduplication
    
    Args:
        enriched_lead: Complete enriched lead data
        
    Returns:
        True if saved successfully, False otherwise
    """
    if not DATABASE_URL:
        logger.error("❌ DATABASE_URL not set, cannot save to database")
        return False
    
    try:
        # psycopg2.connect accepts postgresql:// URLs directly
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Ensure table exists
        ensure_table_exists(cur)
        
        # Extract values
        linkedin_url = enriched_lead.get('linkedinUrl') or enriched_lead.get('linkedin_url')
        name = enriched_lead.get('name') or f"{enriched_lead.get('firstName', '')} {enriched_lead.get('lastName', '')}".strip()
        phone = enriched_lead.get('phone')
        email = enriched_lead.get('email')
        city = enriched_lead.get('city')
        state = enriched_lead.get('state')
        zipcode = enriched_lead.get('zipcode')
        age = enriched_lead.get('age') or enriched_lead.get('chimera_age')
        income = enriched_lead.get('income') or enriched_lead.get('median_income') or enriched_lead.get('chimera_income')
        dnc_status = enriched_lead.get('dnc_status') or enriched_lead.get('status', 'UNKNOWN')
        can_contact = enriched_lead.get('can_contact', False)
        title = enriched_lead.get('title') or ''

        # Golden Record: confidence and source_metadata
        conf_age = _compute_confidence_age(age, title)
        conf_inc = _compute_confidence_income(income, title)
        needs_vlm = conf_age < 0.7 or conf_inc < 0.5
        sources = {}
        if age is not None:
            sources['age'] = 'chimera' if enriched_lead.get('chimera_age') is not None else 'census'
        if income is not None:
            sources['income'] = 'chimera' if enriched_lead.get('chimera_income') is not None else 'census'
        source_metadata = json.dumps({'sources': sources, 'needs_vlm_check': needs_vlm, 'title': title})
        
        # Insert or update with deduplication and Golden Record fields
        cur.execute("""
            INSERT INTO leads (
                linkedin_url, name, phone, email,
                city, state, zipcode, age, income,
                dnc_status, can_contact, confidence_age, confidence_income, source_metadata,
                enriched_at, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW(), COALESCE((SELECT created_at FROM leads WHERE linkedin_url = %s), NOW()))
            ON CONFLICT (linkedin_url) 
            DO UPDATE SET
                phone = COALESCE(EXCLUDED.phone, leads.phone),
                email = COALESCE(EXCLUDED.email, leads.email),
                age = COALESCE(EXCLUDED.age, leads.age),
                income = COALESCE(EXCLUDED.income, leads.income),
                dnc_status = COALESCE(EXCLUDED.dnc_status, leads.dnc_status),
                can_contact = COALESCE(EXCLUDED.can_contact, leads.can_contact),
                city = COALESCE(EXCLUDED.city, leads.city),
                state = COALESCE(EXCLUDED.state, leads.state),
                zipcode = COALESCE(EXCLUDED.zipcode, leads.zipcode),
                confidence_age = COALESCE(EXCLUDED.confidence_age, leads.confidence_age),
                confidence_income = COALESCE(EXCLUDED.confidence_income, leads.confidence_income),
                source_metadata = COALESCE(EXCLUDED.source_metadata, leads.source_metadata),
                enriched_at = NOW()
            RETURNING id
        """, (
            linkedin_url, name, phone, email,
            city, state, zipcode, age, income,
            dnc_status, can_contact, conf_age, conf_inc, source_metadata, linkedin_url
        ))
        
        result = cur.fetchone()
        lead_id = result[0] if result else None
        
        conn.commit()
        cur.close()
        conn.close()
        
        logger.info(f"✅ Saved lead to database (ID: {lead_id}, LinkedIn: {linkedin_url})")
        return True

    except psycopg2.IntegrityError as e:
        logger.warning(f"⚠️  Database integrity error (likely duplicate): {e}")
        return True  # Consider duplicate as success
    except Exception as e:
        logger.exception(f"❌ Database save error: {e}")
        return False

def ensure_table_exists(cur):
    """Ensure leads table exists with Golden Record columns (confidence_*, source_metadata)."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id SERIAL PRIMARY KEY,
            linkedin_url VARCHAR(255) UNIQUE NOT NULL,
            name VARCHAR(255),
            phone VARCHAR(20),
            email VARCHAR(255),
            city VARCHAR(100),
            state VARCHAR(50),
            zipcode VARCHAR(10),
            age INTEGER,
            income VARCHAR(50),
            dnc_status VARCHAR(20),
            can_contact BOOLEAN DEFAULT false,
            confidence_age NUMERIC(3,2),
            confidence_income NUMERIC(3,2),
            source_metadata JSONB,
            enriched_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    for col, typ in [
        ("confidence_age", "NUMERIC(3,2)"),
        ("confidence_income", "NUMERIC(3,2)"),
        ("source_metadata", "JSONB"),
    ]:
        cur.execute(f"ALTER TABLE leads ADD COLUMN IF NOT EXISTS {col} {typ}")
