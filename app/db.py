"""Database engine, sessions and schema creation.

Models subclass Base; init_db() creates their tables when the app starts.
"""

import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.sqlalchemy_url, pool_pre_ping=True) if settings.database_url else None
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False) if engine else None


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


async def init_db() -> None:
    if engine is not None:
        await asyncio.to_thread(Base.metadata.create_all, engine)
