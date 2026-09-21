# backend/agents/exam/state.py

from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from pydantic import BaseModel


class ScoringPointResult(BaseModel):
    """单个得分点的评分结果"""
    point_id:    str
    point_desc:  str
    point_score: int
    earned:      bool
    evidence:    str   # earned=True 时填学员答案中对应原文
    missing:     str   # earned=False 时填未得分原因


class SubjectiveReviewResult(BaseModel):
    """简答题批改结果（LLM 结构化输出）"""
    question_id:     str
    student_answer:  str
    total_score:     int
    full_score:      int
    confidence:      float       # [0, 1]，低于 0.7 时标记需复核
    point_results:   list[ScoringPointResult]
    overall_comment: str


class WeakPoint(BaseModel):
    """单个知识薄弱点"""
    tag:          str            # 知识点标签，如 "Spring IOC"、"Redis缓存穿透"
    wrong_count:  int
    total_count:  int
    question_nos: list[int]      # 涉及的题目序号列表
    suggestion:   str            # 针对该知识点的复习建议


class WeakPointsReport(BaseModel):
    """知识薄弱点分析报告（LLM 结构化输出）"""
    weak_points:     list[WeakPoint]
    overall_summary: str         # 整体评价，不超过50字


class TeacherDecision(BaseModel):
    """教师确认决策（interrupt 恢复时传入）"""
    action:        str           # "approve" / "modify"
    modifications: list[dict]    # [{question_id, new_score, comment}, ...]
    teacher_id:    str
    
class ExamState(TypedDict):
    """试卷批改 Agent 完整 State"""

    # ── 请求上下文 ──────────────────────────────────────────────
    messages:        Annotated[list[BaseMessage], add_messages]
    student_id:      str
    session_id:      str
    exam_id:         str         # 试卷 ID（exams 表）
    submission_id:   str         # 提交记录 ID（exam_submissions 表）
    word_file_path:  str         # 学员作答 Word 文件本地临时路径

    # ── 解析结果 ───────────────────────────────────────────────
    parsed_questions: list[dict] # 解析+DB合并后的完整题目列表

    # ── 三轨批改结果 ────────────────────────────────────────────
    objective_results:  list[dict]
    subjective_results: list[dict]
    code_results:       list[dict]

    # ── 汇总预批改结果 ─────────────────────────────────────────
    pre_review_summary: dict

    # ── 知识薄弱点分析 ─────────────────────────────────────────
    weak_points:         list[dict]
    weak_points_summary: str

    # ── Human-in-the-Loop ──────────────────────────────────────
    teacher_notified:  bool
    teacher_decision:  Optional[dict]

    # ── 最终结果 ───────────────────────────────────────────────
    final_results:     list[dict]
    published:         bool

    # ── 降级标记 ───────────────────────────────────────────────
    fallback_used:     bool
    structured_output: Optional[dict]
