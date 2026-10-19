"""User REST endpoints (port of com.smartContact.Controller.UserController).

Spring's ``@RestController`` becomes an ``APIRouter`` with no prefix, so every
path stays exactly as it was in the source. Each handler only delegates to
:class:`app.services.user_service.UserService`, which is injected through
``Depends(get_user_service)`` instead of ``@Autowired`` field injection.

Wire contract:

* ``POST   /save_user_data``             -> 200 text/plain "User data saved successfully!"
* ``GET    /get_user_data``              -> 200 JSON array of users
* ``GET    /get_user_data/{id}``         -> 200 JSON user, or 404 ErrorMessage
* ``DELETE /delete_user_data/{id}``      -> 200 text/plain "user data deleted Successfully",
                                            or 500 if the id does not exist
* ``PUT    /update_user_data/{id}``      -> 200 JSON echo of the request body (path id applied)
* ``GET    /get_user_name/name/{name}``  -> 200 JSON user, or 200 with an EMPTY body

Validation failures, including a non-int path id, return 400 rather than 422
through the handlers in ``app/errors.py``.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, field_validator

from app.models.user import User
from app.services.user_service import UserService, get_user_service

__all__ = ["router", "UserIn", "UserCreate", "UserOut"]

logger = logging.getLogger(__name__)

router = APIRouter(tags=["users"])

_JAVA_INT_MIN = -(2**31)
_JAVA_INT_MAX = 2**31 - 1

# Path ids must fit in a Java ``int``. A non-numeric or out-of-range value
# raises a RequestValidationError, which app/errors.py turns into a 400.
UserId = Annotated[int, Path(alias="id", ge=_JAVA_INT_MIN, le=_JAVA_INT_MAX)]

SAVE_SUCCESS_MESSAGE = "User data saved successfully!"
DELETE_SUCCESS_MESSAGE = "user data deleted Successfully"
NAME_BLANK_MESSAGE = "please Add the department Name"


# --------------------------------------------------------------------------- #
# Schemas (the JSON shape Jackson read and wrote for com.smartContact.model.User)
# --------------------------------------------------------------------------- #
class UserIn(BaseModel):
    """Request body without Bean Validation. Used by PUT, where the source had no ``@Valid``.

    Jackson's defaults apply: missing fields become null, or 0 for ``int id``,
    and unknown properties are ignored.
    """

    model_config = ConfigDict(extra="ignore")

    id: int = 0
    name: str | None = None
    email: str | None = None
    password: str | None = None
    role: str | None = None
    about: str | None = None

    def to_entity(self) -> User:
        return User(
            self.id, self.name, self.email, self.password, self.role, self.about
        )


class UserCreate(UserIn):
    """Request body for POST. Ports ``@NotBlank(message = "please Add the department Name")``."""

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str | None) -> str | None:
        # @NotBlank rejects null, empty, and whitespace-only strings.
        if value is None or not value.strip():
            raise ValueError(NAME_BLANK_MESSAGE)
        return value


class UserOut(BaseModel):
    """Response body: every field of the entity, like Jackson serialising ``User``.

    MIGRATION_NOTE / SECURITY: as in the source, the plaintext password is
    returned to clients. Kept so the wire contract does not change; needs review.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None = None
    email: str | None = None
    password: str | None = None
    role: str | None = None
    about: str | None = None


ServiceDep = Annotated[UserService, Depends(get_user_service)]


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@router.post(
    "/save_user_data",
    response_class=PlainTextResponse,
    status_code=200,
)
async def save_user(
    user: Annotated[UserCreate, Body()], service: ServiceDep
) -> PlainTextResponse:
    """Validate and persist a user (merge semantics), then return a fixed message."""
    logger.info("inside the saveUser of UserController ")
    await service.save_user(user.to_entity())
    return PlainTextResponse(SAVE_SUCCESS_MESSAGE, status_code=200)


@router.get("/get_user_data", response_model=list[UserOut])
async def fetch_user_list(service: ServiceDep) -> list[UserOut]:
    """Return every user."""
    logger.info("inside the fetchUserList of UserController ")
    users = await service.fetch_user_list()
    return [UserOut.model_validate(u) for u in users]


@router.get("/get_user_data/{id}", response_model=UserOut)
async def fetch_user_by_id(user_id: UserId, service: ServiceDep) -> UserOut:
    """Return one user. ``UserNotFoundException`` becomes a 404 in app/errors.py."""
    user = await service.fetch_user_by_id(user_id)
    return UserOut.model_validate(user)


@router.delete(
    "/delete_user_data/{id}",
    response_class=PlainTextResponse,
    status_code=200,
)
async def delete_user(user_id: UserId, service: ServiceDep) -> PlainTextResponse:
    """Delete a user. A missing id raises ``UserDeleteError``, which becomes a 500 (source behaviour)."""
    await service.delete_user(user_id)
    return PlainTextResponse(DELETE_SUCCESS_MESSAGE, status_code=200)


@router.put("/update_user_data/{id}", response_model=UserOut)
async def update_user(
    user_id: UserId, user: Annotated[UserIn, Body()], service: ServiceDep
) -> UserOut:
    """Update the user with the path id and echo the request body.

    No NotBlank check applies here, because the source had no ``@Valid``.
    The service sets ``id`` on the object, so the echoed body carries the path
    id, as in the source, where Java mutated the same ``User`` instance.
    """
    updated = await service.update_user(user_id, user.to_entity())
    return UserOut.model_validate(updated)


@router.get("/get_user_name/name/{name}", response_model=None)
async def get_user_name_by_name(
    name: Annotated[str, Path()], service: ServiceDep
) -> UserOut | Response:
    """Look a user up by exact name.

    Spring returned 200 with an empty body when the handler returned ``null``.
    This is reproduced with an explicit empty ``Response`` (not JSON ``null``).
    Several matching rows raise ``MultipleResultsFound``, which becomes a 500.
    """
    user = await service.get_user_by_name(name)
    if user is None:
        return Response(status_code=200)
    return UserOut.model_validate(user)
