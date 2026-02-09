import pytest
#!/usr/bin/env python3
"""
API-Database Integration Test
============================

Tests the complete data flow from API → Database → API
Creates multiple tenants via API and verifies they're stored in database.
"""

import asyncio
import httpx
import json
from datetime import datetime
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from infrastructure.config import get_settings

settings = get_settings()

def get_async_url():
    """Get async database URL."""
    url = str(settings.database.url)
    return url.split('?')[0].replace('postgresql://', 'postgresql+asyncpg://')

async def check_database_direct():
    """Test direct database connection."""
    print("🔍 Testing direct database connection...")
    
    engine = create_async_engine(get_async_url())
    try:
        async with engine.begin() as conn:
            # Test connection
            result = await conn.execute(text("SELECT COUNT(*) FROM tenants"))
            tenant_count = result.scalar()
            
            result = await conn.execute(text("SELECT COUNT(*) FROM tenant_events"))
            event_count = result.scalar()
            
            print(f"✅ Database responsive: {tenant_count} tenants, {event_count} events")
            return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False
    finally:
        await engine.dispose()

@pytest.mark.asyncio
async def test_api_server():
    """Check if API server is running."""
    print("\n🌐 Testing API server...")
    
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get("http://localhost:8000/health")
            if response.status_code == 200:
                print("✅ API server is running")
                data = response.json()
                print(f"   Service: {data.get('service', 'unknown')} v{data.get('version', 'unknown')}")
                return True
            else:
                print(f"❌ API server unhealthy: {response.status_code}")
                return False
    except Exception as e:
        print(f"❌ API server not accessible: {e}")
        print("💡 Start with: uv run python -m app.main")
        return False

async def create_tenant_via_api(client, tenant_data):
    """Create a tenant via API."""
    try:
        response = await client.post(
            "http://localhost:8000/api/v1/organizations",
            json=tenant_data
        )
        
        if response.status_code == 201:
            created = response.json()
            print(f"✅ Created tenant via API: {created['name']} (ID: {created['id'][:8]}...)")
            return created['id']
        else:
            print(f"❌ Failed to create tenant: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ API creation error: {e}")
        return None

