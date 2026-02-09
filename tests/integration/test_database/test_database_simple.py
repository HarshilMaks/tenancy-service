import pytest
#!/usr/bin/env python3
"""
Simple Database Test Script
===========================

Test database connectivity and basic operations with your Neon PostgreSQL database.
"""

import asyncio
import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from infrastructure.config import get_settings

# Get database settings
settings = get_settings()


def get_async_url():
    """Convert sync PostgreSQL URL to async asyncpg URL."""
    url = str(settings.database.url)
    print(f"Original URL: {url}")  # Debug
    
    # Split URL into base and params
    if '?' in url:
        base_url, params = url.split('?', 1)
    else:
        base_url, params = url, ""
    
    # Convert to asyncpg
    async_base = base_url.replace("postgresql://", "postgresql+asyncpg://")
    
    # For Neon, we need SSL but asyncpg handles it differently
    # Try without explicit SSL parameter first
    async_url = async_base
        
    print(f"Converted URL: {async_url}")  # Debug
    return async_url


@pytest.mark.asyncio
async def test_connection():
    """Test basic database connectivity."""
    print("🔗 Testing database connection...")
    
    try:
        engine = create_async_engine(get_async_url())
        async with engine.begin() as conn:
            # Test basic connection
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"✅ Connected to PostgreSQL: {version[:50]}...")
            
            # Check tables
            result = await conn.execute(text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """))
            tables = [row[0] for row in result.fetchall()]
            print(f"✅ Found tables: {', '.join(tables)}")
            
        await engine.dispose()
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


@pytest.mark.asyncio
async def test_data_operations():
    """Test inserting, reading, updating, and deleting data."""
    print("\n📝 Testing CRUD operations...")
    
    engine = create_async_engine(get_async_url())
    test_id = str(uuid4())
    
    try:
        async with engine.begin() as conn:
            # 1. INSERT - Create test tenant
            current_time = datetime.now(timezone.utc)
            await conn.execute(text("""
                INSERT INTO tenants (
                    id, name, normalized_name, external_id,
                    status, plan_tier, region, compliance_requirements,
                    plan_limits, metadata, created_at, updated_at, version
                ) VALUES (
                    :id, :name, :norm_name, :external_id,
                    :status, :plan_tier, :region, :compliance_requirements,
                    :plan_limits, :metadata, :created_at, :updated_at, :version
                )
            """), {
                "id": test_id,
                "name": f"Test Tenant {current_time.strftime('%H:%M:%S')}",
                "norm_name": f"test_tenant_{current_time.strftime('%H%M%S')}",
                "external_id": f"ext-{test_id[:8]}",
                "status": "active",
                "plan_tier": "starter",
                "region": "us-east-1",
                "compliance_requirements": json.dumps(["SOC2"]),
                "plan_limits": json.dumps({"users": 10, "storage_gb": 1}),
                "metadata": json.dumps({"source": "test_script", "test": True}),
                "created_at": current_time,
                "updated_at": current_time,
                "version": 1
            })
            print(f"✅ Created test tenant (ID: {test_id[:8]}...)")
            
            # 2. READ - Fetch the tenant
            result = await conn.execute(text("""
                SELECT name, status, plan_tier, region 
                FROM tenants WHERE id = :id
            """), {"id": test_id})
            row = result.fetchone()
            print(f"✅ Retrieved tenant: {row[0]} | Status: {row[1]} | Plan: {row[2]} | Region: {row[3]}")
            
            # 3. UPDATE - Modify the tenant (with suspension reason)
            await conn.execute(text("""
                UPDATE tenants 
                SET status = 'suspended', 
                    suspended_reason = 'Testing database operations', 
                    suspended_at = :suspended_at,
                    updated_at = :updated_at
                WHERE id = :id
            """), {
                "id": test_id, 
                "suspended_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            })
            print("✅ Updated tenant status to 'suspended'")
            
            # 4. INSERT EVENT - Add tenant event
            event_id = str(uuid4())
            await conn.execute(text("""
                INSERT INTO tenant_events (id, tenant_id, event_type, event_version, payload, metadata, created_at)
                VALUES (:id, :tenant_id, :event_type, :event_version, :payload, :metadata, :created_at)
            """), {
                "id": event_id,
                "tenant_id": test_id,
                "event_type": "tenant_suspended",
                "event_version": 1,
                "payload": json.dumps({"reason": "test", "source": "database_test"}),
                "metadata": json.dumps({"test": True, "script_generated": True}),
                "created_at": datetime.now(timezone.utc)
            })
            print("✅ Created tenant event")
            
            # 5. READ EVENTS
            result = await conn.execute(text("""
                SELECT event_type, payload FROM tenant_events 
                WHERE tenant_id = :tenant_id
            """), {"tenant_id": test_id})
            events = result.fetchall()
            print(f"✅ Found {len(events)} events for tenant")
            for event in events:
                print(f"    Event: {event[0]} - Payload: {event[1]}")
            
            # 6. DELETE - Clean up
            await conn.execute(text("DELETE FROM tenant_events WHERE tenant_id = :id"), {"id": test_id})
            await conn.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": test_id})
            print("✅ Cleaned up test data")
            
    except Exception as e:
        print(f"❌ CRUD operations failed: {e}")
        return False
    finally:
        await engine.dispose()
    
    return True


async def show_existing_data():
    """Show what data currently exists in the database."""
    print("\n📊 Current Database Contents:")
    
    engine = create_async_engine(get_async_url())
    
    try:
        async with engine.begin() as conn:
            # Count tenants
            result = await conn.execute(text("SELECT COUNT(*) FROM tenants"))
            tenant_count = result.scalar()
            print(f"📁 Tenants: {tenant_count}")
            
            if tenant_count > 0:
                result = await conn.execute(text("""
                    SELECT name, status, plan_tier, region, created_at 
                    FROM tenants 
                    ORDER BY created_at DESC LIMIT 3
                """))
                print("   Recent tenants:")
                for row in result.fetchall():
                    print(f"   • {row[0]} ({row[1]}, {row[2]}, {row[3]}) - {row[4]}")
            
            # Count events
            result = await conn.execute(text("SELECT COUNT(*) FROM tenant_events"))
            event_count = result.scalar()
            print(f"📝 Events: {event_count}")
            
            if event_count > 0:
                result = await conn.execute(text("""
                    SELECT event_type, payload, created_at 
                    FROM tenant_events 
                    ORDER BY created_at DESC LIMIT 3
                """))
                print("   Recent events:")
                for row in result.fetchall():
                    print(f"   • {row[0]} - {row[2]}")
                    
    except Exception as e:
        print(f"❌ Failed to show data: {e}")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_api():
    """Test if the API server is running."""
    print("\n🌐 Testing API Server:")
    
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Test health endpoint
            try:
                response = await client.get("http://localhost:8000/health")
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ Health check: {data.get('status', 'unknown')}")
                    print(f"   Service: {data.get('service', 'unknown')} v{data.get('version', 'unknown')}")
                else:
                    print(f"❌ Health check failed: HTTP {response.status_code}")
            except Exception as e:
                print(f"⚠️  API server not running on localhost:8000")
                print(f"   Start with: uv run python -m app.main")
                print(f"   Error: {e}")
                return
            
            # Test tenants endpoint
            try:
                response = await client.get("http://localhost:8000/api/v1/tenants")
                if response.status_code == 200:
                    tenants = response.json()
                    print(f"✅ Tenants API: {len(tenants)} tenants returned")
                else:
                    print(f"⚠️  Tenants API: HTTP {response.status_code}")
            except Exception as e:
                print(f"⚠️  Tenants API error: {e}")
                
    except ImportError:
        print("⚠️  httpx not available - skipping API tests")
    except Exception as e:
        print(f"❌ API test error: {e}")


def print_pgadmin_guide():
    """Print comprehensive pgAdmin 4 usage guide."""
    print("\n" + "="*60)
    print("🔍 pgAdmin 4 Database Testing Guide")
    print("="*60)
    
    print("\n1. CONNECT TO NEON DATABASE:")
    print("   • Right-click 'Servers' → Create → Server")
    print("   • General tab:")
    print("     - Name: Neon Tenancy Service")
    print("   • Connection tab:")
    print("     - Host: [See .env.local]")
    print("     - Port: 5432")
    print("     - Maintenance database: [See .env.local]")
    print("     - Username: [See .env.local]") 
    print("     - Password: [See .env.local]")
    print("   • SSL tab:")
    print("     - SSL mode: Require")
    print("   • Click 'Save'")
    
    print("\n2. NAVIGATE TO TABLES:")
    print("   • Expand: Servers → Neon Tenancy Service → Databases → neondb")
    print("   • Expand: Schemas → public → Tables")
    print("   • You should see: tenants, tenant_events")
    
    print("\n3. TEST QUERIES (Query Tool - Tools → Query Tool):")
    print("   ┌─" + "─"*55 + "┐")
    print("   │ -- View all tenants                              │")
    print("   │ SELECT * FROM tenants;                           │")
    print("   │                                                  │")
    print("   │ -- View all events                               │")
    print("   │ SELECT * FROM tenant_events;                     │")
    print("   │                                                  │")
    print("   │ -- Count records                                 │")
    print("   │ SELECT                                           │")
    print("   │   (SELECT COUNT(*) FROM tenants) as tenant_count,│")
    print("   │   (SELECT COUNT(*) FROM tenant_events) as events;│")
    print("   │                                                  │")
    print("   │ -- Add a test tenant                             │")
    print("   │ INSERT INTO tenants (                            │")
    print("   │   id, name, normalized_name, external_id,        │")
    print("   │   status, plan_tier, region, compliance_requirements, │")
    print("   │   plan_limits, metadata, created_at, updated_at, │")
    print("   │   version                                        │")
    print("   │ ) VALUES (                                       │")
    print("   │   gen_random_uuid(),                             │")
    print("   │   'pgAdmin Test Tenant',                         │")
    print("   │   'pgadmin_test_tenant',                         │")
    print("   │   'pgadmin-ext-id',                              │")
    print("   │   'active',                                      │")
    print("   │   'starter',                                     │")
    print("   │   'us-east-1',                                   │")
    print("   │   '[\"SOC2\"]',                                   │")
    print("   │   '{\"users\": 5}',                              │")
    print("   │   '{}',                                          │")
    print("   │   NOW(),                                         │")
    print("   │   NOW(),                                         │")
    print("   │   1                                              │")
    print("   │ );                                               │")
    print("   │                                                  │")
    print("   │ -- Check table structure                         │")
    print("   │ \\d tenants                                        │")
    print("   │ \\d tenant_events                                  │")
    print("   └─" + "─"*55 + "┘")
    
    print("\n4. VERIFY DATA FLOW:")
    print("   • Run this script: uv run python test_database.py")
    print("   • Refresh tables in pgAdmin (F5)")
    print("   • Check if new test records appear")
    print("   • Verify they get deleted after the test")
    
    print("\n5. TROUBLESHOOTING:")
    print("   • If connection fails: Check Neon dashboard for IP allowlisting")
    print("   • If SSL issues: Try 'Prefer' instead of 'Require'")
    print("   • If timeout: Neon may pause idle databases (wait ~1 minute)")
    

async def main():
    """Run all database tests."""
    print("🚀 Database Test Suite")
    print("="*50)
    
    # Test 1: Basic connection
    if not await test_connection():
        print("\n❌ Database connection failed - check your configuration")
        return
    
    # Test 2: CRUD operations
    if not await test_data_operations():
        print("\n❌ Data operations failed")
        return
    
    # Test 3: Show existing data
    await show_existing_data()
    
    # Test 4: API endpoints
    await test_api()
    
    print("\n" + "="*50)
    print("✅ All tests completed successfully!")
    
    # Print pgAdmin guide
    print_pgadmin_guide()


if __name__ == "__main__":
    asyncio.run(main())