"""ReviewDesk backend launcher.

On Windows, psycopg's async connection requires SelectorEventLoop.
This launcher sets the policy before Uvicorn creates its event loop.
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
