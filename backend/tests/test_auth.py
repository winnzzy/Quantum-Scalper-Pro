"""Authentication tests."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.auth.service import AuthService
from app.core.database import get_db
from app.models.user import User


@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    """Test user registration."""
    response = await client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "username": "testuser",
        "password": "TestPass123!"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["username"] == "testuser"


@pytest.mark.asyncio
async def test_login_user(client: AsyncClient):
    """Test user login."""
    # Register first
    await client.post("/api/v1/auth/register", json={
        "email": "login@example.com",
        "username": "loginuser",
        "password": "TestPass123!"
    })

    # Login
    response = await client.post("/api/v1/auth/login", data={
        "username": "login@example.com",
        "password": "TestPass123!"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_get_current_user(client: AsyncClient):
    """Test getting current user."""
    # Register and login
    await client.post("/api/v1/auth/register", json={
        "email": "me@example.com",
        "username": "meuser",
        "password": "TestPass123!"
    })

    login_response = await client.post("/api/v1/auth/login", data={
        "username": "me@example.com",
        "password": "TestPass123!"
    })
    token = login_response.json()["access_token"]

    # Get me
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me@example.com"


@pytest.mark.asyncio
async def test_invalid_login(client: AsyncClient):
    """Test invalid login credentials."""
    response = await client.post("/api/v1/auth/login", data={
        "username": "nonexistent@example.com",
        "password": "wrongpassword"
    })
    assert response.status_code == 401
