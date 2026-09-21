# scripts/seed_data.py
# 执行：python scripts/seed_data.py
# 用途：灌入本地开发测试账号

import asyncio
import uuid
import os
import sys
import asyncpg                       # PostgreSQL 异步驱动（脚本直接用它，简单直接）
from passlib.context import CryptContext

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import get_settings
# 兼容性补丁：同 auth.py，让 passlib 能读到 bcrypt 版本
import bcrypt as _b, types as _t
if not hasattr(_b, "__about__"):
    _b.__about__ = _t.SimpleNamespace(__version__=getattr(_b, "__version__", "4.x"))

s = get_settings()
# 用环境变量拼出 asyncpg 的连接串（注意 asyncpg 用的是 postgresql:// 而非 +asyncpg）
DB_DSN = (
    f"postgresql://{s.db_user}:{s.db_password}"
    f"@{s.db_host}:{s.db_port}"
    f"/{s.db_name}"
)

print(f'DB_DSN: {DB_DSN}')
# print(DB_DSN)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def seed_users():
    """灌入 4 个测试账号（已存在则跳过）。"""
    conn = await asyncpg.connect(DB_DSN)             # 连接数据库
    print("✅ 数据库连接成功，开始灌入测试账号...")
    try:
        users = [
            {"username": "admin",     "email": "admin@eduagent.local",     "pwd": "Admin@123456",   "role": "admin"},
            {"username": "teacher01", "email": "teacher01@eduagent.local", "pwd": "Teacher@123456", "role": "teacher"},
            {"username": "student01", "email": "student01@eduagent.local", "pwd": "Student@123456", "role": "student"},
            {"username": "student02", "email": "student02@eduagent.local", "pwd": "Student@123456", "role": "student"},
            {"username": "student03", "email": "student03@eduagent.local", "pwd": "Student@123456", "role": "student"},
            {"username": "lxy",       "email": "lxy@eduagent.local",       "pwd": "123456",              "role": "teacher"},
        ]
        for u in users:
            await conn.execute(
                """
                INSERT INTO users (id, username, email, password_hash, role)
                SELECT $1::uuid, $2::varchar, $3::varchar, $4::varchar, $5::varchar
                WHERE NOT EXISTS (
                    SELECT 1 FROM users WHERE email = $3::varchar
                )
                """,
                str(uuid.uuid4()), u["username"], u["email"],
                pwd_context.hash(u["pwd"]),          # 存哈希，绝不存明文
                u["role"],
            )
        print(f"✅ 测试账号灌入完成（{len(users)} 个，已存在则跳过）：")
        print("   admin@eduagent.local      / Admin@123456")
        print("   teacher01@eduagent.local  / Teacher@123456")
        print("   student01@eduagent.local  / Student@123456")
        print("   student02@eduagent.local  / Student@123456")
        print("   student03@eduagent.local  / Student@123456")
        print("   lxy@eduagent.local        / 123456")
    finally:
        await conn.close()                           # 无论成败都关闭连接


if __name__ == "__main__":
    asyncio.run(seed_users())
    ...
