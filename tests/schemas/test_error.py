"""Tests for app.schemas.error (port of com.smartContact.model.ErrorMessage)."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.schemas.error import ErrorMessage, ErrorResponse


# ---------------------------------------------------------------------------
# No-args constructor
# ---------------------------------------------------------------------------


def test_no_args_constructor_fields_default_to_none():
    em = ErrorMessage()
    assert em.status is None
    assert em.message is None


# ---------------------------------------------------------------------------
# All-args constructor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [HTTPStatus.NOT_FOUND, 404, "NOT_FOUND", "not_found", "404"])
def test_all_args_constructor_not_found(status):
    em = ErrorMessage(status=status, message="Contact not found")
    assert em.status == "NOT_FOUND"
    assert em.message == "Contact not found"


def test_all_args_constructor_nulls():
    em = ErrorMessage(status=None, message=None)
    assert em.status is None
    assert em.message is None


def test_all_args_constructor_empty_message_unchanged():
    em = ErrorMessage(status=HTTPStatus.NOT_FOUND, message="")
    assert em.message == ""


def test_constructor_keyword_names_status_then_message():
    assert list(ErrorMessage.model_fields) == ["status", "message"]


@pytest.mark.parametrize("bad", [999, "NOPE", True, 4.04, object()])
def test_invalid_status_rejected(bad):
    with pytest.raises(ValidationError):
        ErrorMessage(status=bad, message="x")


# ---------------------------------------------------------------------------
# status getter/setter
# ---------------------------------------------------------------------------


def test_set_status_bad_request():
    em = ErrorMessage(status=HTTPStatus.NOT_FOUND, message="m")
    em.status = HTTPStatus.BAD_REQUEST
    assert em.status == "BAD_REQUEST"
    assert em.message == "m"


def test_set_status_none():
    em = ErrorMessage(status=HTTPStatus.NOT_FOUND, message="m")
    em.status = None
    assert em.status is None
    assert em.message == "m"


def test_set_status_invalid_raises_on_assignment():
    em = ErrorMessage()
    with pytest.raises(ValidationError):
        em.status = 12345


# ---------------------------------------------------------------------------
# message getter/setter
# ---------------------------------------------------------------------------


def test_set_message():
    em = ErrorMessage(status=HTTPStatus.NOT_FOUND, message="old")
    em.message = "Invalid input"
    assert em.message == "Invalid input"
    assert em.status == "NOT_FOUND"


def test_set_message_none():
    em = ErrorMessage(status=HTTPStatus.NOT_FOUND, message="old")
    em.message = None
    assert em.message is None
    assert em.status == "NOT_FOUND"


# ---------------------------------------------------------------------------
# equality
# ---------------------------------------------------------------------------


def test_equal_same_values():
    a = ErrorMessage(status=HTTPStatus.NOT_FOUND, message="x")
    b = ErrorMessage(status=404, message="x")
    c = ErrorMessage(status="NOT_FOUND", message="x")
    assert a == a
    assert a == b and b == a
    assert b == c and a == c


def test_not_equal_different_status_or_message():
    base = ErrorMessage(status=HTTPStatus.NOT_FOUND, message="x")
    assert base != ErrorMessage(status=HTTPStatus.BAD_REQUEST, message="x")
    assert base != ErrorMessage(status=HTTPStatus.NOT_FOUND, message="y")


def test_equal_both_null():
    assert ErrorMessage() == ErrorMessage(status=None, message=None)


@pytest.mark.parametrize("other", [None, "x", 1, object()])
def test_not_equal_to_none_or_other_type(other):
    assert (ErrorMessage() == other) is False


def test_dump_stable_and_equal_for_equal_objects():
    a = ErrorMessage(status=HTTPStatus.NOT_FOUND, message="x")
    b = ErrorMessage(status=404, message="x")
    assert a.model_dump() == b.model_dump()
    assert a.model_dump() == a.model_dump()


# ---------------------------------------------------------------------------
# repr / toString
# ---------------------------------------------------------------------------


def test_repr_contains_class_and_fields():
    r = repr(ErrorMessage(status=HTTPStatus.NOT_FOUND, message="x"))
    assert "ErrorMessage" in r
    assert "status=" in r and "NOT_FOUND" in r
    assert "message=" in r and "'x'" in r


def test_repr_null_fields():
    r = repr(ErrorMessage())
    assert r == "ErrorMessage(status=None, message=None)"


# ---------------------------------------------------------------------------
# serialization / deserialization
# ---------------------------------------------------------------------------


def test_json_serialization_uses_enum_name():
    em = ErrorMessage(status=HTTPStatus.NOT_FOUND, message="Contact not found")
    assert em.model_dump(mode="json") == {"status": "NOT_FOUND", "message": "Contact not found"}


def test_json_serialization_nulls():
    assert ErrorMessage().model_dump(mode="json") == {"status": None, "message": None}


def test_json_deserialization():
    em = ErrorMessage.model_validate_json('{"status": "NOT_FOUND", "message": "m"}')
    assert em == ErrorMessage(status=HTTPStatus.NOT_FOUND, message="m")


def test_json_deserialization_empty_object():
    assert ErrorMessage.model_validate_json("{}") == ErrorMessage()


# ---------------------------------------------------------------------------
# ErrorResponse
# ---------------------------------------------------------------------------


def test_error_response_drops_unset_extras():
    assert ErrorResponse(error="boom").model_dump() == {"error": "boom", "details": None}


def test_error_response_includes_extras_when_set():
    r = ErrorResponse(error="e", details={"a": 1}, status=404, message="m")
    assert r.model_dump(mode="json") == {
        "error": "e",
        "details": {"a": 1},
        "status": "NOT_FOUND",
        "message": "m",
    }


def test_error_response_requires_error():
    with pytest.raises(ValidationError):
        ErrorResponse()


def test_error_response_invalid_status():
    with pytest.raises(ValidationError):
        ErrorResponse(error="e", status="BOGUS")


# ---------------------------------------------------------------------------
# HTTP round-trip
# ---------------------------------------------------------------------------


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.get("/missing")
    async def missing():
        em = ErrorMessage(status=HTTPStatus.NOT_FOUND, message="Contact not found")
        return JSONResponse(status_code=404, content=em.model_dump(mode="json"))

    @app.get("/err")
    async def err():
        return JSONResponse(status_code=400, content=ErrorResponse(error="bad").model_dump(mode="json"))

    return app


@pytest.mark.asyncio
async def test_http_error_message_body(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/missing")
    assert resp.status_code == 404
    assert resp.json() == {"status": "NOT_FOUND", "message": "Contact not found"}
    assert ErrorMessage.model_validate(resp.json()).status == "NOT_FOUND"


@pytest.mark.asyncio
async def test_http_error_response_body(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/err")
    assert resp.status_code == 400
    assert resp.json() == {"error": "bad", "details": None}