import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import MultipleResultsFound

from app.errors import UserDeleteError, UserNotFoundException
from app.models.user import User
from app.repositories.user_repository import EmptyResultError, UserRepository
from app.services.user_service import (
    USER_NOT_AVAILABLE_MESSAGE,
    UserService,
    get_user_service,
)


@pytest.fixture
def repo():
    return AsyncMock(spec=UserRepository)


@pytest.fixture
def service(repo):
    return UserService(repo)


def hemraj() -> User:
    return (
        User.builder()
        .name("hemraj")
        .email("hemrajmalhi1234@gmail.com")
        .about("Sr")
        .password("root")
        .role("java developer")
        .id(3)
        .build()
    )


# ---------------------------------------------------------- getUserByName (ported)
@pytest.mark.asyncio
async def test_get_user_by_name_found(service, repo):
    repo.find_by_name.return_value = hemraj()
    found = await service.get_user_by_name("hemraj")
    assert found is not None
    assert found.name == "hemraj"
    repo.find_by_name.assert_awaited_once_with("hemraj")


@pytest.mark.asyncio
async def test_get_user_by_name_not_found_returns_none(service, repo):
    repo.find_by_name.return_value = None
    assert await service.get_user_by_name("nobody") is None
    repo.find_by_name.assert_awaited_once_with("nobody")


@pytest.mark.asyncio
async def test_get_user_by_name_multiple_propagates(service, repo):
    repo.find_by_name.side_effect = MultipleResultsFound("2")
    with pytest.raises(MultipleResultsFound):
        await service.get_user_by_name("dup")


# ---------------------------------------------------------------- saveUser
@pytest.mark.asyncio
async def test_save_new_user_assigns_id(service, repo):
    new = User(name="a", email="a@x.com")
    saved = User(7, "a", "a@x.com")
    repo.save.return_value = saved
    result = await service.save_user(new)
    assert result is saved
    assert result.id == 7
    repo.save.assert_awaited_once_with(new)


@pytest.mark.asyncio
async def test_save_existing_user_returns_updated(service, repo, caplog):
    user = User(3, "new", None, None, None, None)
    repo.save.return_value = user
    with caplog.at_level(logging.DEBUG):
        result = await service.save_user(user)
    assert result == User(3, "new")
    assert result.email is None
    repo.save.assert_awaited_once_with(user)


# ---------------------------------------------------------------- fetchUserList
@pytest.mark.asyncio
async def test_fetch_user_list_returns_all(service, repo):
    users = [hemraj(), User(4, "b")]
    repo.find_all.return_value = users
    assert await service.fetch_user_list() == users
    repo.find_all.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_fetch_user_list_empty(service, repo):
    repo.find_all.return_value = []
    result = await service.fetch_user_list()
    assert result == []
    assert result is not None


# ---------------------------------------------------------------- fetchUserById
@pytest.mark.asyncio
async def test_fetch_user_by_id_found(service, repo):
    u = hemraj()
    repo.find_by_id.return_value = u
    assert await service.fetch_user_by_id(3) is u
    repo.find_by_id.assert_awaited_once_with(3)


@pytest.mark.asyncio
async def test_fetch_user_by_id_missing_raises(service, repo):
    repo.find_by_id.return_value = None
    with pytest.raises(UserNotFoundException) as ei:
        await service.fetch_user_by_id(99)
    assert str(ei.value) == "User are not available"
    assert ei.value.message == USER_NOT_AVAILABLE_MESSAGE


# ---------------------------------------------------------------- deleteUser
@pytest.mark.asyncio
async def test_delete_existing_then_fetch_raises(service, repo):
    repo.delete_by_id.return_value = None
    assert await service.delete_user(3) is None
    repo.delete_by_id.assert_awaited_once_with(3)
    repo.find_by_id.return_value = None
    with pytest.raises(UserNotFoundException):
        await service.fetch_user_by_id(3)


@pytest.mark.asyncio
async def test_delete_missing_raises_delete_error(service, repo):
    repo.delete_by_id.side_effect = EmptyResultError(42)
    with pytest.raises(UserDeleteError) as ei:
        await service.delete_user(42)
    assert ei.value.user_id == 42
    assert isinstance(ei.value.__cause__, EmptyResultError)
    assert str(ei.value) == "No User entity with id 42 exists!"


# ---------------------------------------------------------------- updateUser
@pytest.mark.asyncio
async def test_update_existing_overrides_id_and_saves(service, repo):
    user = User(999, "n", None, "p", None, None)
    repo.save.return_value = User(5, "n", None, "p")
    result = await service.update_user(5, user)
    assert user.id == 5
    assert result is user
    saved_arg = repo.save.await_args.args[0]
    assert saved_arg is user
    assert saved_arg.id == 5
    assert saved_arg.email is None


@pytest.mark.asyncio
async def test_update_missing_id_echoes_path_id(service, repo):
    user = User(0, "x")
    repo.save.return_value = User(77, "x")
    result = await service.update_user(10, user)
    assert result.id == 10
    repo.save.assert_awaited_once_with(user)


@pytest.mark.asyncio
async def test_update_none_user_raises(service, repo):
    with pytest.raises(AttributeError):
        await service.update_user(1, None)  # type: ignore[arg-type]
    repo.save.assert_not_awaited()


# ---------------------------------------------------------------- dependency
def test_get_user_service_wraps_repository():
    r = MagicMock(spec=UserRepository)
    svc = get_user_service(r)
    assert isinstance(svc, UserService)
    assert svc._repository is r