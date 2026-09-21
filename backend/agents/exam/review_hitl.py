import asyncio
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command # 恢复运行
from backend.agents.exam.state import ExamState
from backend.agents.exam.nodes import teacher_review_node

# 公共基础 state（teacher_review_node 用到的所有字段）
BASE_STATE = {
    "submission_id": "sub-test-001",
    "student_id": "stu-test-001",
    "pre_review_summary": {
        "by_question": [
            {"question_id": "q-001", "score": 7, "comment": "基本正确"},
            {"question_id": "q-002", "score": 5, "comment": "答案不完整"},
        ],
        "total_score": 12,
    },
    "weak_points": ["递归算法", "时间复杂度分析"],
    "weak_points_summary": "学员对递归理解薄弱，建议补充练习",
}


def _build_review_graph():
    """构造只含 teacher_review_node 的最小测试图"""
    builder = StateGraph(ExamState)
    builder.add_node("teacher_review", teacher_review_node)
    builder.add_edge(START, "teacher_review")
    builder.add_edge("teacher_review", END)
    return builder.compile(checkpointer=MemorySaver())


# ── 用例①：教师直接批准 AI 结果 ─────────────────────────────
async def atest_review_approve():
    print("\n" + "=" * 55)
    print("【teacher_review_node】用例① approve")
    print("=" * 55)

    graph = _build_review_graph()
    config = {"configurable": {"thread_id": "test-approve-001"}}

    # 第一次 invoke：图在 interrupt() 处暂停，返回 display_data
    snapshot = await graph.ainvoke(BASE_STATE, config=config)
    print(f"图已暂停，展示给教师的数据: {snapshot}")

    # 教师选择"批准"，不修改任何题目
    decision = {
        "action": "approve",
        "modifications": [],
        "teacher_id": "teacher-001",
    }
    final = await graph.ainvoke(Command(resume=decision), config=config)
    print("*"*80)
    print(f'final: {final}')
    print("*" * 80)
    print(f"teacher_decision: {final['teacher_decision']}")
    print("✅ approve 用例通过")


# ── 用例②：教师修改部分题目分数 ─────────────────────────────
async def atest_review_modify():
    print("\n" + "=" * 55)
    print("【teacher_review_node】用例② modify（修改 q-002 分数）")
    print("=" * 55)

    graph = _build_review_graph()
    config = {"configurable": {"thread_id": "test-modify-001"}}

    await graph.ainvoke(BASE_STATE, config=config)

    # 教师修改 q-002 分数，同时追加评语；q-001 不动
    decision = {
        "action": "modify",
        "modifications": [
            {
                "question_id": "q-002",
                "new_score": 8,
                "comment": "重新审阅，核心逻辑正确，调高分数",
            }
        ],
        "teacher_id": "teacher-001",
    }
    final = await graph.ainvoke(Command(resume=decision), config=config)
    print(f"final: {final}")
    print("*" * 80)
    td = final["teacher_decision"]
    print(f"teacher_decision: {td}")
    print("✅ modify 用例通过")


if __name__ == '__main__':
    import asyncio
    # asyncio.run(atest_review_approve())
    asyncio.run(atest_review_modify())
