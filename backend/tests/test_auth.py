"""Integration tests for auth/user API."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.database import init_db


@pytest_asyncio.fixture
async def client():
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_full_auth_flow(client: AsyncClient):
    phone = f"138{uuid.uuid4().int % 100_000_000:08d}"
    masked_phone = phone[:3] + "****" + phone[-4:]

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
        "phone": phone,
        "password": "test123",
        "nickname": "测试用户",
        "captcha_id": captcha["captcha_id"],
        "captcha_text": answer,
    })
    assert r.status_code == 200, f"Register failed: {r.text}"
    token_data = r.json()
    assert token_data["access_token"]
    assert token_data["refresh_token"]
    assert token_data["user"]["phone"] == masked_phone
    print(f"[register] OK: user={token_data['user']['nickname']}")

    # 3. Login
    r = await client.post("/api/auth/login", json={
        "phone": phone,
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
    assert user["phone"] == masked_phone
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

    auth_headers = {"Authorization": f"Bearer {new_access}"}

    # 7. Cloud plan CRUD keeps the client-generated plan ID.
    plan_id = f"plan-{uuid.uuid4()}"
    r = await client.post("/api/user/plans", headers=auth_headers, json={
        "id": plan_id,
        "title": "成都周末游",
        "destination": "成都",
        "date_range": "2026-07-25 - 2026-07-27",
        "day_count": 3,
        "preferences": "[]",
        "plan_data": "{}",
    })
    assert r.status_code == 201, r.text
    assert r.json()["id"] == plan_id
    r = await client.put(f"/api/user/plans/{plan_id}", headers=auth_headers, json={"title": "成都三日游"})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "成都三日游"
    r = await client.get("/api/user/plans", headers=auth_headers)
    assert any(item["id"] == plan_id for item in r.json())
    r = await client.delete(f"/api/user/plans/{plan_id}", headers=auth_headers)
    assert r.status_code == 204, r.text

    # 8. Cloud footprint API.
    r = await client.post("/api/user/footprints", headers=auth_headers, json={
        "city_name": "成都",
        "province_name": "四川",
    })
    assert r.status_code == 201, r.text
    r = await client.get("/api/user/footprints", headers=auth_headers)
    assert any(item["city_name"] == "成都" for item in r.json())

    # 9. Cloud journal CRUD.
    r = await client.post("/api/user/journals", headers=auth_headers, json={
        "title": "成都第一天",
        "location": "成都",
        "date": "2026-07-25",
        "body": "测试游记",
        "photos": "[]",
    })
    assert r.status_code == 201, r.text
    journal_id = r.json()["id"]
    r = await client.put(f"/api/user/journals/{journal_id}", headers=auth_headers, json={"title": "成都第一日"})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "成都第一日"
    r = await client.get("/api/user/journals", headers=auth_headers)
    assert any(item["id"] == journal_id for item in r.json())
    r = await client.delete(f"/api/user/journals/{journal_id}", headers=auth_headers)
    assert r.status_code == 204, r.text

    # 10. Duplicate register
    r = await client.post("/api/auth/register", json={
        "phone": phone,
        "password": "test123",
        "captcha_id": captcha["captcha_id"],
        "captcha_text": "wrong",
    })
    assert r.status_code == 400
    print(f"[dup register] {r.json()['detail']}")

    # 11. Wrong password
    r = await client.post("/api/auth/login", json={
        "phone": phone,
        "password": "wrong",
    })
    assert r.status_code == 401
    print(f"[bad pwd] {r.json()['detail']}")

    # 12. No auth
    r = await client.get("/api/user/me")
    assert r.status_code == 401
    print(f"[no auth] {r.json()['detail']}")

    print("=== Auth and cloud CRUD integration tests passed! ===")
