"""Integration tests for auth/user API."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_full_auth_flow(client: AsyncClient):
    # 1. Get captcha
    r = await client.get("/api/auth/captcha")
    assert r.status_code == 200
    captcha = r.json()
    assert captcha["captcha_id"]
    assert captcha["image_base64"]
    print(f"[captcha] id={captcha['captcha_id'][:8]}...")

    # Peek captcha answer (same process, share _store)
    from app.services.captcha_service import _store
    answer = _store[captcha["captcha_id"]][0]
    print(f"[captcha] answer={answer}")

    # 2. Register
    r = await client.post("/api/auth/register", json={
        "phone": "13800000001",
        "password": "test123",
        "nickname": "测试用户",
        "captcha_id": captcha["captcha_id"],
        "captcha_text": answer,
    })
    assert r.status_code == 200, f"Register failed: {r.text}"
    token_data = r.json()
    assert token_data["access_token"]
    assert token_data["refresh_token"]
    assert token_data["user"]["phone"] == "138****0001"
    print(f"[register] OK: user={token_data['user']['nickname']}")

    # 3. Login
    r = await client.post("/api/auth/login", json={
        "phone": "13800000001",
        "password": "test123",
    })
    assert r.status_code == 200
    token_data = r.json()
    access = token_data["access_token"]
    refresh = token_data["refresh_token"]
    print(f"[login] OK")

    # 4. GET /user/me
    r = await client.get("/api/user/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    user = r.json()
    assert user["phone"] == "138****0001"
    assert user["nickname"] == "测试用户"
    print(f"[get me] OK: {user['nickname']}")

    # 5. PUT /user/me
    r = await client.put("/api/user/me", headers={"Authorization": f"Bearer {access}"}, json={"nickname": "新昵称"})
    assert r.status_code == 200
    assert r.json()["nickname"] == "新昵称"
    print(f"[update] OK: {r.json()['nickname']}")

    # 6. Refresh token
    r = await client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    new_access = r.json()["access_token"]
    assert new_access
    print(f"[refresh] OK")

    # 7. Duplicate register
    r = await client.post("/api/auth/register", json={
        "phone": "13800000001",
        "password": "test123",
        "captcha_id": captcha["captcha_id"],
        "captcha_text": "wrong",
    })
    assert r.status_code == 400
    print(f"[dup register] {r.json()['detail']}")

    # 8. Wrong password
    r = await client.post("/api/auth/login", json={
        "phone": "13800000001",
        "password": "wrong",
    })
    assert r.status_code == 401
    print(f"[bad pwd] {r.json()['detail']}")

    # 9. No auth
    r = await client.get("/api/user/me")
    assert r.status_code == 401
    print(f"[no auth] {r.json()['detail']}")

    print("=== All 9 tests passed! ===")
