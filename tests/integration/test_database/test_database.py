import pytest
#!/usr/bin/env python3
"""
Database Test Script
====================

Simple script to test database connectivity and CRUD operations.
Use this to verify data input/output with your Neon PostgreSQL database.
"""

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4
import time
import re
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

from sqlalchemy import text, create_engine
from sqlalchemy.ext.asyncio import create_async_engine

from infrastructure.config import get_settings

# Get database settings
settings = get_settings()


@pytest.mark.asyncio
async def test_database_connection():
    """Test basic database connectivity."""
    print("🔗 Testing database connection...")
    
    try:
        # Convert sync URL to async URL for asyncpg using URL parsing
        url = str(settings.database.url)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        parsed = urlparse(url)
        q = dict(parse_qsl(parsed.query))
        # Remove Neon-specific or driver-specific query params that asyncpg.connect doesn't accept
        q.pop('channel_binding', None)
        q.pop('sslmode', None)
        new_query = urlencode(q, doseq=True)
        parsed = parsed._replace(query=new_query)
        async_url = urlunparse(parsed)
        
        engine = create_async_engine(async_url)
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"✅ Database connected successfully!")
            print(f"   PostgreSQL version: {version}")
            
            # Test tables exist
            result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """))
            tables = [row[0] for row in result.fetchall()]
            print(f"   Tables found: {', '.join(tables)}")
            
        await engine.dispose()
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


@pytest.mark.asyncio
async def test_tenant_crud_operations():
    """Test Create, Read, Update, Delete operations on tenants."""
    print("\n📝 Testing Tenant CRUD operations...")
    
    # Convert sync URL to async URL for asyncpg using URL parsing
    url = str(settings.database.url)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    parsed = urlparse(url)
    q = dict(parse_qsl(parsed.query))
    # Remove Neon-specific or driver-specific query params that asyncpg.connect doesn't accept
    q.pop('channel_binding', None)
    q.pop('sslmode', None)
    new_query = urlencode(q, doseq=True)
    parsed = parsed._replace(query=new_query)
    async_url = urlunparse(parsed)
    
    engine = create_async_engine(async_url)
    
    try:
        async with engine.begin() as conn:
            # Test 1: CREATE - Insert a new tenant
            test_tenant_id = uuid4()
            current_time = datetime.now(timezone.utc)
            
            await conn.execute(text("""
                INSERT INTO tenants (
                    id, name, normalized_name, external_id,
                    status, plan_tier, region,
                    compliance_requirements, plan_limits, metadata,
                    created_at, updated_at, version
                ) VALUES (
                    :id, :name, :normalized_name, :external_id,
                    :status, :plan_tier, :region,
                    :compliance_requirements, :plan_limits, :metadata,
                    :created_at, :updated_at, :version
                )
            """), {
                "id": str(test_tenant_id),
                "name": f"Test Tenant {current_time.strftime('%H:%M:%S')}",
                "normalized_name": f"test_tenant_{current_time.strftime('%H%M%S')}",
                "external_id": f"ORG-{test_tenant_id.hex[:8].upper()}",
                "status": "active",
                "plan_tier": "professional",
                "region": "us-east-1",
                "compliance_requirements": json.dumps({}),
                "plan_limits": json.dumps({"test": True}),
                "metadata": json.dumps({"created_via": "test_script"}),
                "created_at": current_time,
                "updated_at": current_time,
                "version": 1
            })
            
            print(f"✅ Created tenant: Test Tenant (ID: {test_tenant_id})")
            
            # Test 2: READ - Query the tenant back
            result = await conn.execute(text("""
                SELECT name, status, plan_tier, metadata FROM tenants WHERE id = :id
            """), {"id": str(test_tenant_id)})
            
            row = result.fetchone()
            if row:
                print(f"✅ Retrieved tenant: {row[0]}")
                print(f"   Status: {row[1]}")
                print(f"   Plan: {row[2]}")
                print(f"   Settings: {row[3]}")
            
            # Test 3: UPDATE - Modify the tenant
            await conn.execute(text("""
                UPDATE tenants 
                SET status = :status, 
                    suspended_reason = :suspended_reason,
                    suspended_at = :suspended_at,
                    metadata = :metadata, 
                    updated_at = :updated_at,
                    version = version + 1
                WHERE id = :id
            """), {
                "id": str(test_tenant_id),
                "status": "suspended",
                "suspended_reason": "testing",
                "suspended_at": datetime.now(timezone.utc),
                "metadata": json.dumps({"updated_by": "database_test_script"}),
                "updated_at": datetime.now(timezone.utc)
            })
            
            print("✅ Updated tenant status to SUSPENDED")
            
            # Verify update
            result = await conn.execute(text("""
                SELECT status FROM tenants WHERE id = :id
            """), {"id": str(test_tenant_id)})
            new_status = result.scalar()
            print(f"   New status: {new_status}")
            
            # Test 4: CREATE EVENT - Add a tenant event
            test_event_id = uuid4()
            await conn.execute(text("""
                INSERT INTO tenant_events (
                    id, tenant_id, event_type, event_version, payload, metadata, created_at
                ) VALUES (
                    :id, :tenant_id, :event_type, :event_version, :payload, :metadata, :created_at
                )
            """), {
                "id": str(test_event_id),
                "tenant_id": str(test_tenant_id),
                "event_type": "tenant_created",
                "event_version": 1,
                "payload": json.dumps({"reason": "Database test", "test": True}),
                "metadata": json.dumps({"source": "test"}),
                "created_at": datetime.now(timezone.utc)
            })
            
            print(f"✅ Created tenant event: tenant_created")
            
            # Test 5: READ EVENTS - Query events
            result = await conn.execute(text("""
                SELECT event_type, payload FROM tenant_events WHERE tenant_id = :tenant_id
            """), {"tenant_id": str(test_tenant_id)})
            
            events = result.fetchall()
            print(f"✅ Retrieved {len(events)} events for tenant")
            for event in events:
                print(f"   Event: {event[0]} - Data: {event[1]}")
            
            # Test 6: DELETE - Clean up test data
            await conn.execute(text("""
                DELETE FROM tenant_events WHERE tenant_id = :tenant_id
            """), {"tenant_id": str(test_tenant_id)})
            
            await conn.execute(text("""
                DELETE FROM tenants WHERE id = :id
            """), {"id": str(test_tenant_id)})
            
            print("✅ Cleaned up test data (deleted tenant and events)")
            
    except Exception as e:
        print(f"❌ CRUD operations failed: {e}")
        raise
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_api_endpoints():
    """Test API endpoints using HTTP requests."""
    print("\n🌐 Testing API endpoints...")
    
    try:
        import httpx
        
        # Test health endpoint
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get("http://localhost:8000/health")
                if response.status_code == 200:
                    health_data = response.json()
                    print(f"✅ Health check: {health_data['status']}")
                    print(f"   Service: {health_data['service']}")
                    print(f"   Version: {health_data['version']}")
                else:
                    print(f"❌ Health check failed: {response.status_code}")
            except httpx.ConnectError:
                print("⚠️  API server not running on localhost:8000")
                print("   Start with: uv run python -m app.main")
                return
            
            # Test tenants list endpoint  
            try:
                response = await client.get("http://localhost:8000/api/v1/tenants")
                if response.status_code == 200:
                    tenants_data = response.json()
                    print(f"✅ Tenants endpoint: {len(tenants_data)} tenants found")
                    if tenants_data:
                        print(f"   First tenant: {tenants_data[0].get('name', 'Unknown')}")
                else:
                    print(f"❌ Tenants endpoint failed: {response.status_code}")
                    
            except Exception as e:
                print(f"⚠️  Tenants endpoint error: {e}")
                
    except ImportError:
        print("⚠️  httpx not installed - skipping API tests")
        print("   Install with: uv add httpx")
    except Exception as e:
        print(f"❌ API test failed: {e}")


async def show_current_data():
    """Show current data in the database."""
    print("\n📊 Current Database Data:")
    
    # Convert sync URL to async URL for asyncpg using URL parsing
    url = str(settings.database.url)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    parsed = urlparse(url)
    q = dict(parse_qsl(parsed.query))
    q.pop('channel_binding', None)
    q.pop('sslmode', None)
    new_query = urlencode(q, doseq=True)
    parsed = parsed._replace(query=new_query)
    async_url = urlunparse(parsed)
    
    engine = create_async_engine(async_url)
    
    try:
        async with engine.begin() as conn:
            # Count tenants
            result = await conn.execute(text("SELECT COUNT(*) FROM tenants"))
            tenant_count = result.scalar()
            print(f"📁 Total tenants: {tenant_count}")
            
            if tenant_count > 0:
                result = await conn.execute(text("""
                    SELECT name, status, created_at 
                    FROM tenants 
                    ORDER BY created_at DESC 
                    LIMIT 5
                """))
                tenants = result.fetchall()
                print("   Recent tenants:")
                for tenant in tenants:
                    print(f"   • {tenant[0]} ({tenant[1]}) - Created: {tenant[2]}")
            
            # Count events
            result = await conn.execute(text("SELECT COUNT(*) FROM tenant_events"))
            event_count = result.scalar()
            print(f"📝 Total events: {event_count}")
            
            if event_count > 0:
                result = await conn.execute(text("""
                    SELECT event_type, created_at 
                    FROM tenant_events 
                    ORDER BY created_at DESC 
                    LIMIT 5
                """))
                events = result.fetchall()
                print("   Recent events:")
                for event in events:
                    print(f"   • {event[0]} - {event[1]}")
            
    except Exception as e:
        print(f"❌ Failed to show data: {e}")
    finally:
        await engine.dispose()


def print_pgadmin_instructions():
    """Print instructions for using pgAdmin 4."""
    print("\n🔍 pgAdmin 4 Verification Instructions:")
    print("=" * 50)
    print("1. Open pgAdmin 4")
    print("2. Create New Server Connection:")
    print("   - Name: Neon Tenancy DB")
    print("   - Host: [See .env.local]")
    print("   - Port: 5432")
    print("   - Database: [See .env.local]")
    print("   - Username: [See .env.local]")
    print("   - Password: [See .env.local]")
    print("   - SSL Mode: Require")
    print("\n3. Navigate to: Servers > Neon Tenancy DB > Databases > neondb > Schemas > public > Tables")
    print("\n4. Test with these SQL queries:")
    print("   ┌─────────────────────────────────────────┐")
    print("   │ -- Check all tenants                   │")
    print("   │ SELECT * FROM tenants;                 │")
    print("   │                                        │")
    print("   │ -- Check tenant events                 │")  
    print("   │ SELECT * FROM tenant_events;           │")
    print("   │                                        │")
    print("   │ -- Count records                       │")
    print("   │ SELECT COUNT(*) FROM tenants;          │")
    print("   │ SELECT COUNT(*) FROM tenant_events;    │")
    print("   │                                        │")
    print("   │ -- Test inserting data                 │")
    print("   │ INSERT INTO tenants (id, name,         │")
    print("   │   normalized_name, external_id,        │")
    print("   │   status, plan_tier, region,           │")
    print("   │   compliance_requirements, plan_limits,│")
    print("   │   metadata, created_at, updated_at)    │")
    print("   │ VALUES (                               │")
    print("   │   gen_random_uuid(),                   │")
    print("   │   'Test from pgAdmin',                 │")
    print("   │   'test_from_pgadmin',                 │")
    print("   │   'test-pgadmin',                      │")
    print("   │   'test.example.com',                  │")
    print("   │   'active',                            │")
    print("   │   'starter',                           │")
    print("   │   '{}',                                │")
    print("   │   '{}',                                │")
    print("   │   NOW(),                               │")
    print("   │   NOW()                                │")
    print("   │ );                                     │")
    print("   └─────────────────────────────────────────┘")


async def main():
    """Run all database tests."""
    print("🔄 Starting Database Tests")
    print("=" * 50)
    
    # Test 1: Database connection
    if not await test_database_connection():
        print("❌ Database connection failed - stopping tests")
        return
    
    # Test 2: CRUD operations
    await test_tenant_crud_operations()
    
    # Test 3: Show current data
    await show_current_data()
    
    # Test 4: API endpoints
    await test_api_endpoints()
    
    print("\n" + "=" * 50)
    print("✅ Database tests completed!")
    
    # Print pgAdmin instructions
    print_pgadmin_instructions()


if __name__ == "__main__":
    asyncio.run(main())