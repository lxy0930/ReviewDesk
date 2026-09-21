# backend/api/v1/unified_chat.py
# 统一 AI 助手入口：规则前置拦截 -> LLM 路由 -> 引导到已实现的 Exam / Resume Agent

import asyncio
import json
import re
from dataclasses import dataclass

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from langchain_core.messages import HumanMessage

from backend.core.llm_factory import get_llm
from backend.core.logger import get_logger
from backend.core.orchestrator import AgentType
from backend.dependencies import get_current_user

router = APIRouter()
logger = get_logger(__name__)


# ── 已实现 Agent 的中文名和跳转路径 ──────────────────────────────
_AGENT_DISPLAY = {
    "exam":   "试卷批改",
    "resume": "简历审查",
}

_GUIDANCE = {
    "exam": {
        "message": "检测到您需要进行试卷批改。请前往「试卷批改」页面上传 Word 格式答卷，AI 将自动完成三轨批改并分析知识薄弱点。",
        "action_label": "前往试卷批改",
        "action_url": "/exam",
    },
    "resume": {
        "message": "检测到您需要进行简历审查。请前往「简历审查」页面上传 PDF 格式简历，AI 将从六个维度进行评分并给出改进建议。",
        "action_label": "前往简历审查",
        "action_url": "/resume",
    },
}


# ── 去除末尾标点空白，用于关键词精确比对 ─────────────────────────
_STRIP_TAIL_RE = re.compile(r"[\s!！?？。~～,.，。]+$")

_HELLO_KEYWORDS = frozenset([
    "你好", "您好", "hi", "hello", "hey", "哈喽", "嗨",
    "在吗", "在不在", "在线吗", "有人吗",
])

_THANKS_KEYWORDS = frozenset([
    "谢谢", "感谢", "多谢", "谢了", "非常感谢", "万分感谢",
    "辛苦了", "辛苦", "麻烦了", "不好意思",
    "太棒了", "太好了", "厉害", "厉害了", "牛", "牛啊", "牛逼",
    "好的好的", "明白了", "懂了", "知道了", "收到",
])

_BYE_KEYWORDS = frozenset([
    "再见", "拜拜", "拜", "88", "886", "bye", "goodbye", "byebye",
    "下次见", "下次再聊", "先走了", "先撤了", "溜了", "闪了",
])

_IDENTITY_RE = re.compile(
    r"(你|您)(是谁|叫什么|的名字|是什么|是.*AI|是.*机器人|是.*助手)"
    r"|介绍.{0,4}(你自己|自己|一下)"
    r"|你是谁"
    r"|你叫(啥|什么名)",
    re.IGNORECASE,
)

_CAPABILITY_RE = re.compile(
    r"(你|您)(能|可以|会).{0,6}(做|帮|干)"
    r"|(你|您).{0,4}(功能|用途|能力|特点)"
    r"|怎么(用|使用)(你|您|这个)?"
    r"|(使用说明|帮助菜单|help|usage)"
    r"|你能帮(我|忙)吗",
    re.IGNORECASE,
)


_REPLY_HELLO = (
    "您好！我是 ReviewDesk AI 助手。\n\n"
    "目前我可以帮您：\n"
    "- **试卷批改**：告诉我「我要提交试卷」，AI 完成三轨批改和知识薄弱点分析\n"
    "- **简历审查**：告诉我「帮我看看简历」，AI 给出六维度评分与改进建议\n\n"
    "请问有什么可以帮到您？"
)

_REPLY_THANKS = (
    "不客气，很高兴能帮到您！\n\n"
    "如果还有其他问题，随时告诉我，我随时在线。"
)

_REPLY_BYE = (
    "再见！希望今天的学习对您有所帮助，期待下次与您交流。\n\n"
    "祝您学习顺利！"
)

_REPLY_IDENTITY = (
    "我是 **ReviewDesk AI 助手**，你的个人提效工作台。\n\n"
    "目前可以帮你处理两件事：\n"
    "- **试卷批改**：AI 三轨并行批改 + 知识薄弱点分析\n"
    "- **简历审查**：六维度质量评审，提供原文定位的修改建议\n\n"
    "有什么可以帮到您吗？"
)

_REPLY_CAPABILITY = (
    "我能为您提供以下功能：\n\n"
    "- 「提交试卷批改」 -> 上传 Word 答卷，AI 完成批改并分析薄弱点\n"
    "- 「审查我的简历」 -> 上传 PDF 简历，六维度评分 + 改进建议\n\n"
    "直接告诉我您的需求，我会自动路由到对应的 Agent。"
)


def _pre_filter(text: str) -> str | None:
    """规则前置拦截。命中常见社交/元场景时直接返回模板回复，不调用 LLM。"""
    t = text.strip()
    t_lower = _STRIP_TAIL_RE.sub("", t.lower())

    if t_lower in _HELLO_KEYWORDS:
        return _REPLY_HELLO
    if t_lower in _THANKS_KEYWORDS:
        return _REPLY_THANKS
    if t_lower in _BYE_KEYWORDS:
        return _REPLY_BYE
    if _IDENTITY_RE.search(t):
        return _REPLY_IDENTITY
    if _CAPABILITY_RE.search(t):
        return _REPLY_CAPABILITY

    return None


