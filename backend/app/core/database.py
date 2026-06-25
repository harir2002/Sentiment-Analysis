from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    from app.models import db_models  # noqa: F401
    from sqlalchemy import inspect, text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def migrate(connection):
            inspector = inspect(connection)
            if not inspector.has_table("comparison_jobs"):
                return
            columns = {c["name"] for c in inspector.get_columns("comparison_jobs")}
            if "stt_language_code" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE comparison_jobs "
                        "ADD COLUMN stt_language_code VARCHAR(16)"
                    )
                )

        await conn.run_sync(migrate)
