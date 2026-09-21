from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages      # 消息列表的「追加」合并器
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────
# 一、结构化提取结果（LLM Function Calling 的输出目标）
# ──────────────────────────────────────────────────────────────

class EducationItem(BaseModel):
    """单条教育经历。"""
    school:   str = Field(description="学校名称")          # description 会发给 LLM，指导它提取
    major:    str = Field(description="专业名称")
    degree:   str = Field(description="学历：本科/专科/硕士等")
    duration: str = Field(description="在校时间，如 2020.09 - 2024.06")
    gpa:      str = Field(default="", description="GPA 或成绩（可选）")  # 可选字段，提取不到给空串


class ProjectItem(BaseModel):
    """单条项目经历。"""
    name:        str       = Field(description="项目名称")
    role:        str       = Field(description="担任角色，如：后端开发/全栈/负责人")
    duration:    str       = Field(description="项目时间，如 2023.06 - 2023.12")
    tech_stack:  list[str] = Field(description="使用的技术栈列表，如 [Spring Boot, MySQL, Redis]")
    description: str       = Field(description="项目描述原文（保留原始表述）")
    # default_factory=list：列表默认值必须用工厂函数，不能写 default=[]（会被所有实例共享，经典坑）
    highlights:  list[str] = Field(default_factory=list, description="量化亮点句子列表（含数字的句子）")


class WorkItem(BaseModel):
    """单条工作/实习经历。"""
    company:     str       = Field(description="公司名称")
    position:    str       = Field(description="职位名称")
    duration:    str       = Field(description="工作时间")
    tech_stack:  list[str] = Field(default_factory=list, description="涉及技术栈")
    description: str       = Field(description="工作内容原文")


class ResumeStructured(BaseModel):
    """简历结构化提取结果（完整 Schema）——extract_structured 节点的输出目标。"""
    # 基本信息
    name:            str  = Field(description="姓名")
    phone:           str  = Field(default="", description="手机号")
    email:           str  = Field(default="", description="邮箱")
    target_position: str  = Field(default="", description="求职意向岗位")
    # 教育经历（按时间倒序）
    education:       list[EducationItem] = Field(default_factory=list)
    # 技能
    skills_raw:      str       = Field(default="", description="技能栏原始文本")
    skills_list:     list[str] = Field(default_factory=list, description="解析后的技术标签列表")
    # 项目经历
    projects:        list[ProjectItem] = Field(default_factory=list)
    # 工作/实习经历
    work_experience: list[WorkItem] = Field(default_factory=list)
    # 其他
    certificates:    list[str] = Field(default_factory=list, description="证书列表")
    self_intro:      str       = Field(default="", description="个人简介/自我评价原文")

# ──────────────────────────────────────────────────────────────
# 二、六维度评审结果
# ──────────────────────────────────────────────────────────────

class DimensionScore(BaseModel):
    """单个评审维度结果。"""
    # dimension/weight 由代码层填（来自 4.5 的 SIX_DIMENSIONS），LLM 不用管，给默认值即可
    dimension:   str       = Field(default="", description="维度名称（代码层覆盖，LLM 可留空）")
    score:       int       = Field(description="得分 0-100")               # LLM 真正要给的
    weight:      float     = Field(default=0.0, description="权重（代码层覆盖，LLM 可填 0）")
    issues:      list[str] = Field(default_factory=list, description="该维度问题列表")
    suggestions: list[str] = Field(default_factory=list, description="改进建议列表")


class IssueItem(BaseModel):
    """单条诊断问题。"""
    priority:    str = Field(description="优先级：high / medium / low")
    dimension:   str = Field(description="所属维度")
    description: str = Field(description="问题描述（1句话）")
    location:    str = Field(description="问题在简历中的定位，如：项目经历-电商系统-第2句")
    suggestion:  str = Field(description="具体修改建议（可操作）")


class IssueList(BaseModel):
    """IssueItem 列表的包装类。
    为什么要包一层：with_structured_output 要求顶层是「对象」而非「裸列表」，
    所以不能直接让 LLM 返回 list[IssueItem]，要包成 {items: [...]}。"""
    items: list[IssueItem]


class ResumeSummary(BaseModel):
    """简历整体评价——generate_summary 节点的输出目标。"""
    highlights:        list[str] = Field(description="2-3 条核心亮点")
    core_improvements: list[str] = Field(description="2-3 条最重要的改进方向")
    overall_comment:   str       = Field(description="1-2 句综合评语")
    fit_assessment:    str       = Field(description="对目标岗位的匹配度评估（1句话）")


class ResumeState(TypedDict):
    """简历审查 Agent 完整 State。字段按数据流阶段分组，对应各节点的产出。"""

    # ── 请求上下文 ──
    messages:       Annotated[list[BaseMessage], add_messages]  # 对话消息（追加合并）
    student_id:     str
    review_id:      str        # resume_reviews 表的 UUID
    pdf_minio_path: str        # 对象存储路径（本地模式留空，遗留字段）
    pdf_local_path: str        # 本地临时文件路径（真正用的）
    target_position: str       # 用户填写的目标岗位名称
    job_description: str       # 用户填写的目标岗位完整描述

    # ── 解析中间结果 ──
    raw_text:       str        # extract_text 产出：PDF 全文
    page_count:     int        # PDF 页数

    # ── 结构化提取结果 ──
    structured:     Optional[dict]   # extract_structured 产出：ResumeStructured.model_dump()

    # ── 六维度评审结果 ──
    dimension_scores: list[dict]     # run_six_dimensions 产出：六维度各一条
    weighted_score:   float          # 加权综合得分 0-100

    # ── 逐条问题诊断 ──
    issues:          list[dict]      # diagnose_issues 产出：IssueItem 列表，按优先级排序

    # ── 整体评价 ──
    summary:         Optional[dict]  # generate_summary 产出：ResumeSummary.model_dump()

    # ── 降级标记 ──
    fallback_used:    bool
    structured_output: Optional[dict]

if __name__ == '__main__':
    from pydantic import ValidationError

    # ① 嵌套构建一份结构化简历，并 dump 成字典
    r = ResumeStructured(
        name="张三",
        target_position="后端开发",
        education=[EducationItem(school="某大学", major="计算机", degree="本科", duration="2020.09-2024.06")],
        skills_list=["Java", "Spring Boot", "MySQL"],
        projects=[ProjectItem(name="电商系统", role="后端", duration="2023.06-2023.12",
                              tech_stack=["Spring Boot", "Redis"], description="做了下单与库存")],
    )
    # print(f'r-->{r}')
    # print("=="*50)
    # d = r.model_dump()
    # print(f'd-->{d}')
    # print("=="*50)
    # print("① 结构化简历 name:", d["name"], "| 项目数:", len(d["projects"]),
    #       "| 第一个项目技术栈:", d["projects"][0]["tech_stack"])
    # # ③ IssueList 包装
    # il = IssueList(items=[IssueItem(priority="high", dimension="项目深度",
    #                                 description="项目描述空洞", location="项目-电商-第2句", suggestion="补充技术难点")])
    # print("③ IssueList 条数:", len(il.items), "| 第一条优先级:", il.items[0].priority)

    # ④ 校验：缺必填字段会报错
    try:
        EducationItem(school="只有学校")   # 缺 major/degree/duration
    except ValidationError as e:
        print("④ 缺必填字段校验:", e.error_count(), "个错误（major/degree/duration 必填）")
        raise
