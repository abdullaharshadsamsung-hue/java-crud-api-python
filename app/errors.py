"""Global exception handling (port of com.smartContact.error).

Covers ``UserNotFoundException`` and ``RestResponseEntityExceptionHandling``.
In Spring the latter is a ``@ControllerAdvice`` extending
``ResponseEntityExceptionHandler``. FastAPI has no advice classes, so it
becomes ``register_exception_handlers(app)``, called from the app factory.

Wire contract:

* ``UserNotFoundException`` returns 404 with an ``ErrorMessage`` body whose
  ``status`` is ``"NOT_FOUND"`` and whose ``message`` is the exception message.
  This is the only handler the Java class declares explicitly.
* Every other handler stands in for the defaults Spring gives through
  ``ResponseEntityExceptionHandler`` and the Boot error controller. These
  bodies use the project-wide shape ``{"error": str, "details": ...}``.
"""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, MultipleResultsFound
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.error import ErrorMessage

__all__ = [
    "UserNotFoundException",
    "UserDeleteError",
    "register_exception_handlers",
]

logger = logging.getLogger(__name__)


class UserNotFoundException(Exception):
    """Raised when a requested user does not exist.

    Mirrors the Java exception's constructor overloads: no args, a message,
    a message plus cause, or a cause alone. Arguments can be positional or
    keyword.
    """

    def __init__(
        self,
        message: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        if message is None and cause is not None:
            # Java's Throwable(Throwable cause) uses cause.toString() as the message.
            message = _describe_cause(cause)
        super().__init__(message)
        self.message: str | None = message
        if cause is not None:
            self.__cause__ = cause

    def __str__(self) -> str:
        return self.message or ""


class UserDeleteError(Exception):
    """Raised when deleting a user id that does not exist.

    Port of Spring's ``EmptyResultDataAccessException`` thrown by
    ``deleteById``. The source never handled it, so it surfaced as a 500.
    """

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        super().__init__(f"No User entity with id {user_id} exists!")


def _describe_cause(cause: BaseException | None) -> str | None:
    """Render an exception roughly like Java's ``Throwable.toString()``."""
    if cause is None:
        return None
    text = str(cause)
    name = type(cause).__name__
    return f"{name}: {text}" if text else name


def _error_body(status_code: int, details: Any) -> dict[str, Any]:
    """Build the project-wide ``{"error", "details"}`` body for *status_code*."""
    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        phrase = "Error"
    return {"error": phrase, "details": jsonable_encoder(details)}


async def _user_not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    """Port of ``userNotFoundException``: 404 with an ``ErrorMessage`` body."""
    message = exc.message if isinstance(exc, UserNotFoundException) else str(exc)
    error_message = ErrorMessage(status=HTTPStatus.NOT_FOUND, message=message)
    body: dict[str, Any] = error_message.model_dump(mode="json")
    # Make sure the project-wide keys are always present.
    body.setdefault("error", message)
    body.setdefault("details", None)
    return JSONResponse(status_code=HTTPStatus.NOT_FOUND, content=body)


async def _validation_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return 400 rather than FastAPI's default 422, matching Spring's status.

    Triggered by a blank name, malformed or missing JSON, or a non-int path id.
    """
    errors: list[dict[str, Any]] = []
    if isinstance(exc, RequestValidationError):
        errors = [
            {"loc": list(err.get("loc", ())), "msg": str(err.get("msg", ""))}
            for err in exc.errors()
        ]
    return JSONResponse(
        status_code=HTTPStatus.BAD_REQUEST,
        content=_error_body(HTTPStatus.BAD_REQUEST, errors),
    )


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Keep the HTTP status (for example 404 or 405) and use the shared body shape."""
    if not isinstance(exc, StarletteHTTPException):
        return await _unhandled_handler(request, exc)
    headers = getattr(exc, "headers", None)
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.status_code, exc.detail),
        headers=dict(headers) if headers else None,
    )


async def _integrity_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle a duplicate email or other constraint violation.

    Kept as 500 because that is what the source returned.

    MIGRATION_NOTE: Exception handlers cannot reach the request-scoped session,
    so the rollback must happen in ``app.db.get_db``, which should roll back
    whenever an exception propagates. Manual review: confirm ``get_db`` does
    this rollback.
    """
    logger.warning("Integrity error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        content=_error_body(HTTPStatus.INTERNAL_SERVER_ERROR, "Data integrity violation"),
    )


async def _delete_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle a delete of a missing id: 500 with "No User entity with id N exists!"."""
    return JSONResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        content=_error_body(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc)),
    )


async def _multiple_results_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle a single-result lookup (for example findByName) that matched several rows."""
    logger.warning("Multiple results on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        content=_error_body(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc)),
    )


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler: log the traceback and return 500 with no details."""
    logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc
    )
    return JSONResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        content=_error_body(HTTPStatus.INTERNAL_SERVER_ERROR, None),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Install every handler on *app*. Equivalent to the ``@ControllerAdvice`` class."""
    app.add_exception_handler(UserNotFoundException, _user_not_found_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(IntegrityError, _integrity_handler)
    app.add_exception_handler(UserDeleteError, _delete_error_handler)
    app.add_exception_handler(MultipleResultsFound, _multiple_results_handler)

    # The import is local to avoid a circular import, because the repository
    # layer may import exceptions from this module.
    try:
        from app.repositories.user_repository import EmptyResultError
    except ImportError:  # pragma: no cover - defensive
        logger.debug("EmptyResultError not available; skipping its handler")
    else:
        app.add_exception_handler(EmptyResultError, _delete_error_handler)

    app.add_exception_handler(Exception, _unhandled_handler)