# ── LLM 路由 Prompt：把用户输入归到已实现的 2 类或 clarify ─────
_ROUTE_PROMPT = """判断用户需求应路由到哪个功能。

可选功能：
- exam        : 试卷/作业批改（需上传 Word 答卷，用户提到"批改""作业""提交试卷"等）
- resume      : 简历审查（需上传 PDF 简历，用户提到"简历""帮我看看简历"等）
- clarify     : 意图不明确，无法判断，需要追问

严格按以下 JSON 格式返回，不要有其他内容：
{{"label": "功能名", "reason": "一句话说明判断依据"}}

用户输入：{message}"""

_LABEL_TO_AGENT = {
    "exam":    AgentType.EXAM,
    "resume":  AgentType.RESUME,
    "clarify": None,
}
_VALID_LABELS = frozenset(_LABEL_TO_AGENT)


_REPLY_PROMPT = """你是 ReviewDesk 的 AI 助手，一个个人提效工作台。

请根据用户输入和识别到的意图，生成一段简洁、自然、有帮助的中文回复。

规则：
- 最多 3 句话，不要重复用户问题。
- 如果意图是试卷批改或简历审查，说明下一步要做什么，并引导用户前往对应页面。
- 如果意图不明确，提出一个具体澄清问题。
- 不要编造系统没有的功能。

用户输入：{message}
识别意图：{label}
判断依据：{reason}
"""


@dataclass
class _RouteResult:
    label:      str
    agent_type: AgentType | None
    confidence: float
    reason:     str


async def _llm_route(message: str) -> _RouteResult:
    """调用 LLM 判断用户输入应路由到 Exam、Resume 或 clarify。"""
    try:
        llm = get_llm("intent", temperature=0)
        resp = await llm.ainvoke([HumanMessage(content=_ROUTE_PROMPT.format(message=message))])
        raw = resp.text.strip()
        parsed = json.loads(raw)
        label = parsed.get("label", "clarify").strip().lower()
        reason = parsed.get("reason", "LLM 路由判断")

        if label not in _VALID_LABELS:
            logger.warning("unified_chat.llm_route_unknown_label", label=label, fallback="clarify")
            label = "clarify"

        logger.info("unified_chat.llm_route_result", label=label, reason=reason)
    except Exception as e:
        logger.warning("unified_chat.llm_route_failed", error=str(e), fallback="clarify")
        label = "clarify"
        reason = "路由判断异常，请描述得更具体一些"

    return _RouteResult(
        label=label,
        agent_type=_LABEL_TO_AGENT[label],
        confidence=0.85,
        reason=reason,
    )


class UnifiedChatRequest(BaseModel):
    session_id: str = Field(..., description="会话 ID")
    message:    str = Field(..., min_length=1, max_length=2000, description="用户输入")


def _sse(data: dict) -> dict:
    return {"data": json.dumps(data, ensure_ascii=False)}


async def _stream_text(text: str, chunk_size: int = 6):
    """把固定回复按小块拆成 SSE token 事件，模拟逐字流式输出。"""
    for index in range(0, len(text), chunk_size):
        chunk = text[index:index + chunk_size]
        if not chunk:
            continue
        yield _sse({"type": "token", "content": chunk})
        await asyncio.sleep(0.015)


async def _stream_llm_reply(message: str, label: str, reason: str):
    """调用 LLM 生成自然语言回复，并逐 token 返回文本。"""
    llm = get_llm("chat", temperature=0.3, streaming=True)
    prompt = _REPLY_PROMPT.format(
        message=message,
        label=label,
        reason=reason,
    )

    async for chunk in llm.astream([HumanMessage(content=prompt)]):
        content = getattr(chunk, "content", "")
        token = content if isinstance(content, str) else str(content)
        if token:
            for index in range(0, len(token), 4):
                piece = token[index:index + 4]
                if piece:
                    yield piece
                    await asyncio.sleep(0.01)


@router.post("/stream")
async def unified_chat_stream(
    req: UnifiedChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """统一 AI 助手流式接口（SSE），仅路由到已实现的 Exam / Resume Agent。"""

    async def event_generator():
        pre_reply = _pre_filter(req.message)
        if pre_reply is not None:
            async for event in _stream_text(pre_reply):
                yield event
            yield _sse({"type": "done"})
            return

        decision = await _llm_route(req.message)

        yield _sse({
            "type":          "routing_decision",
            "agent_type":    decision.agent_type.value if decision.agent_type else "",
            "agent_display": _AGENT_DISPLAY.get(decision.agent_type.value if decision.agent_type else "", ""),
            "confidence":    round(decision.confidence, 4),
            "reason":        decision.reason,
        })

        if decision.label in ("exam", "resume"):
            guidance = _GUIDANCE[decision.label]
            reply_parts: list[str] = []
            async for token in _stream_llm_reply(
                req.message,
                decision.label,
                decision.reason,
            ):
                reply_parts.append(token)
                yield _sse({"type": "token", "content": token})
            reply_text = "".join(reply_parts)
            yield _sse({
                "type":         "guidance",
                "message":      reply_text or guidance["message"],
                "action_label": guidance["action_label"],
                "action_url":   guidance["action_url"],
            })
        else:
            reply_parts = []
            async for token in _stream_llm_reply(
                req.message,
                decision.label,
                decision.reason,
            ):
                reply_parts.append(token)
                yield _sse({"type": "token", "content": token})
            reply_text = "".join(reply_parts)
            yield _sse({
                "type":         "guidance",
                "message":      reply_text,
                "action_label": "",
                "action_url":   "",
            })

        yield _sse({"type": "done"})

    return EventSourceResponse(event_generator())


if __name__ == "__main__":
    print(_pre_filter("你好."))
