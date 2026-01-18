"""
Chimera Core - Database Bridge

PostgreSQL persistence layer for mission results and worker performance.
Records 100% Human trust scores and selector repair history.
"""

import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("APP_DATABASE_URL")


def get_db_connection():
    """
    Get PostgreSQL connection.
    
    Returns:
        psycopg2 connection object or None if DATABASE_URL not set
    """
    if not DATABASE_URL:
        logger.warning("⚠️ DATABASE_URL not set - database persistence disabled")
        return None
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        logger.error(f"❌ Failed to connect to PostgreSQL: {e}")
        return None


def ensure_mission_results_table(conn):
    """
    Ensure mission_results table exists.
    
    Creates table if it doesn't exist (idempotent).
    
    Args:
        conn: PostgreSQL connection
    """
    try:
        cur = conn.cursor()
        
        # Create mission_results table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mission_results (
                id SERIAL PRIMARY KEY,
                worker_id VARCHAR(100) NOT NULL,
                trust_score FLOAT NOT NULL,
                is_human BOOLEAN NOT NULL,
                validation_method VARCHAR(50) DEFAULT 'creepjs',
                fingerprint_details JSONB,
                mission_type VARCHAR(100),
                mission_status VARCHAR(50) DEFAULT 'completed',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP
            )
        """)
        
        # Create indexes for faster lookups
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_mission_results_worker_id 
            ON mission_results(worker_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_mission_results_trust_score 
            ON mission_results(trust_score)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_mission_results_is_human 
            ON mission_results(is_human)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_mission_results_created_at 
            ON mission_results(created_at)
        """)
        
        conn.commit()
        cur.close()
        logger.debug("✅ mission_results table verified")
        
    except Exception as e:
        logger.error(f"❌ Failed to create mission_results table: {e}")
        conn.rollback()


def log_mission_result(
    worker_id: str,
    trust_score: float,
    is_human: bool,
    validation_method: str = "creepjs",
    fingerprint_details: Optional[Dict[str, Any]] = None,
    mission_type: Optional[str] = None,
    mission_status: str = "completed",
    error_message: Optional[str] = None
) -> bool:
    """
    Log mission result to PostgreSQL.
    
    Records 100% Human trust scores and validation outcomes.
    
    Args:
        worker_id: Worker identifier (e.g., "worker-0")
        trust_score: CreepJS trust score (0.0-100.0)
        is_human: Whether score indicates human (>= 100.0)
        validation_method: Validation method used (default: "creepjs")
        fingerprint_details: Optional fingerprint details dict
        mission_type: Optional mission type identifier
        mission_status: Mission status (default: "completed")
        error_message: Optional error message if validation failed
    
    Returns:
        True if logged successfully, False otherwise
    """
    if not DATABASE_URL:
        logger.debug("⚠️ DATABASE_URL not set - skipping mission result log")
        return False
    
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        ensure_mission_results_table(conn)
        
        cur = conn.cursor()
        
        # Insert mission result
        cur.execute("""
            INSERT INTO mission_results (
                worker_id,
                trust_score,
                is_human,
                validation_method,
                fingerprint_details,
                mission_type,
                mission_status,
                error_message,
                completed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            worker_id,
            trust_score,
            is_human,
            validation_method,
            psycopg2.extras.Json(fingerprint_details) if fingerprint_details else None,
            mission_type,
            mission_status,
            error_message
        ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        if is_human and trust_score >= 100.0:
            logger.info(f"✅ Mission result logged: {worker_id} - {trust_score}% HUMAN")
        else:
            logger.warning(f"⚠️ Mission result logged: {worker_id} - {trust_score}% (NOT HUMAN)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to log mission result: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


def test_db_connection() -> bool:
    """
    Test PostgreSQL connection on boot.
    
    Returns:
        True if connection successful, False otherwise
    """
    if not DATABASE_URL:
        logger.warning("⚠️ DATABASE_URL not set - PostgreSQL persistence disabled")
        return False
    
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        cur.close()
        conn.close()
        
        logger.info(f"✅ Connected to PostgreSQL Persistence Layer")
        logger.debug(f"   PostgreSQL version: {version.split(',')[0]}")
        return True
        
    except Exception as e:
        logger.error(f"❌ PostgreSQL connection test failed: {e}")
        if conn:
            conn.close()
        return False
