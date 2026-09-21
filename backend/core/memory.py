# backend/core/memory.py

from typing import Optional
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from backend.core.logger import get_logger

logger = get_logger(__name__)

# 每个 Agent 独立的 MemorySaver 实例
# 不同 Agent 的 State schema 不同，共用同一个 MemorySaver 会导致
# msgpack 序列化时 schema 字段冲突，必须隔离
_memory_savers: dict[str, MemorySaver] = {}


def get_memory_saver(agent_type: str = "default") -> MemorySaver:
    """
    获取指定 Agent 类型的 MemorySaver 单例。

    本地阶段使用内存存储（进程重启后历史丢失）。
    生产阶段替换为 AsyncPostgresSaver 即可持久化，业务代码无需修改。

    Args:
        agent_type: Agent 标识符，如 "exam" / "resume"

    Returns:
        MemorySaver 实例，传给 StateGraph.compile(checkpointer=...)
    """
    if agent_type not in _memory_savers:
        _memory_savers[agent_type] = MemorySaver()
        logger.info("memory.saver_initialized", agent=agent_type)
    return _memory_savers[agent_type]


def build_thread_id(student_id: str, session_id: str) -> str:
    """
    构建 LangGraph Checkpointer 使用的 thread_id。

    格式：student_{student_id}_session_{session_id}
    同一学员的不同会话有独立的历史，互不干扰。

    Example:
        build_thread_id("abc123", "xyz789")
        → "student_abc123_session_xyz789"
    """
    return f"student_{student_id}_session_{session_id}"


def build_config(student_id: str, session_id: str) -> dict:
    """
    构建 LangGraph 调用所需的 config 字典。

    用法：
        config = build_config(student_id, session_id)
        result = await graph.ainvoke(state, config=config)

    Returns:
        {"configurable": {"thread_id": "student_xxx_session_yyy"}}
    """
    return {
        "configurable": {
            "thread_id": build_thread_id(student_id, session_id),
        }
    }


def trim_messages_to_window(
    messages: list[BaseMessage],
    window_size: int = 10,
) -> list[BaseMessage]:
    """
    滑动窗口裁剪：保留最近 window_size 轮对话。
    SystemMessage 始终保留在最前，不受 window_size 限制。

    Args:
        messages:    当前完整消息列表
        window_size: 保留的对话轮数（1轮 = 1 Human + 1 AI），默认 10 轮

    Returns:
        裁剪后的消息列表
    """
    system_messages  = [m for m in messages if isinstance(m, SystemMessage)]
    # print(f'system_messages: {system_messages}')
    dialogue_messages = [m for m in messages if not isinstance(m, SystemMessage)]
    # print(f'dialogue_messages: {dialogue_messages}')
    max_dialogue_messages = window_size * 2   # 1轮 = 2条消息

    if len(dialogue_messages) <= max_dialogue_messages:
        return messages   # 未超出窗口，不裁剪

    trimmed = dialogue_messages[-max_dialogue_messages:]

    logger.info(
        "memory.window_trimmed",
        original=len(dialogue_messages),
        kept=len(trimmed),
        window_size=window_size,
    )

    return system_messages + trimmed

def should_trigger_summary(
    messages: list[BaseMessage],
    threshold: int = 10,
) -> bool:
    """
    判断对话轮数是否超过阈值，决定是否触发摘要压缩。

    Args:
        messages:  当前消息列表
        threshold: 触发压缩的轮数阈值，默认 10 轮

    Returns:
        True → 需要压缩
    """
    dialogue_count = sum(1 for m in messages if isinstance(m, (HumanMessage, AIMessage)))
    # print(f'dialogue_count: {dialogue_count}')
    # rounds = dialogue_count // 2 # 每轮2条
    #
    return dialogue_count % ( threshold * 2 ) == 0 # 每轮 2 条，dialogue_count / 2 = 实际轮数

async def compress_to_summary(
    messages: list[BaseMessage],
    existing_summary: Optional[str] = None,
) -> str:
    """
    将历史对话压缩为结构化学员画像摘要。

    增量压缩：传入 existing_summary 防止已记录内容被重复写入。

    Args:
        messages:         待压缩的历史消息列表
        existing_summary: 上次的摘要（可选）

    Returns:
        压缩后的摘要文本
    """
    from langchain_core.messages import HumanMessage as LCHuman
    from backend.core.llm_factory import get_llm

    SUMMARY_PROMPT = """请将以下学员对话压缩为结构化学员画像摘要。

【压缩规则】
必须保留：学员明确不理解的知识点 / 反复出现的薄弱点 / 项目背景新增信息
选择性保留：已掌握知识点（简短标注）/ 学习进度信息
可以丢弃：已在上次摘要记录的内容 / 闲聊 / 已解决且理解的问题

【上一次摘要】
{previous_summary}

【本次新增对话】
{new_conversations}

请直接输出摘要文本，不要加任何前缀。"""

    conversation_text = "\n".join([
        f"{'学员' if isinstance(m, HumanMessage) else 'AI'}：{m.text if hasattr(m, 'text') and not callable(m.text) else str(m.content)}"
        for m in messages
        if isinstance(m, (HumanMessage, AIMessage))
    ])

    prompt_text = SUMMARY_PROMPT.format(
        previous_summary=existing_summary or "（无上次摘要）",
        new_conversations=conversation_text,
    )

    llm = get_llm("summarize")
    response = await llm.ainvoke([LCHuman(content=prompt_text)])
    summary = (
        response.content if isinstance(response.content, str)
        else str(response.content)
    ).strip()

    logger.info(
        "memory.summary_generated",
        input_messages=len(messages),
        summary_length=len(summary),
    )
    return summary

if __name__ == '__main__':
    # print(build_config(student_id="abc123", session_id="xyz789"))
    # print(get_memory_saver(agent_type="exam"))
    # ── 测试 2：滑动窗口裁剪 ─────────────────────────────────────
    messages = [SystemMessage(content="你是教学助手")]
    print(messages[0].text)
    print(messages[0].content)
    for i in range(1, 7):  # 模拟 6 轮对话
        messages.append(HumanMessage(content=f"问题{i}"))
        messages.append(AIMessage(content=f"回答{i}"))
    # # print(f'messages: {messages}')
    # # trimmed = trim_messages_to_window(messages, window_size=3)
    # # print(f'trimmed: {trimmed}')
    # print(should_trigger_summary(messages, threshold=10))

    import asyncio
    async def main():
        if should_trigger_summary(messages, threshold=3):
            summary = await compress_to_summary(messages)
            print(f'summary:{summary}')
    asyncio.run(main())
