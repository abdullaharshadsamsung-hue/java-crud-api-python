"""User ORM entity (port of com.smartContact.model.User).

Maps to the table ``USER``. The table is created by ``app.db.init_db()``
(``Base.metadata.create_all``) at application startup, replacing Hibernate's
``ddl-auto``. Request/response validation (the source's ``@NotBlank``) lives in
the Pydantic schemas in ``app/schemas/user.py``, not here.
"""

from __future__ import annotations

from typing import Any, ClassVar

from sqlalchemy import Integer, String, event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm.mapper import Mapper

from app.db import Base

__all__ = ["User", "UserBuilder"]


class User(Base):
    """A smart-contact user.

    Lombok's ``@Data``/``@NoArgsConstructor``/``@AllArgsConstructor``/``@Builder``
    become: plain attribute access (accessors), a positional/keyword
    constructor, ``User.builder()``, value-based ``__eq__``/``__hash__`` and
    ``__repr__``.
    """

    # "USER" is a reserved word in PostgreSQL; SQLAlchemy quotes it (and the
    # mixed-case column names below) automatically, so the source's exact
    # identifiers are preserved.
    __tablename__ = "USER"

    # MIGRATION_NOTE: the source used GenerationType.AUTO (Hibernate
    # hibernate_sequence on MySQL). Here the PK is a PostgreSQL SERIAL column;
    # a legacy database needs a one-off migration of its id generator.
    id: Mapped[int] = mapped_column(
        "User_id", Integer, primary_key=True, autoincrement=True
    )
    name: Mapped[str | None] = mapped_column("User_name", String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(
        "User_Email", String(255), unique=True, nullable=True
    )
    # MIGRATION_NOTE / SECURITY: passwords are stored in plaintext, exactly as
    # in the source. Needs manual review (hash with passlib/bcrypt).
    password: Mapped[str | None] = mapped_column(
        "User_Password", String(255), nullable=True
    )
    role: Mapped[str | None] = mapped_column("User_Role", String(255), nullable=True)
    about: Mapped[str | None] = mapped_column("User_About", String(500), nullable=True)

    _FIELDS: ClassVar[tuple[str, ...]] = (
        "id",
        "name",
        "email",
        "password",
        "role",
        "about",
    )

    def __init__(
        self,
        id: int = 0,
        name: str | None = None,
        email: str | None = None,
        password: str | None = None,
        role: str | None = None,
        about: str | None = None,
    ) -> None:
        """No-args (all defaults: id 0, strings None) or all-args constructor,
        in the source field order: id, name, email, password, role, about."""
        super().__init__()
        self.id = id
        self.name = name
        self.email = email
        self.password = password
        self.role = role
        self.about = about

    @classmethod
    def builder(cls) -> UserBuilder:
        """Lombok ``User.builder()`` equivalent."""
        return UserBuilder()

    def _values(self) -> tuple[Any, ...]:
        return tuple(getattr(self, f) for f in self._FIELDS)

    def __eq__(self, other: object) -> bool:
        if self is other:
            return True
        if not isinstance(other, User):
            return NotImplemented
        return self._values() == other._values()

    def __hash__(self) -> int:
        # MIGRATION_NOTE: mirrors Lombok's @Data hashCode over mutable fields;
        # the hash changes if a field changes, so avoid using mutated
        # instances as dict keys / set members.
        return hash(self._values())

    def __repr__(self) -> str:
        return (
            f"User(id={self.id}, name={self.name}, email={self.email}, "
            f"password={self.password}, role={self.role}, about={self.about})"
        )

    __str__ = __repr__


class UserBuilder:
    """Fluent builder: ``User.builder().name("x").email("y").build()``."""

    def __init__(self) -> None:
        self._id: int = 0
        self._name: str | None = None
        self._email: str | None = None
        self._password: str | None = None
        self._role: str | None = None
        self._about: str | None = None

    def id(self, id: int) -> UserBuilder:
        self._id = id
        return self

    def name(self, name: str | None) -> UserBuilder:
        self._name = name
        return self

    def email(self, email: str | None) -> UserBuilder:
        self._email = email
        return self

    def password(self, password: str | None) -> UserBuilder:
        self._password = password
        return self

    def role(self, role: str | None) -> UserBuilder:
        self._role = role
        return self

    def about(self, about: str | None) -> UserBuilder:
        self._about = about
        return self

    def build(self) -> User:
        return User(
            self._id, self._name, self._email, self._password, self._role, self._about
        )

    def __repr__(self) -> str:
        return (
            f"User.UserBuilder(id={self._id}, name={self._name}, email={self._email}, "
            f"password={self._password}, role={self._role}, about={self._about})"
        )


@event.listens_for(User, "before_insert")
def _generate_id_when_unset(
    mapper: Mapper[Any], connection: Connection, target: User
) -> None:
    """Java's ``int id`` defaults to 0 and Hibernate treats 0 as "unsaved",
    generating a new id. Reproduce that: an id of 0 lets the SERIAL column
    assign the key instead of inserting a literal 0."""
    if target.id == 0:
        target.id = None  # type: ignore[assignment]
