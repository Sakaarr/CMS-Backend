import pytest
from httpx import AsyncClient

BASE_AUTH = "/api/v1/auth"
BASE = "/api/v1/vendors"
TENANT_SLUG = "test-procurement-co"


async def get_token(client: AsyncClient, email: str, password: str = "Test@1234") -> str:
    r = await client.post(f"{BASE_AUTH}/login", json={"email": email, "password": password})
    return r.json()["data"]["access_token"]


async def setup_user_and_tenant(client: AsyncClient) -> dict:
    await client.post(f"{BASE_AUTH}/register", json={
        "email": "buyer@testco.com",
        "password": "Test@1234",
        "full_name": "Buyer User",
    })

    admin_token = await get_token(client, "admin@cms.com", "Admin@123456")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    await client.post("/api/v1/tenants", json={
        "name": "Procurement Co",
        "slug": TENANT_SLUG,
        "email": "info@procurementco.com",
    }, headers=admin_headers)

    token = await get_token(client, "buyer@testco.com")
    return {"Authorization": f"Bearer {token}", "X-Tenant-Slug": TENANT_SLUG}


@pytest.mark.asyncio
async def test_create_vendor_uppercases_code(client: AsyncClient):
    headers = await setup_user_and_tenant(client)
    r = await client.post(BASE, json={
        "name": "ABC Supplies",
        "code": "ven-001",
        "email": "abc@supplies.com",
    }, headers=headers)
    assert r.status_code == 201
    assert r.json()["success"] is True
    assert r.json()["data"]["code"] == "VEN-001"

