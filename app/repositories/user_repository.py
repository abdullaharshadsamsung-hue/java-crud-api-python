"""User repository (port of com.smartContact.repository.UserDao).

Spring Data generated a proxy implementing ``JpaRepository<User, Integer>``
plus the derived query ``findByName``. Here the same contract is an explicit
class over a SQLAlchemy ``Session``. The scaffold's ``app.db`` exposes a
*synchronous* engine/session, so every public method is ``async`` and runs the
blocking ORM work in a worker thread (``asyncio.to_thread``) to keep the event
loop free. A session is only ever used by one operation at a time (each call
is awaited before the next), which is the thread-safety contract SQLAlchemy
sessions require.

MIGRATION_NOTE: the agreed plan mentions an ``AsyncSession``; the already
migrated ``app/db.py`` provides a sync ``Session``/``get_db``. This file
follows the real scaffold. If ``app/db.py`` is moved to ``AsyncSession``,
replace ``_run`` with direct ``await session.execute(...)`` calls.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import TypeVar

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.exc import MultipleResultsFound, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User

__all__ = [
    "EmptyResultError",
    "Page",
    "UserRepository",
    "get_user_repository",
]

_T = TypeVar("_T")


class EmptyResultError(LookupError):
    """Port of Spring's ``EmptyResultDataAccessException``.

    Raised by :meth:`UserRepository.delete_by_id` when no row has the id,
    matching Spring Data 2.x ``SimpleJpaRepository.deleteById``.
    """

    def __init__(self, entity_id: int) -> None:
        super().__init__(f"No class com.smartContact.model.User entity with id {entity_id} exists!")
        self.entity_id = entity_id


class Page:
    """Minimal equivalent of Spring Data's ``Page<User>``."""

    def __init__(self, content: list[User], page: int, size: int, total: int) -> None:
        self.content = content
        self.page = page
        self.size = size
        self.total_elements = total

    @property
    def total_pages(self) -> int:
        return 0 if self.size <= 0 else -(-self.total_elements // self.size)

    def __iter__(self) -> Iterator[User]:
        return iter(self.content)

    def __len__(self) -> int:
        return len(self.content)


class UserRepository:
    """CRUD + paging for :class:`User`, keyed by its integer id."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------ infra
    async def _run(self, fn: Callable[[], _T]) -> _T:
        return await asyncio.to_thread(fn)

    def _commit(self) -> None:
        """Commit the implicit transaction; roll back on any DB failure.

        Replaces ``@Transactional`` on ``SimpleJpaRepository`` write methods.
        """
        try:
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise

    # ---------------------------------------------------------- derived query
    async def find_by_name(self, name: str | None) -> User | None:
        """``findByName``: the single User whose name equals ``name`` exactly.

        Returns ``None`` when no row matches (the Java method returned null).
        Raises :class:`sqlalchemy.exc.MultipleResultsFound` when more than one
        row matches (Spring raised ``IncorrectResultSizeDataAccessException``).
        A ``None`` name is translated to ``IS NULL`` like Spring Data does.
        """

        def work() -> User | None:
            condition = User.name.is_(None) if name is None else User.name == name
            rows: Sequence[User] = self._session.scalars(
                select(User).where(condition)
            ).all()
            if not rows:
                return None
            if len(rows) > 1:
                raise MultipleResultsFound(
                    f"query did not return a unique result: {len(rows)}"
                )
            return rows[0]

        return await self._run(work)

    # ------------------------------------------------------------------ reads
    async def find_all(self) -> list[User]:
        """``findAll()`` — every user, ordered by id for deterministic output."""
        return await self._run(
            lambda: list(self._session.scalars(select(User).order_by(User.id)).all())
        )

    async def find_all_by_id(self, ids: Iterable[int]) -> list[User]:
        """``findAllById``."""
        id_list = list(ids)
        if not id_list:
            return []
        return await self._run(
            lambda: list(
                self._session.scalars(
                    select(User).where(User.id.in_(id_list)).order_by(User.id)
                ).all()
            )
        )

    async def find_page(self, page: int, size: int) -> Page:
        """``findAll(Pageable)`` — zero-based ``page`` of ``size`` users."""
        if page < 0:
            raise ValueError("Page index must not be less than zero")
        if size < 1:
            raise ValueError("Page size must not be less than one")

        def work() -> Page:
            total = self._session.scalar(select(func.count()).select_from(User)) or 0
            content = list(
                self._session.scalars(
                    select(User).order_by(User.id).offset(page * size).limit(size)
                ).all()
            )
            return Page(content, page, size, total)

        return await self._run(work)

    async def find_by_id(self, user_id: int) -> User | None:
        """``findById`` — ``None`` replaces ``Optional.empty()``."""
        if user_id is None:
            # Spring Data: "The given id must not be null!"
            raise ValueError("The given id must not be null!")
        return await self._run(lambda: self._session.get(User, user_id))

    async def exists_by_id(self, user_id: int) -> bool:
        return await self.find_by_id(user_id) is not None

    async def count(self) -> int:
        return await self._run(
            lambda: int(self._session.scalar(select(func.count()).select_from(User)) or 0)
        )

    # ----------------------------------------------------------------- writes
    def _save_one(self, user: User) -> User:
        """JPA ``save`` semantics: persist when new, merge otherwise.

        ``id == 0`` (Java's int default) means "new": the database assigns the
        key. A non-zero id that does not exist is also treated as new, as
        Hibernate's merge of a detached entity with a generated id would do —
        this keeps the SERIAL sequence from being bypassed by explicit ids.
        """
        if user.id and self._session.get(User, user.id) is None:
            user = User(0, user.name, user.email, user.password, user.role, user.about)
        managed = self._session.merge(user)
        self._session.flush()
        return managed

    async def save(self, user: User) -> User:
        """Insert or update ``user``; returns the managed, refreshed instance."""

        def work() -> User:
            try:
                managed = self._save_one(user)
            except SQLAlchemyError:
                self._session.rollback()
                raise
            self._commit()
            self._session.refresh(managed)
            return managed

        return await self._run(work)

    async def save_all(self, users: Iterable[User]) -> list[User]:
        """``saveAll`` — all-or-nothing in one transaction."""
        batch = list(users)

        def work() -> list[User]:
            try:
                saved = [self._save_one(u) for u in batch]
            except SQLAlchemyError:
                self._session.rollback()
                raise
            self._commit()
            for u in saved:
                self._session.refresh(u)
            return saved

        return await self._run(work)

    async def delete_by_id(self, user_id: int) -> None:
        """``deleteById`` — raises :class:`EmptyResultError` if absent."""

        def work() -> None:
            existing = self._session.get(User, user_id)
            if existing is None:
                raise EmptyResultError(user_id)
            self._session.delete(existing)
            self._commit()

        await self._run(work)

    async def delete(self, user: User) -> None:
        """``delete(entity)`` — silently ignores a user that is not stored."""

        def work() -> None:
            existing = self._session.get(User, user.id) if user.id else None
            if existing is None:
                return
            self._session.delete(existing)
            self._commit()

        await self._run(work)

    async def delete_all(self) -> None:
        """``deleteAll`` — removes every user in one transaction."""

        def work() -> None:
            for u in self._session.scalars(select(User)).all():
                self._session.delete(u)
            self._commit()

        await self._run(work)


def get_user_repository(session: Session = Depends(get_db)) -> UserRepository:
    """FastAPI dependency replacing Spring's ``@Autowired UserDao``."""
    return UserRepository(session)
