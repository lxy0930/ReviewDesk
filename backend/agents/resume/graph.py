from langgraph.graph import StateGraph, START, END

from backend.agents.resume.state import ResumeState
from backend.agents.resume.nodes import (          # 导入 8 个节点函数
    upload_to_minio_node,
    download_pdf_node,
    extract_text_node,
    extract_structured_node,
    run_six_dimensions_node,
    diagnose_issues_node,
    generate_summary_node,
    save_results_node,
)


def build_resume_graph():
    """构建并编译简历审查 Agent 的状态图。
    特点：无分支、无 interrupt、无 checkpointer（一次性任务），六维度并行是性能关键路径。"""
    builder = StateGraph(ResumeState)              # 用 ResumeState 作为图的状态类型

    # ① 注册 8 个节点（节点名 → 节点函数）
    builder.add_node("upload_to_minio",    upload_to_minio_node)
    builder.add_node("download_pdf",       download_pdf_node)
    builder.add_node("extract_text",       extract_text_node)
    builder.add_node("extract_structured", extract_structured_node)
    builder.add_node("run_six_dimensions", run_six_dimensions_node)
    builder.add_node("diagnose_issues",    diagnose_issues_node)
    builder.add_node("generate_summary",   generate_summary_node)
    builder.add_node("save_results",       save_results_node)

    # ② 顺次连边：START → … → END（一条直线，无分支）
    builder.add_edge(START,                 "upload_to_minio")
    builder.add_edge("upload_to_minio",     "download_pdf")
    builder.add_edge("download_pdf",        "extract_text")
    builder.add_edge("extract_text",        "extract_structured")
    builder.add_edge("extract_structured",  "run_six_dimensions")
    builder.add_edge("run_six_dimensions",  "diagnose_issues")
    builder.add_edge("diagnose_issues",     "generate_summary")
    builder.add_edge("generate_summary",    "save_results")
    builder.add_edge("save_results",        END)

    # ③ 编译。不传 checkpointer：一次性任务，不需要断点恢复
    return builder.compile()
if __name__ == '__main__':
    g = build_resume_graph()
    nodes = [n for n in g.get_graph().nodes if n not in ("__start__", "__end__")]
    print("图编译成功:", g is not None)
    print("节点数:", len(nodes))
    print("节点:", nodes)
