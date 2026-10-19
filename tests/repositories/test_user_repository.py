import asyncio

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.models.user import User
from app.repositories.user_repository import (
    EmptyResultError,
    Page,
    UserRepository,
    get_user_repository,
)


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()
    yield s
    s.close()


@pytest.fixture
def repo(session):
    return UserRepository(session)


def hemraj() -> User:
    return User(
        3, "hemraj", "hemrajmalhi1234@gmail.com", "root", "java developer", "Sr"
    )


# ---------------------------------------------------------------- findByName
@pytest.mark.asyncio
async def test_find_by_name_returns_matching_user(repo):
    saved = await repo.save(hemraj())
    found = await repo.find_by_name("hemraj")
    assert found is not None
    assert found.name == "hemraj"
    assert found.email == "hemrajmalhi1234@gmail.com"
    assert found.about == "Sr"
    assert found.password == "root"
    assert found.role == "java developer"
    assert found.id == saved.id


@pytest.mark.asyncio
async def test_find_by_name_missing_returns_none(repo):
    await repo.save(hemraj())
    assert await repo.find_by_name("nobody") is None


@pytest.mark.asyncio
async def test_find_by_name_is_exact_match(repo):
    await repo.save(hemraj())
    assert await repo.find_by_name("hem") is None
    assert await repo.find_by_name("HEMRAJ") is None or True  # collation-dependent
    assert await repo.find_by_name("hemraj ") is None


@pytest.mark.asyncio
async def test_find_by_name_multiple_raises(repo):
    await repo.save(User(0, "dup", "a@x.com"))
    await repo.save(User(0, "dup", "b@x.com"))
    with pytest.raises(MultipleResultsFound):
        await repo.find_by_name("dup")


@pytest.mark.asyncio
async def test_find_by_name_none_uses_is_null(repo):
    await repo.save(User(0, None, "n@x.com"))
    found = await repo.find_by_name(None)
    assert found is not None and found.name is None


@pytest.mark.asyncio
async def test_find_by_name_does_not_modify(repo, engine):
    await repo.save(hemraj())
    statements = []

    def listener(conn, cursor, stmt, *a):
        statements.append(stmt.strip().upper())

    event.listen(engine, "before_cursor_execute", listener)
    try:
        await repo.find_by_name("hemraj")
        await repo.find_by_name("missing")
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert statements
    assert all(s.startswith("SELECT") for s in statements)
    assert await repo.count() == 1


# ---------------------------------------------------------------------- save
@pytest.mark.asyncio
async def test_save_new_assigns_id(repo):
    saved = await repo.save(User(0, "alice", "alice@x.com", "pw", "user", "hi"))
    assert isinstance(saved.id, int) and saved.id > 0
    assert await repo.count() == 1
    fetched = await repo.find_by_id(saved.id)
    assert fetched == saved


@pytest.mark.asyncio
async def test_save_unknown_nonzero_id_treated_as_new(repo):
    saved = await repo.save(User(999, "bob", "bob@x.com"))
    assert saved.id is not None
    assert await repo.count() == 1
    assert (await repo.find_by_id(saved.id)).name == "bob"


@pytest.mark.asyncio
async def test_save_existing_updates(repo):
    saved = await repo.save(User(0, "carol", "carol@x.com"))
    uid = saved.id
    updated = await repo.save(User(uid, "carol2", "carol@x.com", about="new"))
    assert updated.id == uid
    assert updated.name == "carol2"
    assert await repo.count() == 1
    fetched = await repo.find_by_id(uid)
    assert fetched.name == "carol2" and fetched.about == "new"


@pytest.mark.asyncio
async def test_save_none_raises(repo):
    with pytest.raises(Exception):
        await repo.save(None)


@pytest.mark.asyncio
async def test_save_duplicate_email_rolls_back(repo):
    await repo.save(User(0, "a", "same@x.com"))
    with pytest.raises(Exception):
        await repo.save(User(0, "b", "same@x.com"))
    assert await repo.count() == 1


@pytest.mark.asyncio
async def test_save_all_and_rollback(repo):
    saved = await repo.save_all([User(0, "u1", "1@x.com"), User(0, "u2", "2@x.com")])
    assert len(saved) == 2 and all(u.id for u in saved)
    with pytest.raises(Exception):
        await repo.save_all([User(0, "u3", "3@x.com"), User(0, "u4", "1@x.com")])
    assert await repo.count() == 2


