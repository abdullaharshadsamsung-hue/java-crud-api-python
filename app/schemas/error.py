"""Error response payloads.

Port of ``com.smartContact.model.ErrorMessage`` plus the project-wide
``ErrorResponse`` shape (``{"error": str, "details": ...}``).
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_serializer
from pydantic_core.core_schema import SerializerFunctionWrapHandler

__all__ = ["ErrorMessage", "ErrorResponse"]


def _status_name(value: object) -> str | None:
    """Normalise a status to Spring's ``HttpStatus`` enum name (e.g. ``"NOT_FOUND"``).

    Jackson serialises Spring's ``HttpStatus`` by its enum constant name, so the
    wire value is the name, not the numeric code. Accepts ``http.HTTPStatus``,
    an ``int`` code, a name string, or ``None``.
    """
    if value is None:
        return None
    if isinstance(value, HTTPStatus):
        return value.name
    if isinstance(value, bool):
        raise ValueError("status must be an HTTP status, not a bool")
    if isinstance(value, int):
        try:
            return HTTPStatus(value).name
        except ValueError as exc:
            raise ValueError(f"unknown HTTP status code: {value}") from exc
    if isinstance(value, str):
        name = value.strip().upper()
        if name.isdigit():
            return _status_name(int(name))
        if name not in HTTPStatus.__members__:
            raise ValueError(f"unknown HTTP status name: {value!r}")
        return name
    raise ValueError(f"unsupported status type: {type(value).__name__}")


class ErrorMessage(BaseModel):
    """Error body returned for domain errors (e.g. 404 user not found).

    Lombok ``@Data``/``@NoArgsConstructor``/``@AllArgsConstructor`` map onto
    Pydantic: ``ErrorMessage()`` leaves both fields unset (``None``),
    ``ErrorMessage(status=..., message=...)`` sets both, attributes are
    readable/assignable (validated on assignment), and ``==``/``repr`` are
    value-based over ``status`` and ``message``.

    MIGRATION_NOTE: Spring's ``HttpStatus`` enum is represented as its constant
    name string (``"NOT_FOUND"``), matching Jackson's JSON output.
    ``http.HTTPStatus`` members and int codes are accepted and normalised.
    Note: Python's ``HTTPStatus`` names differ from Spring's for a few codes
    (e.g. 413 ``REQUEST_ENTITY_TOO_LARGE`` vs Spring ``PAYLOAD_TOO_LARGE``);
    the only status used by this project is 404 ``NOT_FOUND``, which matches.
    """

    model_config = ConfigDict(validate_assignment=True)

    status: str | None = None
    message: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _normalise_status(cls, value: object) -> str | None:
        return _status_name(value)


class ErrorResponse(BaseModel):
    """Project-wide error shape: ``{"error": str, "details": ...}``.

    ``status`` and ``message`` are optional extras omitted from the JSON body
    when unset, so bodies stay compatible with the ``ErrorMessage`` contract.
    """

    model_config = ConfigDict(validate_assignment=True)

    error: str
    details: Any = None
    status: str | None = None
    message: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _normalise_status(cls, value: object) -> str | None:
        return _status_name(value)

    @model_serializer(mode="wrap")
    def _drop_unset_extras(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for key in ("status", "message"):
            if key in data and data[key] is None:
                del data[key]
        return data
