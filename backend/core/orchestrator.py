# backend/core/orchestrator.py
# Orchestrator：统一管理 Agent 图实例，并提供 Agent 执行入口。

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from backend.core.logger import get_logger
from backend.core.retry import with_retry

logger = get_logger(__name__)


class AgentType(str, Enum):
    """已接入的 Agent 类型。"""

    EXAM = "exam"
    RESUME = "resume"


class Orchestrator:
    """Agent 编排服务。

    当前职责：
        - 按 AgentType 懒加载 LangGraph 图。
        - 缓存已编译的图实例，避免重复初始化。
        - 提供统一的 graph.ainvoke 执行入口。

    API 层负责构造各自的 initial_state，Orchestrator 不关心具体业务 State 结构。
    """

    def __init__(self) -> None:
        self._agent_graphs: dict[AgentType, Any] = {}
        logger.info("orchestrator.initialized")

    def get_graph(self, agent_type: AgentType) -> Any:
        """按 AgentType 获取编译后的 LangGraph 图，并缓存实例。"""
        if agent_type not in self._agent_graphs:
            if agent_type == AgentType.EXAM:
                from backend.agents.exam.graph import build_exam_graph
                from backend.core.checkpoint import get_postgres_checkpointer

                self._agent_graphs[agent_type] = build_exam_graph(
                    get_postgres_checkpointer()
                )

            elif agent_type == AgentType.RESUME:
                from backend.agents.resume.graph import build_resume_graph

                self._agent_graphs[agent_type] = build_resume_graph()

            else:
                raise ValueError(f"未知 AgentType: {agent_type}")

            logger.info(
                "orchestrator.agent_graph_loaded",
                agent_type=agent_type.value,
            )

        return self._agent_graphs[agent_type]

    async def run(
        self,
        agent_type: AgentType,
        payload: Any,
        config: Optional[dict[str, Any]] = None,
        enable_retry: bool = True,
        allow_fallback: bool = False,
    ) -> Any:
        """统一执行 Agent 图。

        payload 可以是 initial_state，也可以是 Command(resume=...)，由调用方决定。
        """
        graph = self.get_graph(agent_type)
        logger.info(
            "orchestrator.run_start",
            agent_type=agent_type.value,
            has_config=config is not None,
        )
        if not enable_retry:
            return await graph.ainvoke(payload, config=config)

        @with_retry(
            agent_type=agent_type.value,
            allow_fallback=allow_fallback,
        )
        async def _invoke():
            return await graph.ainvoke(payload, config=config)

        return await _invoke()


_orchestrator_instance: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    """获取 Orchestrator 模块级单例。"""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = Orchestrator()
    return _orchestrator_instance
