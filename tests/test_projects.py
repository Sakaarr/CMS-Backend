import pytest
from httpx import AsyncClient

BASE_AUTH = "/api/v1/auth"
BASE = "/api/v1/projects"
TENANT_SLUG = "test-company"


async def get_token(client: AsyncClient, email: str, password: str = "Test@1234") -> str:
    r = await client.post(f"{BASE_AUTH}/login", json={"email": email, "password": password})
    return r.json()["data"]["access_token"]


async def setup_user_and_tenant(client: AsyncClient) -> dict:
    """Register a user, create a tenant, return auth headers."""
    # Register
    await client.post(f"{BASE_AUTH}/register", json={
        "email": "pm@testco.com",
        "password": "Test@1234",
        "full_name": "Project Manager",
    })
    # Login as superadmin to create tenant
    admin_token = await get_token(client, "admin@cms.com", "Admin@123456")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    await client.post("/api/v1/tenants", json={
        "name": "Test Company",
        "slug": TENANT_SLUG,
        "email": "info@testco.com",
    }, headers=admin_headers)
    # Login as PM
    token = await get_token(client, "pm@testco.com")
    return {"Authorization": f"Bearer {token}", "X-Tenant-Slug": TENANT_SLUG}


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient):
    headers = await setup_user_and_tenant(client)
    response = await client.post(BASE, json={
        "name": "Kathmandu Office Block",
        "code": "PRJ-001",
        "project_type": "commercial",
        "city": "Kathmandu",
        "district": "Kathmandu",
        "estimated_budget": 50000000,
        "currency": "NPR",
    }, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["data"]["code"] == "PRJ-001"


@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient):
    headers = await setup_user_and_tenant(client)
    await client.post(BASE, json={
        "name": "Test Project", "code": "PRJ-002",
    }, headers=headers)
    response = await client.get(BASE, headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] >= 1


@pytest.mark.asyncio
async def test_project_status_transition(client: AsyncClient):
    headers = await setup_user_and_tenant(client)
    r = await client.post(BASE, json={
        "name": "Status Test", "code": "PRJ-003",
    }, headers=headers)
    project_id = r.json()["data"]["id"]

    # DRAFT → PLANNING (valid)
    r = await client.patch(f"{BASE}/{project_id}/status",
        json={"status": "planning"}, headers=headers)
    assert r.status_code == 200

    # PLANNING → COMPLETED (invalid — must go through ACTIVE)
    r = await client.patch(f"{BASE}/{project_id}/status",
        json={"status": "completed"}, headers=headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_site(client: AsyncClient):
    headers = await setup_user_and_tenant(client)
    r = await client.post(BASE, json={
        "name": "Site Test Project", "code": "PRJ-004",
    }, headers=headers)
    project_id = r.json()["data"]["id"]

    r = await client.post(f"{BASE}/{project_id}/sites", json={
        "name": "Main Site", "code": "SITE-001",
        "city": "Pokhara", "district": "Kaski",
    }, headers=headers)
    assert r.status_code == 201
    assert r.json()["data"]["code"] == "SITE-001"


@pytest.mark.asyncio
async def test_create_milestone(client: AsyncClient):
    headers = await setup_user_and_tenant(client)
    r = await client.post(BASE, json={
        "name": "Milestone Project", "code": "PRJ-005",
    }, headers=headers)
    project_id = r.json()["data"]["id"]

    r = await client.post(f"{BASE}/{project_id}/milestones", json={
        "name": "Foundation Complete",
        "planned_date": "2025-06-30",
        "sequence": 1,
        "is_critical": True,
    }, headers=headers)
    assert r.status_code == 201
    assert r.json()["data"]["is_critical"] is True


@pytest.mark.asyncio
async def test_duplicate_project_code(client: AsyncClient):
    headers = await setup_user_and_tenant(client)
    await client.post(BASE, json={"name": "First", "code": "PRJ-DUP"}, headers=headers)
    r = await client.post(BASE, json={"name": "Second", "code": "PRJ-DUP"}, headers=headers)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_tenant_isolation(client: AsyncClient):
    """Projects from tenant A must not be visible to tenant B."""
    # Tenant A
    await client.post(f"{BASE_AUTH}/register", json={
        "email": "usera@a.com", "password": "Test@1234", "full_name": "User A"
    })
    admin_token = await get_token(client, "admin@cms.com", "Admin@123456")
    admin_h = {"Authorization": f"Bearer {admin_token}"}
    await client.post("/api/v1/tenants", json={
        "name": "Company A", "slug": "company-a", "email": "a@a.com"
    }, headers=admin_h)
    await client.post("/api/v1/tenants", json={
        "name": "Company B", "slug": "company-b", "email": "b@b.com"
    }, headers=admin_h)

    token_a = await get_token(client, "usera@a.com")
    headers_a = {"Authorization": f"Bearer {token_a}", "X-Tenant-Slug": "company-a"}

    await client.post(BASE, json={
        "name": "Secret Project A", "code": "SECRET-A"
    }, headers=headers_a)

    # Register user B
    await client.post(f"{BASE_AUTH}/register", json={
        "email": "userb@b.com", "password": "Test@1234", "full_name": "User B"
    })
    token_b = await get_token(client, "userb@b.com")
    headers_b = {"Authorization": f"Bearer {token_b}", "X-Tenant-Slug": "company-b"}

    r = await client.get(BASE, headers=headers_b)
    projects = r.json()["data"]
    assert not any(p["code"] == "SECRET-A" for p in projects)