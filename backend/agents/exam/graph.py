# backend/agents/exam/graph.py

from langgraph.graph import StateGraph, START, END

from backend.agents.exam.state import ExamState
from backend.agents.exam.nodes import (
    parse_word_node,
    load_questions_meta_node,
    run_three_tracks_node,
    aggregate_results_node,
    analyze_weak_points_node,
    notify_teacher_node,
    teacher_review_node,
    apply_teacher_decision_node,
    publish_results_node,
)
from backend.core.checkpoint import get_postgres_checkpointer


def build_exam_graph(checkpointer=None):
    """
    构建并编译试卷批改 Agent 的 LangGraph 状态图。

    执行链路（线性）：
        parse_word → load_questions_meta → run_three_tracks
        → aggregate_results → analyze_weak_points
        → notify_teacher → teacher_review [interrupt]
        → apply_teacher_decision → publish_results → END
    """
    builder = StateGraph(ExamState)

    # ── 注册节点 ──────────────────────────────────────────────
    builder.add_node("parse_word",             parse_word_node)
    builder.add_node("load_questions_meta",    load_questions_meta_node)
    builder.add_node("run_three_tracks",       run_three_tracks_node)
    builder.add_node("aggregate_results",      aggregate_results_node)
    builder.add_node("analyze_weak_points",    analyze_weak_points_node)
    builder.add_node("notify_teacher",         notify_teacher_node)
    builder.add_node("teacher_review",         teacher_review_node)
    builder.add_node("apply_teacher_decision", apply_teacher_decision_node)
    builder.add_node("publish_results",        publish_results_node)

    # ── 固定边（线性链）──────────────────────────────────────
    builder.add_edge(START,                    "parse_word")
    builder.add_edge("parse_word",             "load_questions_meta")
    builder.add_edge("load_questions_meta",    "run_three_tracks")
    builder.add_edge("run_three_tracks",       "aggregate_results")
    builder.add_edge("aggregate_results",      "analyze_weak_points")
    builder.add_edge("analyze_weak_points",    "notify_teacher")
    builder.add_edge("notify_teacher",         "teacher_review")
    builder.add_edge("teacher_review",         "apply_teacher_decision")
    builder.add_edge("apply_teacher_decision", "publish_results")
    builder.add_edge("publish_results",        END)

    # ── 编译，绑定 PostgreSQL 持久化 checkpointer ─────────────
    if checkpointer is None:
        checkpointer = get_postgres_checkpointer()
    return builder.compile(checkpointer=checkpointer)
