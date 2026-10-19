import pytest
from sqlalchemy import Integer, String, UniqueConstraint, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base
from app.models.user import User, UserBuilder, _generate_id_when_unset


# ---------- constructors ----------

def test_no_args_constructor_defaults():
    u = User()
    assert u.id == 0
    assert u.name is None
    assert u.email is None
    assert u.password is None
    assert u.role is None
    assert u.about is None


def test_no_args_constructor_does_not_touch_db(monkeypatch):
    import sqlalchemy.engine

    def boom(*a, **k):
        raise AssertionError("DB touched")

    monkeypatch.setattr(sqlalchemy.engine.Engine, "connect", boom)
    User()
    User(1, "a", "b", "c", "d", "e")


def test_all_args_constructor_positional():
    u = User(5, "Alice", "a@x.com", "secret", "ROLE_USER", "hello")
    assert (u.id, u.name, u.email, u.password, u.role, u.about) == (
        5, "Alice", "a@x.com", "secret", "ROLE_USER", "hello"
    )


def test_all_args_constructor_keyword():
    u = User(id=7, name="B", email="b@x.com", password="p", role="r", about="ab")
    assert u.id == 7 and u.name == "B" and u.email == "b@x.com"
    assert u.password == "p" and u.role == "r" and u.about == "ab"


@pytest.mark.parametrize("val", [None, "", "   "])
def test_constructor_performs_no_validation(val):
    u = User(1, val, val, val, val, val)
    assert u.name == val and u.email == val and u.about == val


def test_constructor_accepts_long_about_without_validation():
    u = User(about="x" * 1000)
    assert len(u.about) == 1000


# ---------- builder ----------

def test_builder_returns_builder():
    assert isinstance(User.builder(), UserBuilder)


def test_builder_partial():
    u = User.builder().name("A").email("a@x.com").build()
    assert isinstance(u, User)
    assert u.name == "A" and u.email == "a@x.com"
    assert u.id == 0
    assert u.password is None and u.role is None and u.about is None


def test_builder_all_fields():
    u = (
        User.builder().id(3).name("n").email("e").password("p").role("r").about("a").build()
    )
    assert u == User(3, "n", "e", "p", "r", "a")


def test_builder_empty_build_equals_default():
    assert User.builder().build() == User()


def test_builder_methods_are_fluent():
    b = User.builder()
    for m, v in [("id", 1), ("name", "n"), ("email", "e"), ("password", "p"),
                 ("role", "r"), ("about", "a")]:
        assert getattr(b, m)(v) is b


def test_builder_repr():
    r = repr(User.builder().id(1).name("n"))
    assert r == "User.UserBuilder(id=1, name=n, email=None, password=None, role=None, about=None)"


# ---------- getters / setters ----------

FIELDS = {"id": 42, "name": "N", "email": "e@x", "password": "pw", "role": "admin", "about": "ab"}


@pytest.mark.parametrize("field,value", list(FIELDS.items()))
def test_setter_changes_only_its_field(field, value):
    u = User(1, "a", "b", "c", "d", "e")
    before = {f: getattr(u, f) for f in FIELDS}
    setattr(u, field, value)
    assert getattr(u, field) == value
    for f in FIELDS:
        if f != field:
            assert getattr(u, f) == before[f]


# ---------- equals / hash ----------

def test_equal_users_and_hash():
    a = User(1, "n", "e", "p", "r", "a")
    b = User(1, "n", "e", "p", "r", "a")
    assert a == b and b == a
    assert hash(a) == hash(b)


def test_equal_default_users():
    assert User() == User()
    assert hash(User()) == hash(User())


def test_reflexive():
    a = User(1, "n")
    assert a == a


@pytest.mark.parametrize("field,value", list(FIELDS.items()))
def test_any_field_difference_not_equal(field, value):
    a = User(1, "a", "b", "c", "d", "e")
    b = User(1, "a", "b", "c", "d", "e")
    setattr(b, field, value)
    assert a != b and b != a


@pytest.mark.parametrize("other", [None, "User()", 0, object()])
def test_not_equal_to_non_user(other):
    u = User()
    assert u != other
    assert not (u == other)
    assert u.__eq__(other) is NotImplemented


def test_usable_in_set():
    s = {User(1, "a"), User(1, "a"), User(2, "a")}
    assert len(s) == 2


# ---------- toString ----------

def test_repr_and_str():
    u = User(1, "n", "e@x", "secret", "r", "ab")
    expected = "User(id=1, name=n, email=e@x, password=secret, role=r, about=ab)"
    assert repr(u) == expected
    assert str(u) == expected
    assert "secret" in str(u)


def test_repr_defaults():
    assert repr(User()) == (
        "User(id=0, name=None, email=None, password=None, role=None, about=None)"
    )


# ---------- mapping metadata ----------

def test_table_and_columns():
    t = User.__table__
    assert t.name == "USER"
    assert set(t.c.keys()) == {
        "User_id", "User_name", "User_Email", "User_Password", "User_Role", "User_About"
    }
    assert isinstance(t.c.User_id.type, Integer)
    assert t.c.User_id.primary_key
    assert t.c.User_id.autoincrement is True
    assert t.c.User_About.type.length == 500
    assert isinstance(t.c.User_Email.type, String)


def test_email_unique():
    t = User.__table__
    unique = t.c.User_Email.unique or any(
        isinstance(c, UniqueConstraint) and "User_Email" in c.columns.keys()
        for c in t.constraints
    )
    assert unique


def test_only_name_like_fields_nullable():
    t = User.__table__
    for col in ("User_name", "User_Email", "User_Password", "User_Role", "User_About"):
        assert t.c[col].nullable


# ---------- before_insert hook ----------

def test_before_insert_hook_clears_zero_id():
    u = User()
    _generate_id_when_unset(None, None, u)
    assert u.id is None


def test_before_insert_hook_keeps_nonzero_id():
    u = User(9)
    _generate_id_when_unset(None, None, u)
    assert u.id == 9


# ---------- persistence (sqlite in-memory) ----------

@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    User.__table__.create(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


def test_persist_generates_id(session):
    u = User(name="a", email="a@x.com")
    session.add(u)
    session.commit()
    assert u.id is not None and u.id > 0
    u2 = User.builder().name("b").email("b@x.com").build()
    session.add(u2)
    session.commit()
    assert u2.id not in (0, None, u.id)


def test_persist_roundtrip(session):
    session.add(User(name="n", email="e@x", password="p", role="r", about="ab"))
    session.commit()
    session.expunge_all()
    got = session.query(User).one()
    assert (got.name, got.email, got.password, got.role, got.about) == (
        "n", "e@x", "p", "r", "ab"
    )


def test_duplicate_email_fails(session):
    session.add(User(name="a", email="dup@x.com"))
    session.commit()
    session.add(User(name="b", email="dup@x.com"))
    with pytest.raises(IntegrityError):
        session.commit()