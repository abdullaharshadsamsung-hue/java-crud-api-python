"""User service (port of com.smartContact.service.UserService / UserServiceImp).

The Java interface + ``@Service`` implementation pair collapses into a single
concrete :class:`UserService` class. Spring's ``@Autowired UserDao`` field
injection becomes constructor injection, wired by the FastAPI dependency
:func:`get_user_service`.
"""

from __future__ import annotations

import logging

from fastapi import Depends

from app.errors import UserDeleteError, UserNotFoundException
from app.models.user import User
from app.repositories.user_repository import (
    EmptyResultError,
    UserRepository,
    get_user_repository,
)

__all__ = ["UserService", "get_user_service"]

logger = logging.getLogger(__name__)

USER_NOT_AVAILABLE_MESSAGE = "User are not available"


class UserService:
    """CRUD operations for :class:`User`, delegating to :class:`UserRepository`.

    As in the source there is no service-level transaction: each repository
    call commits on its own (Spring Data's per-method ``@Transactional``).
    """

    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    async def save_user(self, user: User) -> User:
        """Insert or update ``user`` with JPA ``save`` (persist/merge) semantics.

        * ``id == 0`` -> insert with a generated id.
        * ``id != 0`` and the row exists -> overwrite every column (nulls included).
        * ``id != 0`` and the row is missing -> insert with a generated id.

        The semantics are implemented in ``UserRepository.save``.
        """
        saved = await self._repository.save(user)
        logger.debug("Saved user id=%s", saved.id)
        return saved

    async def fetch_user_list(self) -> list[User]:
        """Return every stored user."""
        return await self._repository.find_all()

    async def fetch_user_by_id(self, user_id: int) -> User:
        """Return the user with ``user_id``.

        Raises:
            UserNotFoundException: if no such user exists (mapped to 404).
        """
        user = await self._repository.find_by_id(user_id)
        if user is None:
            logger.info("User id=%s not found", user_id)
            raise UserNotFoundException(USER_NOT_AVAILABLE_MESSAGE)
        return user

    async def delete_user(self, user_id: int) -> None:
        """Delete the user with ``user_id``.

        Raises:
            UserDeleteError: if no such user exists. Spring Data's ``deleteById``
                threw ``EmptyResultDataAccessException`` here, which the source
                never handled, so it is mapped to 500.
        """
        try:
            await self._repository.delete_by_id(user_id)
        except EmptyResultError as exc:
            logger.info("Delete of missing user id=%s", user_id)
            raise UserDeleteError(user_id) from exc

    async def update_user(self, user_id: int, user: User) -> User:
        """Set ``user_id`` on ``user`` and save it, replacing the stored fields.

        Returns the supplied object with the path id echoed. This holds even when
        no row had that id and the repository inserted it under a new generated
        id, matching the source, which ignored the result of ``save``.
        (The Java method returned ``void``; returning the object lets the router
        echo it.)
        """
        user.id = user_id
        await self._repository.save(user)
        return user

    async def get_user_by_name(self, name: str) -> User | None:
        """Return the single user whose name is exactly ``name``, or ``None``.

        If more than one row matches, ``sqlalchemy.exc.MultipleResultsFound``
        propagates (mapped to 500 in ``app/errors.py``).
        """
        return await self._repository.find_by_name(name)


def get_user_service(
    repository: UserRepository = Depends(get_user_repository),
) -> UserService:
    """FastAPI dependency replacing the Spring ``@Service`` singleton bean."""
    return UserService(repository)
