# backend/main.py

import os
import sys
import asyncio

# Windows conda 专用：把 base 的 Library/bin 加入 DLL 搜索路径，
# 让 _lzma.pyd 能找到 liblzma.dll（非 Windows 跳过，不影响 Linux/Mac）
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    _conda_base_lib_bin = os.path.normpath(
        os.path.join(os.path.dirname(sys.executable), "..", "..", "Library", "bin")
    )
    if os.path.isdir(_conda_base_lib_bin):
        os.add_dll_directory(_conda_base_lib_bin)

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings                          # 配置（第 3 章）
from backend.core.logger import configure_logging, get_logger    # 日志（3.3）
from backend.api.router import api_router                        # 8.6.1 聚合的总路由

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()                                  # 初始化结构化日志（3.3）
    logger = get_logger(__name__)
    logger.info("app.starting | env=%s port=%s", settings.app_env, settings.app_port)

    # ① DB Schema 自动迁移（幂等，每次启动执行）—— 第 3 章的建表/迁移
    try:
        from backend.db.migrations import run_migrations
        await run_migrations()
    except Exception as e:
        logger.warning("app.migrations_failed | error=%s", e)   # 迁移失败只告警，不拦启动

    # ② 初始化 PostgreSQL LangGraph checkpointer
    from backend.core.checkpoint import (
        init_postgres_checkpointer,
        close_postgres_checkpointer,
    )
    await init_postgres_checkpointer()

    # ③ 应用运行期间停在这里
    logger.info("app.started")
    yield

    # ── 关闭时执行 ──
    logger.info("app.shutting_down")
    from backend.core.llm_factory import LLMFactory      # LLM 工厂（3.4）
    LLMFactory.clear_cache()                            # 清缓存
    await close_postgres_checkpointer()
    logger.info("app.shutdown_complete")

app = FastAPI(
    title="ReviewDesk API",
    description="个人提效工作台 API：试卷批改与简历审查",
    version="1.0.0",
    docs_url="/docs",                                    # Swagger 文档
    redoc_url="/redoc",                                  # ReDoc 文档
    lifespan=lifespan,                                   # 挂上面的生命周期钩子
)

# CORS：允许前端开发端口跨域访问（3000/3001/5173/8080）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://localhost:3001", "http://localhost:5173", "http://localhost:8080",
        "http://localhost:5174",
        "http://127.0.0.1:3000", "http://127.0.0.1:3001", "http://127.0.0.1:5173", "http://127.0.0.1:8080",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")        # 挂总路由（8.6.1），所有业务接口在 /api/v1 下


@app.get("/health", tags=["系统"])                       # 健康检查（运维探活用）
async def health_check():
    return {"status": "ok", "env": settings.app_env}
