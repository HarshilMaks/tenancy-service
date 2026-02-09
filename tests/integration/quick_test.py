#!/usr/bin/env python3
"""Quick API-Database Integration Test"""

import asyncio
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from infrastructure.config import get_settings

settings = get_settings()

def get_async_url():
    url = str(settings.database.url)
    return url.split('?')[0].replace('postgresql://', 'postgresql+asyncpg://')

@pytest.mark.asyncio
async def test_organization_creation():
    print("\n📝 Testing organization creation...")
    
    test_org = {
        "name": "Test Organization " + str(asyncio.get_event_loop().time())[:8],
        "edition": "professional",
        "region": "us-east-1",
        "org_type": "production",
        "start_trial": True,
        "trial_days": 30
    }
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
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
                    print(f"✅ Organization created: {org.get('org_id')}")
                    return org.get('org_id')
            
            print(f"❌ API error: {response.status_code}")
            return None
                
        except Exception as e:
            print(f"❌ Request failed: {e}")
            return None

async def show_database_contents():
    print("\n📊 Current Database Contents:")
    
    engine = create_async_engine(get_async_url())
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM tenants"))
            tenant_count = result.scalar()
            print(f"Total tenants: {tenant_count}")
            
            if tenant_count > 0:
                result = await conn.execute(text("""
                    SELECT name, external_id, status, plan_tier, region, created_at
                    FROM tenants 
                    ORDER BY created_at DESC
                    LIMIT 5
                """))
                
                print("\nRecent tenants:")
                for i, row in enumerate(result.fetchall(), 1):
                    print(f"  {i}. {row[0]}")
                    print(f"     ID: {row[1]} | Status: {row[2]} | Plan: {row[3]}")
                    
    except Exception as e:
        print(f"❌ Database error: {e}")
    finally:
        await engine.dispose()

async def main():
    print("🚀 API-Database Integration Test")
    print("="*40)
    
    await test_organization_creation()
    await show_database_contents()
    
    print("\n" + "="*40)
    print("✅ Test completed!")

if __name__ == "__main__":
    asyncio.run(main())
