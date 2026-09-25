"""DeepSeek structured-output demonstration.

Usage:
    python scripts/deepseek_structured_output_demo.py success
    python scripts/deepseek_structured_output_demo.py failure
    python scripts/deepseek_structured_output_demo.py invalid

The failure mode deliberately disables tool calling with ``tool_choice='none'``
and then runs LangChain's tools parser. This demonstrates what happens when a
model does not return the structured tool call expected by the parser.
"""

import asyncio
import os
import sys
import traceback

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers.openai_tools import PydanticToolsParser
from pydantic import BaseModel, Field

from backend.core.llm_factory import get_llm


class CandidateProfile(BaseModel):
    """Small schema used only for this demonstration."""

    name: str = Field(description="候选人姓名")
    years_of_experience: int = Field(description="工作或项目经验年数")
    primary_skill: str = Field(description="最主要的技能")


async def run_success_example() -> None:
    """Normal path: let LangChain bind the schema as a function tool."""
    llm = get_llm("resume", temperature=0)
    structured_llm = llm.with_structured_output(
        CandidateProfile,
        method="function_calling",
    )

    result = await structured_llm.ainvoke(
        [
            SystemMessage(content="请从用户文本中提取候选人信息。"),
            HumanMessage(
                content=(
                    "候选人张三有 3 年 Python 后端开发经验，"
                    "目前主要做 FastAPI 和 PostgreSQL 项目。"
                )
            ),
        ]
    )

    print("结构化输出成功：")
    print(type(result).__name__)
    print(result.model_dump())


async def run_failure_example() -> None:
    """Failure path: force a plain text response with no tool call.

    ``with_structured_output`` normally binds the schema as a tool. Here we
    bind the same tool but set ``tool_choice='none'``, so the model can return
    plain text while the parser still expects a structured tool call.
    """
    llm = get_llm("resume", temperature=0)
    model_without_tool_call = llm.bind_tools(
        [CandidateProfile],
        tool_choice="none",
    )

    raw_message = await model_without_tool_call.ainvoke(
        [
            SystemMessage(
                content="不要调用任何工具，不要输出 JSON，只返回普通文本。"
            ),
            HumanMessage(content="请只回复一句：我不会调用工具。"),
        ]
    )

    print("DeepSeek 原始返回：")
    print("content =", repr(raw_message.content))
    print("tool_calls =", getattr(raw_message, "tool_calls", None))

    parser = PydanticToolsParser(
        tools=[CandidateProfile],
        first_tool_only=True,
    )

    try:
        parsed = await parser.ainvoke(raw_message)
        print("\n解析结果：", parsed)
        if parsed is None:
            print(
                "没有抛出异常。当前 LangChain 版本会把缺失的结构化输出"
                "解析为 None。"
            )
    except Exception as exc:
        print("\n结构化解析失败：")
        print("异常类型：", type(exc).__module__ + "." + type(exc).__name__)
        print("异常消息：", str(exc))
        print("\n完整异常：")
        traceback.print_exc()


async def run_invalid_schema_example() -> None:
    """Show the error raised when tool-call arguments violate Pydantic schema."""
    parser = PydanticToolsParser(
        tools=[CandidateProfile],
        first_tool_only=True,
    )

    invalid_message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "CandidateProfile",
                "args": {
                    "name": "张三",
                    # years_of_experience 和 primary_skill 故意缺失
                },
                "id": "invalid-tool-call",
                "type": "tool_call",
            }
        ],
    )

    try:
        parsed = await parser.ainvoke(invalid_message)
        print("解析成功：", parsed)
    except Exception as exc:
        print("结构字段不完整时抛出的异常：")
        print("异常类型：", type(exc).__module__ + "." + type(exc).__name__)
        print("异常消息：", str(exc))
        print("\n完整异常：")
        traceback.print_exc()


async def main(mode: str) -> None:
    if mode == "success":
        await run_success_example()
        return

    if mode == "failure":
        await run_failure_example()
        return

    if mode == "invalid":
        await run_invalid_schema_example()
        return

    raise SystemExit("mode 只能是 success、failure 或 invalid")


if __name__ == "__main__":
    selected_mode = sys.argv[1] if len(sys.argv) > 1 else "success"
    asyncio.run(main(selected_mode))
