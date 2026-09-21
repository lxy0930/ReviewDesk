# backend/dependencies.py（数据库部分）
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials  # 解析 Authorization: Bearer 头
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from jose import JWTError, jwt                       # python-jose：JWT 的编解码库
import os,sys
eduagents_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(eduagents_path)
import os,sys
sys.path.append(r"D:\job\PythonProjects\Multi-Agent")

from backend.config import get_settings

settings = get_settings()

# ── 创建异步引擎（连接池）──
engine = create_async_engine(
    settings.database_url,        # 来自 config.py，最终来自 .env.local
    pool_size=10,                 # 连接池基础大小
    max_overflow=20,              # 高峰时最多再额外开 20 个连接
    echo=False,                   # True 会打印所有 SQL，调试时可临时打开
)

# ── 会话工厂 ──
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：获取异步数据库会话，自动提交 / 回滚 / 关闭"""
    async with AsyncSessionLocal() as session:
        try:
            yield session            # 把会话交给接口使用（回顾 2.1.6 / 2.5）
            await session.commit()   # 接口正常结束 → 自动提交
        except Exception:
            await session.rollback() # 出错 → 自动回滚
            raise


# ── JWT 鉴权 ───────────────────────────────────────────────────
bearer_scheme = HTTPBearer()   # FastAPI 安全方案：自动从请求头解析 "Authorization: Bearer <token>"

async def get_current_user(
    # Depends(bearer_scheme)：FastAPI 自动取出 Bearer Token；没带或格式错会直接 401
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """FastAPI 依赖：验证 JWT Token，返回当前用户信息。
    返回 {"user_id": str, "role": str}；Token 无效则抛 401。"""
    # 预先准备好「401 凭证无效」异常，多处复用
    # print(f'credentials: {credentials}')
    # print(f'credentials.credentials: {credentials.credentials}')
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 用密钥和算法解码 Token；若签名不对/过期，会抛 JWTError
        payload = jwt.decode(
            credentials.credentials,            # 实际的 token 字符串
            settings.jwt_secret_key,            # 验签密钥（和签发时同一个）
            algorithms=[settings.jwt_algorithm],
        )
        user_id: str = payload.get("sub")                                  # 标准字段 sub = 用户ID
        role: str = payload.get("role", "student")                         # 角色
        if not user_id:                         # Token 里没有用户ID，视为无效
            raise credentials_exception

    except JWTError:                            # 解码失败（签名错/过期等）
        raise credentials_exception

    return {"user_id": user_id, "role": role}
if __name__ == '__main__':
    ...
    # test_get_db.py（项目根目录）
    import asyncio
    from sqlalchemy import text
    async def main():
        # 模拟 FastAPI 调用依赖：迭代一次拿到 session，跑一条查询
        async for db in get_db():
            r = await db.execute(text(
                "SELECT current_database(), "
                "count(*) FROM information_schema.tables WHERE table_schema = :s"
            ), {"s": "public"})
            row = r.fetchone()
            print("get_db 连到库:", row[0])
            print("public 下表数量:", row[1])


    asyncio.run(main())
    print("get_db 测试通过 ✅")
