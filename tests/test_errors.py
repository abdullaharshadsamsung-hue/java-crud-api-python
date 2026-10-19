import logging

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, MultipleResultsFound

from app.errors import (
    UserDeleteError,
    UserNotFoundException,
    _describe_cause,
    _error_body,
    register_exception_handlers,
)


class SubUserNotFound(UserNotFoundException):
    pass


class Payload(BaseModel):
    name: str


def build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/notfound")
    async def notfound():
        raise UserNotFoundException("User not found with id 5")

    @app.get("/notfound-none")
    async def notfound_none():
        raise UserNotFoundException()

    @app.get("/notfound-empty")
    async def notfound_empty():
        raise UserNotFoundException("")

    @app.get("/notfound-sub")
    async def notfound_sub():
        raise SubUserNotFound("sub message")

    @app.get("/notfound-cause")
    async def notfound_cause():
        raise UserNotFoundException(cause=ValueError("bad"))

    @app.get("/items/{item_id}")
    async def item(item_id: int):
        return {"id": item_id}

    @app.post("/users")
    async def create(p: Payload):
        return p

    @app.get("/integrity")
    async def integrity():
        raise IntegrityError("stmt", {}, Exception("dup"))

    @app.get("/delete")
    async def delete():
        raise UserDeleteError(7)

    @app.get("/multi")
    async def multi():
        raise MultipleResultsFound("many rows")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret")

    return app


@pytest_asyncio.fixture
async def client():
    app = build_app()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_user_not_found_message(client):
    r = await client.get("/notfound")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert body["status"] == "NOT_FOUND"
    assert body["message"] == "User not found with id 5"


@pytest.mark.asyncio
async def test_user_not_found_null_message(client):
    r = await client.get("/notfound-none")
    assert r.status_code == 404
    body = r.json()
    assert body["status"] == "NOT_FOUND"
    assert body.get("message") is None


@pytest.mark.asyncio
async def test_user_not_found_empty_message(client):
    r = await client.get("/notfound-empty")
    assert r.status_code == 404
    body = r.json()
    assert body["status"] == "NOT_FOUND"
    assert body["message"] == ""


@pytest.mark.asyncio
async def test_user_not_found_subclass(client):
    r = await client.get("/notfound-sub")
    assert r.status_code == 404
    assert r.json()["status"] == "NOT_FOUND"
    assert r.json()["message"] == "sub message"


@pytest.mark.asyncio
async def test_user_not_found_cause_only(client):
    r = await client.get("/notfound-cause")
    assert r.status_code == 404
    assert r.json()["message"] == "ValueError: bad"


@pytest.mark.asyncio
async def test_validation_bad_path_returns_400(client):
    r = await client.get("/items/abc")
    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "Bad Request"
    assert isinstance(body["details"], list) and body["details"]


@pytest.mark.asyncio
async def test_validation_malformed_body_400(client):
    r = await client.post("/users", content="{bad", headers={"content-type": "application/json"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_validation_missing_field_400(client):
    r = await client.post("/users", json={})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_unknown_route_404_shared_shape(client):
    r = await client.get("/nope")
    assert r.status_code == 404
    assert r.json() == {"error": "Not Found", "details": "Not Found"}


@pytest.mark.asyncio
async def test_method_not_allowed_405(client):
    r = await client.delete("/notfound")
    assert r.status_code == 405
    assert r.json()["error"] == "Method Not Allowed"


@pytest.mark.asyncio
async def test_integrity_error_500(client):
    r = await client.get("/integrity")
    assert r.status_code == 500
    assert r.json() == {"error": "Internal Server Error", "details": "Data integrity violation"}


@pytest.mark.asyncio
async def test_delete_error_500(client):
    r = await client.get("/delete")
    assert r.status_code == 500
    assert r.json()["details"] == "No User entity with id 7 exists!"


@pytest.mark.asyncio
async def test_multiple_results_500(client):
    r = await client.get("/multi")
    assert r.status_code == 500
    assert "many rows" in r.json()["details"]


@pytest.mark.asyncio
async def test_unhandled_500_no_details(client, caplog):
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        r = await client.get("/boom")
    assert r.status_code == 500
    assert r.json() == {"error": "Internal Server Error", "details": None}
    assert "secret" not in r.text


def test_exception_constructors():
    assert str(UserNotFoundException()) == ""
    assert UserNotFoundException("m").message == "m"
    cause = KeyError("k")
    e = UserNotFoundException("m", cause)
    assert e.__cause__ is cause and e.message == "m"
    assert UserNotFoundException(cause=RuntimeError()).message == "RuntimeError"
    assert UserDeleteError(3).user_id == 3


def test_helpers():
    assert _describe_cause(None) is None
    assert _error_body(999, {"a": 1}) == {"error": "Error", "details": {"a": 1}}
    assert _error_body(404, None)["error"] == "Not Found"