async def verify_tenant_in_database(tenant_id, expected_name):
    """Verify tenant exists in database."""
    engine = create_async_engine(get_async_url())
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT name, status, plan_tier, external_id, region
                FROM tenants 
                WHERE id = :id
            """), {"id": tenant_id})
            
            row = result.fetchone()
            if row:
                print(f"✅ Found in database: {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]}")
                return True
            else:
                print(f"❌ Tenant {tenant_id} not found in database")
                return False
                
    except Exception as e:
        print(f"❌ Database verification error: {e}")
        return False
    finally:
        await engine.dispose()

async def get_tenant_via_api(client, tenant_id):
    """Get tenant data via API."""
    try:
        # Try to get tenant by listing all (since we don't have individual get endpoint)
        response = await client.get("http://localhost:8000/api/v1/tenants")
        if response.status_code == 200:
            tenants = response.json()
            for tenant in tenants:
                if tenant['id'] == tenant_id:
                    print(f"✅ Retrieved via API: {tenant['name']} | {tenant['status']}")
                    return tenant
            print(f"❌ Tenant {tenant_id[:8]}... not found in API response")
            return None
        else:
            print(f"❌ Failed to get tenants: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ API retrieval error: {e}")
        return None

async def create_test_data():
    """Create multiple test tenants and verify full data flow."""
    print("\n📝 Testing API → Database → API data flow...")
    
    # Test data
    test_tenants = [
        {
            "name": "Tech Startup Inc",
            "external_id": "tech-startup-001",
            "plan_tier": "professional",
            "region": "us-west-2",
            "compliance_requirements": ["SOC2", "GDPR"],
            "plan_limits": {"users": 50, "storage_gb": 100}
        },
        {
            "name": "Global Enterprise Corp",
            "external_id": "enterprise-002", 
            "plan_tier": "enterprise",
            "region": "eu-central-1",
            "compliance_requirements": ["SOC2", "GDPR", "HIPAA"],
            "plan_limits": {"users": 500, "storage_gb": 1000}
        },
        {
            "name": "Small Business Co",
            "external_id": "small-biz-003",
            "plan_tier": "starter", 
            "region": "us-east-1",
            "compliance_requirements": ["SOC2"],
            "plan_limits": {"users": 5, "storage_gb": 10}
        }
    ]
    
    created_ids = []
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        # Step 1: Create tenants via API
        print("\n🔄 Step 1: Creating tenants via API...")
        for i, tenant_data in enumerate(test_tenants, 1):
            print(f"\n[{i}/3] Creating: {tenant_data['name']}")
            tenant_id = await create_tenant_via_api(client, tenant_data)
            if tenant_id:
                created_ids.append((tenant_id, tenant_data['name']))
            await asyncio.sleep(1)  # Small delay between requests
        
        if not created_ids:
            print("❌ No tenants were created successfully")
            return False
        
        print(f"\n✅ Created {len(created_ids)} tenants via API")
        
        # Step 2: Verify in database
        print("\n🔄 Step 2: Verifying tenants in database...")
        db_verified = 0
        for tenant_id, expected_name in created_ids:
            if await verify_tenant_in_database(tenant_id, expected_name):
                db_verified += 1
        
        print(f"\n✅ Verified {db_verified}/{len(created_ids)} tenants in database")
        
        # Step 3: Retrieve via API
        print("\n🔄 Step 3: Retrieving tenants via API...")
        api_verified = 0
        for tenant_id, expected_name in created_ids:
            if await get_tenant_via_api(client, tenant_id):
                api_verified += 1
        
        print(f"\n✅ Retrieved {api_verified}/{len(created_ids)} tenants via API")
        
        # Step 4: Show database state
        print("\n🔄 Step 4: Current database state...")
        await show_database_summary()
        
        # Step 5: Clean up (optional)
        print(f"\n🧹 Cleanup: Created {len(created_ids)} test tenants")
        print("   To clean up manually, run SQL:")
        for tenant_id, name in created_ids:
            print(f"   DELETE FROM tenant_events WHERE tenant_id = '{tenant_id}';")
            print(f"   DELETE FROM tenants WHERE id = '{tenant_id}';")
        
        return db_verified == len(created_ids) and api_verified == len(created_ids)

async def show_database_summary():
    """Show current database state with details."""
    engine = create_async_engine(get_async_url())
    try:
        async with engine.begin() as conn:
            # Count all records
            result = await conn.execute(text("SELECT COUNT(*) FROM tenants"))
            tenant_count = result.scalar()
            
            result = await conn.execute(text("SELECT COUNT(*) FROM tenant_events"))
            event_count = result.scalar()
            
            print(f"📊 Database Summary: {tenant_count} tenants, {event_count} events")
            
            # Show recent tenants with details
            if tenant_count > 0:
                result = await conn.execute(text("""
                    SELECT name, status, plan_tier, region, external_id, created_at
                    FROM tenants 
                    ORDER BY created_at DESC 
                    LIMIT 5
                """))
                
                print("\n📋 Recent Tenants:")
                for i, row in enumerate(result.fetchall(), 1):
                    print(f"   {i}. {row[0]} ({row[1]}) - {row[2]} plan in {row[3]}")
                    print(f"      ID: {row[4]} | Created: {row[5]}")
            
            # Show recent events
            if event_count > 0:
                result = await conn.execute(text("""
                    SELECT event_type, payload, created_at
                    FROM tenant_events 
                    ORDER BY created_at DESC 
                    LIMIT 5
                """))
                
                print("\n📝 Recent Events:")
                for i, row in enumerate(result.fetchall(), 1):
                    print(f"   {i}. {row[0]} - {row[2]}")
                    
    except Exception as e:
        print(f"❌ Database summary error: {e}")
    finally:
        await engine.dispose()

@pytest.mark.asyncio
async def test_api_endpoints():
    """Test various API endpoints."""
    print("\n🔄 Testing API endpoints...")
    
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        endpoints = [
            ("Health", "GET", "/health"),
            ("Root", "GET", "/"),
            ("Health Detailed", "GET", "/health/detailed"),
            ("Tenants List", "GET", "/api/v1/tenants"),
            ("Docs", "GET", "/docs"),
        ]
        
        for name, method, path in endpoints:
            try:
                url = f"http://localhost:8000{path}"
                response = await client.request(method, url)
                
                if response.status_code in [200, 201]:
                    print(f"✅ {name}: {response.status_code}")
                    if path == "/api/v1/tenants":
                        data = response.json()
                        print(f"   → {len(data)} tenants returned")
                else:
                    print(f"⚠️  {name}: {response.status_code}")
                    
            except Exception as e:
                print(f"❌ {name}: {e}")

async def main():
    """Run complete API-Database integration test."""
    print("🚀 API-Database Integration Test")
    print("="*50)
    
    # Step 1: Test database
    if not await check_database_direct():
        print("\n❌ Database test failed - stopping")
        return
    
    # Step 2: Test API server
    if not await test_api_server():
        print("\n❌ API server test failed - stopping")
        return
    
    # Step 3: Test API endpoints
    await test_api_endpoints()
    
    # Step 4: Test data flow
    success = await create_test_data()
    
    print("\n" + "="*50)
    if success:
        print("✅ All tests passed! API ↔ Database integration working correctly!")
    else:
        print("❌ Some tests failed. Check the output above for details.")
        
    print("\n💡 Next steps:")
    print("   • Open Swagger UI: http://localhost:8000/docs")
    print("   • Use pgAdmin 4 to verify database changes")
    print("   • API logs show in the server terminal")

if __name__ == "__main__":
    asyncio.run(main())