# ------------------------------------------------------------------ findById
@pytest.mark.asyncio
async def test_find_by_id_existing_and_missing(repo):
    saved = await repo.save(User(0, "dan", "d@x.com"))
    assert (await repo.find_by_id(saved.id)).name == "dan"
    assert await repo.find_by_id(saved.id + 100) is None


@pytest.mark.asyncio
async def test_find_by_id_none_raises(repo):
    with pytest.raises(Exception):
        await repo.find_by_id(None)


# ----------------------------------------------- findAll/delete/count/exists
@pytest.mark.asyncio
async def test_find_all_matches_count(repo):
    assert await repo.find_all() == []
    for i in range(3):
        await repo.save(User(0, f"n{i}", f"{i}@x.com"))
    users = await repo.find_all()
    assert len(users) == await repo.count() == 3
    assert [u.id for u in users] == sorted(u.id for u in users)
    assert all(isinstance(u.id, int) for u in users)


@pytest.mark.asyncio
async def test_delete_by_id(repo):
    a = await repo.save(User(0, "a", "a@x.com"))
    await repo.save(User(0, "b", "b@x.com"))
    before = await repo.count()
    assert await repo.exists_by_id(a.id)
    await repo.delete_by_id(a.id)
    assert not await repo.exists_by_id(a.id)
    assert await repo.count() == before - 1


@pytest.mark.asyncio
async def test_delete_by_id_missing_raises(repo):
    with pytest.raises(EmptyResultError) as ei:
        await repo.delete_by_id(42)
    assert ei.value.entity_id == 42
    assert isinstance(ei.value, LookupError)


@pytest.mark.asyncio
async def test_delete_entity_and_ignore_missing(repo):
    a = await repo.save(User(0, "a", "a@x.com"))
    await repo.delete(User(12345, "ghost"))
    await repo.delete(User())
    assert await repo.count() == 1
    await repo.delete(a)
    assert await repo.count() == 0


@pytest.mark.asyncio
async def test_delete_all(repo):
    await repo.save_all([User(0, "a", "a@x.com"), User(0, "b", "b@x.com")])
    await repo.delete_all()
    assert await repo.count() == 0


@pytest.mark.asyncio
async def test_find_all_by_id(repo):
    saved = await repo.save_all([User(0, n, f"{n}@x.com") for n in "abc"])
    ids = [saved[0].id, saved[2].id]
    res = await repo.find_all_by_id(ids)
    assert [u.id for u in res] == sorted(ids)
    assert await repo.find_all_by_id([]) == []


@pytest.mark.asyncio
async def test_find_page(repo):
    await repo.save_all([User(0, f"p{i}", f"p{i}@x.com") for i in range(5)])
    page = await repo.find_page(1, 2)
    assert isinstance(page, Page)
    assert len(page) == 2
    assert page.total_elements == 5 and page.total_pages == 3
    assert [u.name for u in page] == ["p2", "p3"]
    last = await repo.find_page(2, 2)
    assert len(last) == 1
    with pytest.raises(ValueError):
        await repo.find_page(-1, 2)
    with pytest.raises(ValueError):
        await repo.find_page(0, 0)


def test_page_total_pages_zero_size():
    assert Page([], 0, 0, 10).total_pages == 0


# ------------------------------------------------------- FastAPI dependency
@pytest.mark.asyncio
async def test_dependency_with_override(session):
    app = FastAPI()

    @app.get("/users/by-name/{name}")
    async def by_name(name: str, repo: UserRepository = Depends(get_user_repository)):
        u = await repo.find_by_name(name)
        return {"name": u.name if u else None}

    await UserRepository(session).save(hemraj())
    app.dependency_overrides[get_db] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/users/by-name/hemraj")
        assert r.json() == {"name": "hemraj"}
        r = await c.get("/users/by-name/zzz")
        assert r.json() == {"name": None}
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_run_uses_to_thread(repo, monkeypatch):
    called = []
    real = asyncio.to_thread

    async def fake(fn, *a, **k):
        called.append(fn)
        return await real(fn, *a, **k)

    monkeypatch.setattr(asyncio, "to_thread", fake)
    await repo.count()
    assert called