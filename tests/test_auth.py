import pytest
from httpx import AsyncClient

BASE = "/api/v1/auth"


@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    response = await client.post(f"{BASE}/register", json={
        "email": "testuser@example.com",
        "password": "Test@1234",
        "full_name": "Test User",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["data"]["email"] == "testuser@example.com"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "Test@1234", "full_name": "Dup User"}
    await client.post(f"{BASE}/register", json=payload)
    response = await client.post(f"{BASE}/register", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    await client.post(f"{BASE}/register", json={
        "email": "login@example.com",
        "password": "Test@1234",
        "full_name": "Login User",
    })
    response = await client.post(f"{BASE}/login", json={
        "email": "login@example.com",
        "password": "Test@1234",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data["data"]
    assert "refresh_token" in data["data"]


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post(f"{BASE}/register", json={
        "email": "wrongpw@example.com",
        "password": "Test@1234",
        "full_name": "Wrong PW",
    })
    response = await client.post(f"{BASE}/login", json={
        "email": "wrongpw@example.com",
        "password": "WrongPassword1",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient):
    await client.post(f"{BASE}/register", json={
        "email": "me@example.com",
        "password": "Test@1234",
        "full_name": "Me User",
    })
    login = await client.post(f"{BASE}/login", json={
        "email": "me@example.com",
        "password": "Test@1234",
    })
    token = login.json()["data"]["access_token"]
    response = await client.get(
        f"{BASE}/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["email"] == "me@example.com"


@pytest.mark.asyncio
async def test_token_refresh(client: AsyncClient):
    await client.post(f"{BASE}/register", json={
        "email": "refresh@example.com",
        "password": "Test@1234",
        "full_name": "Refresh User",
    })
    login = await client.post(f"{BASE}/login", json={
        "email": "refresh@example.com",
        "password": "Test@1234",
    })
    refresh_token = login.json()["data"]["refresh_token"]
    response = await client.post(
        f"{BASE}/refresh", json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()["data"]