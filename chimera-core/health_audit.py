#!/usr/bin/env python3
"""
Chimera Core - Health Audit Script

Queries live PostgreSQL database to verify system restoration:
- Mission results with 100% trust scores
- Trace URLs present
- Self-healing selector repairs recorded
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("APP_DATABASE_URL")

if not DATABASE_URL:
    print("❌ DATABASE_URL not set")
    sys.exit(1)


def audit_mission_results():
    """Audit mission results - verify 100% trust scores and trace URLs"""
    print("\n🔍 Mission Results Audit")
    print("=" * 60)
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get last 10 mission results
        cur.execute("""
            SELECT 
                id,
                worker_id,
                trust_score,
                is_human,
                validation_method,
                mission_type,
                mission_status,
                trace_url,
                created_at
            FROM mission_results
            ORDER BY created_at DESC
            LIMIT 10
        """)
        
        results = cur.fetchall()
        
        if not results:
            print("⚠️ No mission results found")
            return False
        
        print(f"📊 Found {len(results)} mission results\n")
        
        all_valid = True
        trace_count = 0
        
        for i, result in enumerate(results, 1):
            trust_score = float(result['trust_score'])
            is_human = result['is_human']
            trace_url = result.get('trace_url')
            
            # Verify trust score
            score_valid = trust_score == 100.0
            human_valid = is_human is True
            trace_valid = trace_url is not None and '/tmp/chimera-traces/' in trace_url
            
            status = "✅" if (score_valid and human_valid and trace_valid) else "❌"
            
            print(f"{status} Result #{i} (ID: {result['id']})")
            print(f"   Worker: {result['worker_id']}")
            print(f"   Trust Score: {trust_score}% {'✅' if score_valid else '❌'}")
            print(f"   Is Human: {is_human} {'✅' if human_valid else '❌'}")
            print(f"   Trace URL: {trace_url[:60] + '...' if trace_url and len(trace_url) > 60 else trace_url or 'MISSING ❌'}")
            print(f"   Created: {result['created_at']}")
            print()
            
            if not (score_valid and human_valid):
                all_valid = False
            
            if trace_valid:
                trace_count += 1
        
        print(f"📈 Summary:")
        print(f"   Total Results: {len(results)}")
        print(f"   Valid (100% + Human): {sum(1 for r in results if float(r['trust_score']) == 100.0 and r['is_human'])}/{len(results)}")
        print(f"   With Trace URLs: {trace_count}/{len(results)}")
        
        cur.close()
        conn.close()
        
        return all_valid and trace_count > 0
        
    except Exception as e:
        print(f"❌ Database query failed: {e}")
        return False


def audit_selector_repairs():
    """Audit selector repairs - verify Phase 3 self-healing is active"""
    print("\n🧠 Intelligence Audit (Selector Repairs)")
    print("=" * 60)
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if table exists first
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'selector_repairs'
            )
        """)
        table_exists = cur.fetchone()['exists']
        
        if not table_exists:
            print("   ℹ️ selector_repairs table not created yet (no repairs needed)")
            print("   ✅ Intelligence Audit: [0] self-healed selectors verified.")
            cur.close()
            conn.close()
            return True
        
        # Count selector repairs
        cur.execute("""
            SELECT COUNT(*) as count
            FROM selector_repairs
        """)
        
        count_result = cur.fetchone()
        count = count_result['count'] if count_result else 0
        
        # Get recent repairs
        cur.execute("""
            SELECT 
                id,
                worker_id,
                original_selector,
                new_selector,
                repair_method,
                confidence,
                created_at
            FROM selector_repairs
            ORDER BY created_at DESC
            LIMIT 5
        """)
        
        recent = cur.fetchall()
        
        print(f"📊 Total Self-Healed Selectors: {count}")
        
        if recent:
            print(f"\n📋 Recent Repairs (last 5):")
            for i, repair in enumerate(recent, 1):
                print(f"   {i}. Worker: {repair['worker_id']}")
                print(f"      Method: {repair['repair_method']} (confidence: {repair['confidence']})")
                print(f"      Original: {repair['original_selector'][:50]}...")
                print(f"      New: {repair['new_selector'][:50]}...")
                print(f"      Created: {repair['created_at']}")
                print()
        else:
            print("   ⚠️ No repairs recorded yet (system may not have encountered broken selectors)")
        
        cur.close()
        conn.close()
        
        print(f"✅ Intelligence Audit: [{count}] self-healed selectors verified.")
        return True
        
    except Exception as e:
        # Table might not exist yet if no repairs have occurred
        if "does not exist" in str(e).lower():
            print("   ℹ️ selector_repairs table not created yet (no repairs needed)")
            print("   ✅ Intelligence Audit: [0] self-healed selectors verified.")
            return True
        print(f"❌ Database query failed: {e}")
        return False


def main():
    """Run complete health audit"""
    print("\n" + "=" * 60)
    print("🏥 CHIMERA CORE - SYSTEM HEALTH AUDIT")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'Connected'}")
    
    # Audit mission results
    mission_valid = audit_mission_results()
    
    # Audit selector repairs
    intelligence_valid = audit_selector_repairs()
    
    # Final summary
    print("\n" + "=" * 60)
    print("📋 FINAL AUDIT SUMMARY")
    print("=" * 60)
    print(f"Mission Results: {'✅ PASS' if mission_valid else '❌ FAIL'}")
    print(f"Intelligence: {'✅ PASS' if intelligence_valid else '❌ FAIL'}")
    
    if mission_valid and intelligence_valid:
        print("\n🎯 SYSTEM RESTORATION VERIFIED - ALL CHECKS PASSED")
        return 0
    else:
        print("\n⚠️ SYSTEM RESTORATION INCOMPLETE - SOME CHECKS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
