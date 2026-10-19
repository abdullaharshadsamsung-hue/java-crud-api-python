"""Tests for app/routers/users.py."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport
from sqlalchemy.exc import MultipleResultsFound

from app.errors import UserDeleteError, UserNotFoundException, register_exception_handlers
from app.models.user import User
from app.routers.users import router
from app.services.user_service import get_user_service


def _user(id=1, name="alice", email="a@x.com", password="pw", role="admin", about="hi"):
    return User(id, name, email, password, role, about)


def _as_json(u: User) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "password": u.password,
        "role": u.role,
        "about": u.about,
    }


@pytest.fixture
def service():
    svc = AsyncMock()
    svc.save_user = AsyncMock(return_value=None)
    svc.fetch_user_list = AsyncMock(return_value=[])
    svc.fetch_user_by_id = AsyncMock()
    svc.delete_user = AsyncMock(return_value=None)

    async def _update(user_id, user):
        user.id = user_id
        return user

    svc.update_user = AsyncMock(side_effect=_update)
    svc.get_user_by_name = AsyncMock(return_value=None)
    return svc


@pytest.fixture
def app(service):
    application = FastAPI()
    register_exception_handlers(application)
    application.include_router(router)
    application.dependency_overrides[get_user_service] = lambda: service
    return application


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------- POST save
@pytest.mark.asyncio
async def test_save_user_success(client, service, caplog):
    caplog.set_level(logging.INFO)
    body = {"name": "alice", "email": "a@x.com", "password": "pw", "role": "r", "about": "x"}
    resp = await client.post("/save_user_data", json=body)
    assert resp.status_code == 200
    assert resp.text == "User data saved successfully!"
    assert resp.headers["content-type"].startswith("text/plain")
    service.save_user.assert_awaited_once()
    saved = service.save_user.await_args.args[0]
    assert isinstance(saved, User)
    assert saved.name == "alice"
    assert saved.email == "a@x.com"
    assert saved.password == "pw"
    assert saved.role == "r"
    assert saved.about == "x"
    assert saved.id == 0
    assert "inside the saveUser of UserController" in caplog.text


@pytest.mark.asyncio
async def test_save_user_ignores_unknown_fields_and_does_not_echo(client, service):
    resp = await client.post("/save_user_data", json={"name": "bob", "unknown": 1})
    assert resp.status_code == 200
    assert resp.text == "User data saved successfully!"
    assert "bob" not in resp.text
    service.save_user.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"name": ""}, {"name": "   "}, {"name": None}, {"email": "a@x.com"}])
async def test_save_user_blank_name_returns_400(client, service, body):
    resp = await client.post("/save_user_data", json=body)
    assert resp.status_code == 400
    assert resp.json()["error"] == "Bad Request"
    service.save_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_user_blank_name_message(client, service):
    resp = await client.post("/save_user_data", json={"name": ""})
    assert resp.status_code == 400
    assert "please Add the department Name" in str(resp.json()["details"])


@pytest.mark.asyncio
async def test_save_user_malformed_json_returns_400(client, service):
    resp = await client.post(
        "/save_user_data", content=b"{not json", headers={"content-type": "application/json"}
    )
    assert resp.status_code == 400
    service.save_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_user_missing_body_returns_400(client, service):
    resp = await client.post("/save_user_data")
    assert resp.status_code == 400
    service.save_user.assert_not_awaited()


# ---------------------------------------------------------------- GET list
@pytest.mark.asyncio
async def test_fetch_user_list_returns_users_in_order(client, service, caplog):
    caplog.set_level(logging.INFO)
    users = [_user(3, "c"), _user(1, "a", email="b@x.com"), _user(2, "b", email="c@x.com")]
    service.fetch_user_list.return_value = users
    resp = await client.get("/get_user_data")
    assert resp.status_code == 200
    assert resp.json() == [_as_json(u) for u in users]
    service.fetch_user_list.assert_awaited_once()
    assert "inside the fetchUserList of UserController" in caplog.text


@pytest.mark.asyncio
async def test_fetch_user_list_empty(client, service):
    service.fetch_user_list.return_value = []
    resp = await client.get("/get_user_data")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------- GET by id
@pytest.mark.asyncio
async def test_fetch_user_by_id_found(client, service):
    u = _user(7)
    service.fetch_user_by_id.return_value = u
    resp = await client.get("/get_user_data/7")
    assert resp.status_code == 200
    assert resp.json() == _as_json(u)
    service.fetch_user_by_id.assert_awaited_once_with(7)


@pytest.mark.asyncio
async def test_fetch_user_by_id_not_found(client, service):
    service.fetch_user_by_id.side_effect = UserNotFoundException("User not found")
    resp = await client.get("/get_user_data/99")
    assert resp.status_code == 404
    body = resp.json()
    assert body["status"] == "NOT_FOUND"
    assert body["message"] == "User not found"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["abc", "1.5", "2147483648", "-2147483649"])
async def test_fetch_user_by_id_bad_id_returns_400(client, service, bad):
    resp = await client.get(f"/get_user_data/{bad}")
    assert resp.status_code == 400
    service.fetch_user_by_id.assert_not_awaited()


# ---------------------------------------------------------------- DELETE
@pytest.mark.asyncio
async def test_delete_user_success(client, service):
    resp = await client.delete("/delete_user_data/5")
    assert resp.status_code == 200
    assert resp.text == "user data deleted Successfully"
    assert resp.headers["content-type"].startswith("text/plain")
    service.delete_user.assert_awaited_once_with(5)


@pytest.mark.asyncio
async def test_delete_user_missing_id_returns_500(client, service):
    service.delete_user.side_effect = UserDeleteError(42)
    resp = await client.delete("/delete_user_data/42")
    assert resp.status_code == 500
    assert resp.json()["details"] == "No User entity with id 42 exists!"


@pytest.mark.asyncio
async def test_delete_user_unexpected_error_returns_500(client, service):
    service.delete_user.side_effect = RuntimeError("boom")
    resp = await client.delete("/delete_user_data/1")
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_delete_user_bad_id_returns_400(client, service):
    resp = await client.delete("/delete_user_data/abc")
    assert resp.status_code == 400
    service.delete_user.assert_not_awaited()


# ---------------------------------------------------------------- PUT
@pytest.mark.asyncio
async def test_update_user_echoes_body_with_path_id(client, service):
    body = {"id": 999, "name": "new", "email": "n@x.com", "password": "p", "role": "r", "about": "a"}
    resp = await client.put("/update_user_data/3", json=body)
    assert resp.status_code == 200
    assert resp.json() == {**body, "id": 3}
    service.update_user.assert_awaited_once()
    args = service.update_user.await_args.args
    assert args[0] == 3
    assert isinstance(args[1], User)
    assert args[1].name == "new"


@pytest.mark.asyncio
async def test_update_user_no_validation_blank_name(client, service):
    resp = await client.put("/update_user_data/2", json={"name": ""})
    assert resp.status_code == 200
    assert resp.json() == {
        "id": 2, "name": "", "email": None, "password": None, "role": None, "about": None
    }
    service.update_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_user_service_error_propagates(client, service):
    service.update_user.side_effect = UserNotFoundException("missing")
    resp = await client.put("/update_user_data/2", json={"name": "x"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_user_bad_id_returns_400(client, service):
    resp = await client.put("/update_user_data/xyz", json={"name": "x"})
    assert resp.status_code == 400
    service.update_user.assert_not_awaited()


# ---------------------------------------------------------------- GET by name
@pytest.mark.asyncio
async def test_get_user_by_name_found(client, service):
    u = _user(4, "carol")
    service.get_user_by_name.return_value = u
    resp = await client.get("/get_user_name/name/carol")
    assert resp.status_code == 200
    assert resp.json() == _as_json(u)
    service.get_user_by_name.assert_awaited_once_with("carol")


@pytest.mark.asyncio
async def test_get_user_by_name_not_found_empty_body(client, service):
    service.get_user_by_name.return_value = None
    resp = await client.get("/get_user_name/name/nobody")
    assert resp.status_code == 200
    assert resp.content == b""


@pytest.mark.asyncio
async def test_get_user_by_name_multiple_results_returns_500(client, service):
    service.get_user_by_name.side_effect = MultipleResultsFound("multiple")
    resp = await client.get("/get_user_name/name/dup")
    assert resp.status_code == 500