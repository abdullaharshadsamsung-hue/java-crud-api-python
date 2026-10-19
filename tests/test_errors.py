import traceback

import pytest

from app.errors import UserNotFoundException


def test_no_args():
    e = UserNotFoundException()
    assert e.message is None
    assert e.cause is None
    assert e.__cause__ is None
    assert str(e) == ""
    assert e.args == ()


def test_stack_trace_captured_when_raised():
    try:
        raise UserNotFoundException("x")
    except UserNotFoundException as e:
        assert e.__traceback__ is not None
        assert traceback.extract_tb(e.__traceback__)


def test_message_only():
    e = UserNotFoundException("User not found")
    assert e.message == "User not found"
    assert e.cause is None
    assert str(e) == "User not found"
    assert e.args == ("User not found",)


def test_null_message():
    e = UserNotFoundException(None)
    assert e.message is None
    assert e.cause is None


def test_message_and_cause():
    cause = ValueError("boom")
    e = UserNotFoundException("missing", cause)
    assert e.message == "missing"
    assert e.cause is cause
    assert e.__cause__ is cause


def test_message_and_null_cause():
    e = UserNotFoundException("missing", None)
    assert e.message == "missing"
    assert e.cause is None


def test_message_and_cause_keyword():
    cause = KeyError("k")
    e = UserNotFoundException("missing", cause=cause)
    assert e.message == "missing"
    assert e.cause is cause


def test_cause_only_derives_message():
    cause = ValueError("boom")
    e = UserNotFoundException(cause)
    assert e.cause is cause
    assert e.message == "ValueError: boom"
    assert str(e) == "ValueError: boom"


def test_cause_without_text_uses_class_name():
    cause = RuntimeError()
    e = UserNotFoundException(cause)
    assert e.message == "RuntimeError"


def test_from_cause():
    cause = LookupError("nope")
    e = UserNotFoundException.from_cause(cause)
    assert isinstance(e, UserNotFoundException)
    assert e.cause is cause
    assert e.message == "LookupError: nope"


def test_null_cause_overload():
    e = UserNotFoundException(None, None)
    assert e.cause is None
    assert e.message is None


def test_cause_given_twice_raises():
    with pytest.raises(TypeError):
        UserNotFoundException(ValueError("a"), ValueError("b"))


def test_flags_default_true():
    e = UserNotFoundException("m")
    assert e.enable_suppression is True
    assert e.writable_stack_trace is True


@pytest.mark.parametrize("sup,wst", [(False, True), (True, False), (False, False), (True, True)])
def test_four_arg_flags_store_message_and_cause(sup, wst):
    cause = ValueError("c")
    e = UserNotFoundException("m", cause, enable_suppression=sup, writable_stack_trace=wst)
    assert e.enable_suppression is sup
    assert e.writable_stack_trace is wst
    assert e.message == "m"
    assert e.cause is cause


def test_flags_are_keyword_only():
    with pytest.raises(TypeError):
        UserNotFoundException("m", None, False, False)  # type: ignore[misc]


def test_both_flags_true_like_message_cause():
    cause = ValueError("c")
    a = UserNotFoundException("m", cause, enable_suppression=True, writable_stack_trace=True)
    b = UserNotFoundException("m", cause)
    assert (a.message, a.cause, str(a)) == (b.message, b.cause, str(b))


def test_hierarchy_and_identity():
    e = UserNotFoundException()
    assert isinstance(e, Exception)
    assert isinstance(e, BaseException)
    assert not isinstance(e, RuntimeError)
    assert UserNotFoundException.__name__ == "UserNotFoundException"
    assert UserNotFoundException.__module__ == "app.errors"


def test_raise_from_chain():
    cause = ValueError("root")
    with pytest.raises(UserNotFoundException) as info:
        raise UserNotFoundException("wrapped", cause)
    assert info.value.__cause__ is cause
    assert "root" in "".join(traceback.format_exception(info.value))


def test_no_side_effects(monkeypatch, capsys, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    UserNotFoundException("m", ValueError("x"))
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""
    assert caplog.records == []


def test_no_http_mapping_on_class():
    assert not hasattr(UserNotFoundException, "status_code")


@pytest.mark.asyncio
async def test_unmapped_in_app_falls_to_generic_handler():
    import httpx
    from app.main import create_app

    app = create_app()

    @app.get("/boom")
    async def boom():
        raise UserNotFoundException("User not found")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/boom")
    assert r.status_code == 500
    assert r.json()["details"] == "User not found"