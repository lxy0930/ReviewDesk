# backend/core/checkpoint.py
# PostgreSQL LangGraph checkpointer 生命周期管理。

from __future__ import annotations

import asyncio
import sys
from typing import Optional

import psycopg
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from backend.config import get_settings
from backend.core.logger import get_logger

logger = get_logger(__name__)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

_connection: Optional[psycopg.AsyncConnection] = None
_checkpointer: Optional[AsyncPostgresSaver] = None


def _postgres_dsn() -> str:
    settings = get_settings()
    return (
        f"postgresql://{settings.db_user}:{settings.db_password}"
        f"@{settings.db_host}:{settings.db_port}/{settings.db_name}"
    )


async def init_postgres_checkpointer() -> AsyncPostgresSaver:
    """连接 PostgreSQL，创建 checkpoint 表并返回全局 checkpointer。"""
    global _connection, _checkpointer

    if _checkpointer is not None:
        return _checkpointer

    if sys.platform == "win32":
        running_loop = asyncio.get_running_loop()
        if isinstance(running_loop, asyncio.ProactorEventLoop):
            raise RuntimeError(
                "PostgreSQL checkpointer 需要 SelectorEventLoop。"
                "请使用 `python run_backend.py` 启动后端，"
                "不要直接使用 `uvicorn backend.main:app`。"
            )

    _connection = await psycopg.AsyncConnection.connect(
        _postgres_dsn(),
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
    )
    _checkpointer = AsyncPostgresSaver(_connection)
    await _checkpointer.setup()

    logger.info("checkpoint.postgres_initialized")
    return _checkpointer


def get_postgres_checkpointer() -> AsyncPostgresSaver:
    """获取已初始化的 PostgreSQL checkpointer。"""
    if _checkpointer is None:
        raise RuntimeError("PostgreSQL checkpointer 尚未初始化")
    return _checkpointer


async def close_postgres_checkpointer() -> None:
    """关闭 PostgreSQL checkpoint 连接。"""
    global _connection, _checkpointer

    if _connection is not None:
        await _connection.close()
        logger.info("checkpoint.postgres_closed")

    _connection = None
    _checkpointer = None
