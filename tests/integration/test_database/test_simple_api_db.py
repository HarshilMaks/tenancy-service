import pytest
#!/usr/bin/env python3
"""
Simple API-Database Test
========================

Tests basic API-Database integration with actual working endpoints.
"""

import asyncio
import httpx
import json
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from infrastructure.config import get_settings

settings = get_settings()

def get_async_url():
    """Get async database URL."""
    url = str(settings.database.url)
    return url.split('?')[0].replace('postgresql://', 'postgresql+asyncpg://')

@pytest.mark.asyncio
async def test_database():
    """Test database connection."""
    print("🔍 Testing database connection...")
    
    engine = create_async_engine(get_async_url())
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM tenants"))
            tenant_count = result.scalar()
            result = await conn.execute(text("SELECT COUNT(*) FROM tenant_events"))
            event_count = result.scalar()
            print(f"✅ Database: {tenant_count} tenants, {event_count} events")
            return True
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False
    finally:
        await engine.dispose()

@pytest.mark.asyncio
async def test_api_endpoints():
    """Test available API endpoints."""
    print("\n🌐 Testing API endpoints...")
    
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        endpoints_to_test = [
            ("GET", "/"),
            ("GET", "/health"),
            ("GET", "/docs"),
        ]
        
        for method, path in endpoints_to_test:
            try:
                url = f"http://localhost:8000{path}"
                response = await client.request(method, url)
                print(f"✅ {method} {path}: {response.status_code}")
                
                if path == "/":
                    data = response.json()
                    print(f"   Service: {data.get('service', 'unknown')} v{data.get('version', 'unknown')}")
                    
            except Exception as e:
                print(f"❌ {method} {path}: {e}")

@pytest.mark.asyncio
async def test_organization_creation():
    """Test creating organization through API."""
    print("\n📝 Testing organization creation...")
    
    # Simplified test data that should work
    test_org = {
        "name": "Simple Test Organization",
        "edition": "professional",
        "region": "us-east-1",
        "org_type": "production",
        "start_trial": True,
        "trial_days": 30
    }
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            print(f"Creating organization: {test_org['name']}")
            response = await client.post(
                "http://localhost:8000/api/v1/organizations/",
                json=test_org
            )
            
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text[:500]}")
            
            if response.status_code == 201:
                data = response.json()
                if data.get('success'):
                    org = data.get('organization', {})
                    org_id = org.get('org_id', 'unknown')
                    print(f"✅ Organization created: {org_id}")
                    return org_id
                else:
                    print(f"❌ Creation failed: {data.get('errors', [])}")
                    return None
            else:
                print(f"❌ API error: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Request failed: {e}")
            return None

async def verify_in_database(org_id):
    """Check if organization exists in database."""
    print(f"\n🔍 Verifying organization {org_id} in database...")
    
    engine = create_async_engine(get_async_url())
    try:
        async with engine.begin() as conn:
            # Try to find by external_id (which is likely org_id)
            result = await conn.execute(text("""
                SELECT name, status, plan_tier, external_id
                FROM tenants 
                WHERE external_id = :org_id
                LIMIT 1
            """), {"org_id": org_id})
            
            row = result.fetchone()
            if row:
                print(f"✅ Found in database: {row[0]} | Status: {row[1]} | Plan: {row[2]}")
                return True
            else:
                # Maybe check by name too
                result = await conn.execute(text("""
                    SELECT name, status, plan_tier, external_id
                    FROM tenants 
                    WHERE name LIKE '%Simple Test%'
                    LIMIT 1
                """))
                row = result.fetchone()
                if row:
                    print(f"✅ Found by name: {row[0]} | Status: {row[1]} | External ID: {row[3]}")
                    return True
                else:
                    print("❌ Not found in database")
                    return False
                    
    except Exception as e:
        print(f"❌ Database verification failed: {e}")
        return False
    finally:
        await engine.dispose()

async def show_database_contents():
    """Show what's actually in the database."""
    print("\n📊 Current Database Contents:")
    
    engine = create_async_engine(get_async_url())
    try:
        async with engine.begin() as conn:
            # Count records
            result = await conn.execute(text("SELECT COUNT(*) FROM tenants"))
            tenant_count = result.scalar()
            print(f"Total tenants: {tenant_count}")
            
            if tenant_count > 0:
                # Show all tenants
                result = await conn.execute(text("""
                    SELECT name, external_id, status, plan_tier, region, created_at
                    FROM tenants 
                    ORDER BY created_at DESC
                """))
                
                print("\nAll tenants:")
                for i, row in enumerate(result.fetchall(), 1):
                    print(f"  {i}. {row[0]}")
                    print(f"     ID: {row[1]} | Status: {row[2]} | Plan: {row[3]} | Region: {row[4]}")
                    print(f"     Created: {row[5]}")
                    print()
            
            # Show events
            result = await conn.execute(text("SELECT COUNT(*) FROM tenant_events"))
            event_count = result.scalar()
            print(f"Total events: {event_count}")
            
            if event_count > 0:
                result = await conn.execute(text("""
                    SELECT event_type, payload, created_at
                    FROM tenant_events 
                    ORDER BY created_at DESC
                    LIMIT 3
                """))
                
                print("\nRecent events:")
                for i, row in enumerate(result.fetchall(), 1):
                    print(f"  {i}. {row[0]} - {row[2]}")
                    
    except Exception as e:
        print(f"❌ Database contents error: {e}")
    finally:
        await engine.dispose()

async def main():
    """Run the simple test."""
    print("🚀 Simple API-Database Integration Test")
    print("="*50)
    
    # Test 1: Database
    if not await test_database():
        print("❌ Database test failed")
        return
    
    # Test 2: API endpoints
    await test_api_endpoints()
    
    # Test 3: Organization creation
    org_id = await test_organization_creation()
    
    # Test 4: Verify in database
    if org_id:
        await verify_in_database(org_id)
    
    # Test 5: Show contents
    await show_database_contents()
    
    print("\n" + "="*50)
    print("✅ Test completed!")
    print("\n💡 Check:")
    print("   • Swagger UI: http://localhost:8000/docs")
    print("   • Server logs for any errors")
    print("   • pgAdmin 4 for database verification")

if __name__ == "__main__":
    asyncio.run(main())