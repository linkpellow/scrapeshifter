"""
Chimera Core - Database Bridge

PostgreSQL persistence layer for mission results and worker performance.
Records 100% Human trust scores and selector repair history.

Uses connection pooling for high-concurrency worker swarm.
"""

import os
import logging
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from typing import Dict, Any, Optional
from datetime import datetime
import threading

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("APP_DATABASE_URL")

# Connection pool for high-concurrency worker swarm
_connection_pool: Optional[pool.ThreadedConnectionPool] = None
_pool_lock = threading.Lock()


def get_connection_pool():
    """
    Get or create PostgreSQL connection pool.
    
    Returns:
        ThreadedConnectionPool or None if DATABASE_URL not set
    """
    global _connection_pool
    
    if not DATABASE_URL:
        return None
    
    if _connection_pool is None:
        with _pool_lock:
            if _connection_pool is None:
                try:
                    # Connection pool: min 2, max 10 connections
                    # Supports high-concurrency worker swarm
                    _connection_pool = pool.ThreadedConnectionPool(
                        minconn=2,
                        maxconn=10,
                        dsn=DATABASE_URL
                    )
                    logger.debug("✅ PostgreSQL connection pool created (2-10 connections)")
                except Exception as e:
                    logger.error(f"❌ Failed to create connection pool: {e}")
                    return None
    
    return _connection_pool


def get_db_connection():
    """
    Get PostgreSQL connection from pool.
    
    Returns:
        psycopg2 connection object or None if pool unavailable
    """
    pool = get_connection_pool()
    if not pool:
        return None
    
    try:
        conn = pool.getconn()
        return conn
    except Exception as e:
        logger.error(f"❌ Failed to get connection from pool: {e}")
        return None


def return_db_connection(conn):
    """
    Return connection to pool.
    
    Args:
        conn: Connection to return
    """
    pool = get_connection_pool()
    if pool and conn:
        try:
            pool.putconn(conn)
        except Exception as e:
            logger.error(f"❌ Failed to return connection to pool: {e}")
            try:
                conn.close()
            except:
                pass


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
                trace_url TEXT,
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


def log_selector_repair(
    worker_id: str,
    original_selector: str,
    new_selector: str,
    method: str = "isomorphic",
    confidence: float = 0.85,
    intent: Optional[str] = None
) -> bool:
    """
    Log selector repair to PostgreSQL.
    
    Records self-healing selector repairs for future reference.
    
    Args:
        worker_id: Worker identifier
        original_selector: The selector that failed
        new_selector: The repaired selector
        method: Repair method (e.g., "isomorphic", "id-fallback")
        confidence: Confidence score (0.0-1.0)
        intent: Intent description (e.g., "click login button")
    
    Returns:
        True if logged successfully, False otherwise
    """
    if not DATABASE_URL:
        logger.debug("⚠️ DATABASE_URL not set - skipping selector repair log")
        return False
    
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        ensure_selector_repairs_table(conn)
        
        cur = conn.cursor()
        
        # Insert selector repair
        cur.execute("""
            INSERT INTO selector_repairs (
                worker_id,
                original_selector,
                new_selector,
                repair_method,
                confidence,
                intent,
                created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (
            worker_id,
            original_selector,
            new_selector,
            method,
            confidence,
            intent
        ))
        
        conn.commit()
        cur.close()
        return_db_connection(conn)
        
        logger.info(f"✅ Selector self-healed and updated in Postgres")
        logger.debug(f"   Original: {original_selector}")
        logger.debug(f"   New: {new_selector} (method: {method}, confidence: {confidence})")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to log selector repair: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
            return_db_connection(conn)
        return False


def ensure_selector_repairs_table(conn):
    """
    Ensure selector_repairs table exists.
    
    Args:
        conn: PostgreSQL connection
    """
    try:
        cur = conn.cursor()
        
        # Create selector_repairs table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS selector_repairs (
                id SERIAL PRIMARY KEY,
                worker_id VARCHAR(100) NOT NULL,
                original_selector TEXT NOT NULL,
                new_selector TEXT NOT NULL,
                repair_method VARCHAR(50) DEFAULT 'isomorphic',
                confidence FLOAT DEFAULT 0.85,
                intent VARCHAR(255),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Create indexes
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_selector_repairs_worker_id 
            ON selector_repairs(worker_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_selector_repairs_created_at 
            ON selector_repairs(created_at)
        """)
        
        conn.commit()
        cur.close()
        logger.debug("✅ selector_repairs table verified")
        
    except Exception as e:
        logger.error(f"❌ Failed to create selector_repairs table: {e}")
        conn.rollback()


def record_stealth_check(
    worker_id: str,
    score: float,
    fingerprint: Optional[Dict[str, Any]] = None,
    trace_url: Optional[str] = None
) -> bool:
    """
    Record stealth check result (100% human gate).
    
    Convenience function for logging CreepJS validation results.
    
    Args:
        worker_id: Worker identifier (e.g., "worker-0")
        score: Trust score (0.0-100.0)
        fingerprint: Optional fingerprint details dict
        trace_url: Optional trace file URL
    
    Returns:
        True if logged successfully, False otherwise
    """
    return log_mission_result(
        worker_id=worker_id,
        trust_score=score,
        is_human=(score >= 100.0),
        validation_method="creepjs",
        fingerprint_details=fingerprint,
        mission_type="stealth_validation",
        mission_status="completed" if score >= 100.0 else "failed",
        trace_url=trace_url
    )


def log_mission_result(
    worker_id: str,
    trust_score: float,
    is_human: bool,
    validation_method: str = "creepjs",
    fingerprint_details: Optional[Dict[str, Any]] = None,
    mission_type: Optional[str] = None,
    mission_status: str = "completed",
    error_message: Optional[str] = None,
    trace_url: Optional[str] = None
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
                trace_url,
                completed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            worker_id,
            trust_score,
            is_human,
            validation_method,
            psycopg2.extras.Json(fingerprint_details) if fingerprint_details else None,
            mission_type,
            mission_status,
            error_message,
            trace_url
        ))
        
        conn.commit()
        cur.close()
        return_db_connection(conn)  # Return to pool instead of closing
        
        if is_human and trust_score >= 100.0:
            logger.info(f"✅ Mission result logged: {worker_id} - {trust_score}% HUMAN")
        else:
            logger.warning(f"⚠️ Mission result logged: {worker_id} - {trust_score}% (NOT HUMAN)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to log mission result: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
            return_db_connection(conn)  # Return to pool even on error
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
        return_db_connection(conn)  # Return to pool instead of closing
        
        logger.info(f"✅ Connected to PostgreSQL Persistence Layer")
        logger.debug(f"   PostgreSQL version: {version.split(',')[0]}")
        logger.debug(f"   Connection pool: 2-10 connections (high-concurrency ready)")
        return True
        
    except Exception as e:
        logger.error(f"❌ PostgreSQL connection test failed: {e}")
        if conn:
            return_db_connection(conn)  # Return to pool even on error
        return False
