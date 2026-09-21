import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DB_URL = "postgresql+asyncpg://eduagent_user:123456@localhost:5433/eduagent"

async def check_postgres():
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        r = await conn.execute(text("SELECT 1"))
        print("✅ PostgreSQL 连通：", r.scalar())
    await engine.dispose()

async def main():
    await check_postgres()

asyncio.run(main())
