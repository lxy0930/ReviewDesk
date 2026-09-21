# backend/agents/resume/nodes.py

import asyncio
import json
import os

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import text

from backend.agents.resume.state import (
    ResumeState, ResumeStructured, DimensionScore, IssueList, ResumeSummary,
)
from backend.agents.resume.prompts import (
    SYSTEM_PROMPT, EXTRACT_STRUCTURED_PROMPT, DIMENSION_REVIEW_PROMPTS,
    DIAGNOSE_ISSUES_PROMPT, GENERATE_SUMMARY_PROMPT, DIAGNOSE_THINK_PROMPT,
)
from backend.core.llm_factory import get_structured_llm, get_llm
from backend.core.logger import get_logger
from backend.dependencies import AsyncSessionLocal

logger = get_logger(__name__)


# ── 六维度定义（名称 / 权重 / 评分侧重）。权重之和 = 1.0 ──
SIX_DIMENSIONS = [
    {"key": "project_depth",  "name": "项目深度",   "weight": 0.30,
     "focus": "项目描述是否有量化数据、技术选型理由、个人贡献、难点解决"},
    {"key": "tech_match",     "name": "技术匹配度", "weight": 0.25,
     "focus": "技术栈是否与目标岗位匹配，技能描述是否有层次（熟练/了解/掌握）"},
    {"key": "expression",     "name": "表达规范性", "weight": 0.15,
     "focus": "动词开头、STAR 结构、无错别字、无主语省略歧义"},
    {"key": "structure",      "name": "简历结构",   "weight": 0.15,
     "focus": "模块完整性、排版逻辑、信息密度、重要内容是否放前面"},
    {"key": "quantification", "name": "量化程度",   "weight": 0.10,
     "focus": "性能指标、用户量、优化幅度等量化数据的使用情况"},
    {"key": "authenticity",   "name": "真实可信度", "weight": 0.05,
     "focus": "仅判断是否存在明确事实矛盾、日期错误或明显夸大；在校期间实习、项目与课程时间重叠属于正常情况，不得仅因时间重叠判定冲突"},
]


# ── 节点①②：本地模式空跑（保留以对齐结构 / 预留对象存储扩展点）──
async def upload_to_minio_node(state: ResumeState) -> dict:
    """文件已在本地，无需上传对象存储，直接跳过。"""
    logger.info("upload_to_minio.skip", review_id=state["review_id"], reason="local_mode")
    return {}
async def download_pdf_node(state: ResumeState) -> dict:
    """文件已在 pdf_local_path，无需下载，直接跳过。"""
    logger.info("download_pdf.skip", review_id=state["review_id"], reason="local_file_exists")
    return {}


# ── 节点③：extract_text —— PDF 文本提取（双栏处理 + 线程池）──
def _sync_extract_text(pdf_path: str) -> dict:
    """同步 PDF 文本提取（线程池中运行），处理双栏布局。"""
    import fitz                                       # PyMuPDF
    doc = fitz.open(pdf_path)
    page_count = len(doc)
    all_text_parts = []

    for page in doc:
        blocks = page.get_text("blocks")              # 每块 (x0,y0,x1,y1,text,no,type)
        text_blocks = [b for b in blocks if b[6] == 0]   # type==0 文字块
        if not text_blocks:
            continue
        page_width = page.rect.width
        midpoint   = page_width / 2
        left_blocks  = [b for b in text_blocks if b[0] < midpoint - 20]
        right_blocks = [b for b in text_blocks if b[0] >= midpoint - 20]
        is_two_column = (
            len(left_blocks) >= 2 and len(right_blocks) >= 2
            and len(right_blocks) / max(len(text_blocks), 1) > 0.3
        )
        if is_two_column:                             # 双栏：左栏读完读右栏
            left_sorted  = sorted(left_blocks,  key=lambda b: b[1])
            right_sorted = sorted(right_blocks, key=lambda b: b[1])
            page_text = (
                "\n".join(b[4].strip() for b in left_sorted  if b[4].strip())
                + "\n"
                + "\n".join(b[4].strip() for b in right_sorted if b[4].strip())
            )
        else:                                         # 单栏：按 y 从上到下
            sorted_blocks = sorted(text_blocks, key=lambda b: b[1])
            page_text = "\n".join(b[4].strip() for b in sorted_blocks if b[4].strip())
        all_text_parts.append(page_text)

    doc.close()
    raw_text = "\n\n---PAGE BREAK---\n\n".join(all_text_parts)
    return {"raw_text": raw_text, "page_count": page_count}

async def extract_text_node(state: ResumeState) -> dict:
    """异步节点：线程池跑同步解析，避免阻塞事件循环。"""
    pdf_path = state["pdf_local_path"]
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _sync_extract_text, pdf_path)
        raw_text, page_count = result["raw_text"], result["page_count"]
        if len(raw_text.strip()) < 200:               # 疑似扫描件/图片 PDF，仅告警
            logger.warning("extract_text.text_too_short", text_length=len(raw_text.strip()))
        logger.info("extract_text.done", page_count=page_count, text_length=len(raw_text))
        return {"raw_text": raw_text, "page_count": page_count}
    except Exception as e:
        logger.error("extract_text.failed", error=str(e))
        raise


# # ── 节点④：extract_structured —— LLM 结构化提取 ──
# async def extract_structured_node(state: ResumeState) -> dict:
#     """用 LLM Function Calling 把文本提取成结构化简历。"""
#     raw_text = state["raw_text"]
#     text_for_llm = raw_text[:4000] if len(raw_text) > 4000 else raw_text   # 超长截断
#     prompt = EXTRACT_STRUCTURED_PROMPT.format(resume_text=text_for_llm)
#     structured_llm = get_structured_llm("resume", ResumeStructured)
#     structured_dict = None
#     for attempt in range(2):                           # 结构化输出偶发返回 None → 判空+重试
#         try:
#             result = await structured_llm.ainvoke([
#                 SystemMessage(content=SYSTEM_PROMPT),
#                 HumanMessage(content=prompt),
#             ])
#             if result is None:
#                 raise ValueError("structured output returned None")
#             structured_dict = result.model_dump()
#             break
#         except Exception as e:
#             if attempt == 0:
#                 logger.warning("extract_structured.retry", error=str(e))
#                 await asyncio.sleep(1)
#             else:
#                 logger.warning("extract_structured.failed", error=str(e))
#     if structured_dict is None:
#         structured_dict = ResumeStructured(name="未能提取").model_dump()   # 降级空结构
#     logger.info("extract_structured.done",
#                 name=structured_dict.get("name", ""),
#                 projects_count=len(structured_dict.get("projects", [])))
#     return {"structured": structured_dict}


# ── 节点④：extract_structured —— LLM 通过提示词结构化提取 ──
async def extract_structured_node(state: ResumeState) -> dict:
    """用 JSON mode 把文本提取成结构化简历，比 Function Calling 更稳定。"""
    raw_text = state["raw_text"]
    text_for_llm = raw_text[:4000] if len(raw_text) > 4000 else raw_text

    prompt = EXTRACT_STRUCTURED_PROMPT.format(resume_text=text_for_llm)
    llm = get_llm("resume", temperature=0)

    structured_dict = None
    last_error = None

    for attempt in range(2):
        try:
            response = await llm.ainvoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])

            # 取出文本内容
            content = (
                response.content
                if hasattr(response, "content")
                else str(response)
            ).strip()

            # 记录原始返回，方便排查
            logger.debug("extract_structured.raw_response",
                         attempt=attempt, content_preview=content[:200])

            # 清理 markdown 代码块（```json ... ```）
            if "```" in content:
                blocks = content.split("```")
                # 取第一个代码块内容
                for block in blocks[1::2]:
                    block = block.strip()
                    if block.startswith("json"):
                        block = block[4:].strip()
                    content = block
                    break

            raw_dict = json.loads(content)
            # Pydantic 验证 + 补全缺失字段
            structured_dict = ResumeStructured(**raw_dict).model_dump()
            break

        except json.JSONDecodeError as e:
            last_error = f"JSON parse failed: {e} | raw={content[:300]}"
            logger.warning("extract_structured.json_error", attempt=attempt, error=last_error)
            if attempt == 0:
                await asyncio.sleep(1)

        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            logger.warning("extract_structured.error", attempt=attempt, error=last_error)
            if attempt == 0:
                await asyncio.sleep(1)

    if structured_dict is None:
        logger.warning("extract_structured.fallback", last_error=last_error)
        structured_dict = ResumeStructured(name="未能提取").model_dump()

    logger.info("extract_structured.done",
                name=structured_dict.get("name", ""),
                projects_count=len(structured_dict.get("projects", [])))
    return {"structured": structured_dict}



# ── 节点⑤：run_six_dimensions —— 六维度并行评审 ──
async def run_six_dimensions_node(state: ResumeState) -> dict:
    """六维度并行评审：asyncio.gather 同时评，算加权综合分。"""
    raw_text   = state["raw_text"]
    structured = state.get("structured") or {}
    structured_summary = _build_structured_summary(
        structured,
        target_position=state.get("target_position", ""),
        job_description=state.get("job_description", ""),
    )

    async def review_one_dimension(dim: dict) -> dict:
        prompt_template = DIMENSION_REVIEW_PROMPTS.get(dim["key"], "")
        if not prompt_template:
            return _empty_dimension_score(dim)
        prompt = prompt_template.format(
            resume_text=raw_text[:3000],
            structured_summary=structured_summary,
            focus=dim["focus"],
            job_description=state.get("job_description", ""),
        )
        for attempt in range(2):                      # 最多 2 次尝试
            try:
                structured_llm = get_structured_llm("resume", DimensionScore)
                result: DimensionScore = await structured_llm.ainvoke([
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content=prompt),
                ])
                d = result.model_dump()
                d["dimension"], d["weight"], d["key"] = dim["name"], dim["weight"], dim["key"]
                return d
            except Exception as e:
                if attempt == 0:
                    logger.warning("six_dimensions.dimension_retry", dimension=dim["name"], error=str(e))
                    await asyncio.sleep(1)
                else:
                    logger.warning("six_dimensions.dimension_failed", dimension=dim["name"], error=str(e))
                    return _empty_dimension_score(dim)

    tasks = [review_one_dimension(dim) for dim in SIX_DIMENSIONS]
    dimension_scores = await asyncio.gather(*tasks)              # 并行
    weighted_score = sum(d["score"] * d["weight"] for d in dimension_scores)
    logger.info("six_dimensions.done", weighted_score=round(weighted_score, 2),
                scores={d["key"]: d["score"] for d in dimension_scores})
    return {"dimension_scores": list(dimension_scores), "weighted_score": round(weighted_score, 2)}


def _build_structured_summary(
    structured: dict,
    target_position: str = "",
    job_description: str = "",
) -> str:
    """把结构化数据浓缩成几行摘要，供评审使用（省 token）。"""
    lines = []
    if structured.get("name"):
        lines.append(f"姓名：{structured['name']}")
    if target_position:
        lines.append(f"目标岗位：{target_position}")
    elif structured.get("target_position"):
        lines.append(f"求职意向：{structured['target_position']}")
    if job_description:
        lines.append(f"岗位描述：{job_description}")
    if structured.get("education"):
        edu = structured["education"][0]
        lines.append(f"最高学历：{edu.get('school','')} {edu.get('major','')} {edu.get('degree','')}")
    if structured.get("skills_list"):
        lines.append(f"技术栈：{', '.join(structured['skills_list'][:10])}")
    if structured.get("projects"):
        proj_names = [p.get("name", "") for p in structured["projects"]]
        lines.append(f"项目数量：{len(structured['projects'])} 个（{', '.join(proj_names[:3])}）")
    if structured.get("work_experience"):
        lines.append(f"工作经历：{len(structured['work_experience'])} 段")
    return "\n".join(lines) if lines else "（结构化提取失败，请基于原文评审）"

def _empty_dimension_score(dim: dict) -> dict:
    """维度评审失败时的降级结果。"""
    return {"key": dim["key"], "dimension": dim["name"], "score": 50, "weight": dim["weight"],
            "issues": ["该维度评审失败，建议人工复核"], "suggestions": []}


# ── 节点⑥：diagnose_issues —— 逐条问题诊断 ──
async def diagnose_issues_node(state: ResumeState) -> dict:
    """汇总维度问题 → Think 前置推理 → 结构化生成问题清单 → 按优先级排序。"""
    dimension_scores = state.get("dimension_scores", [])
    raw_text         = state["raw_text"]
    structured       = state.get("structured") or {}
    job_description  = state.get("job_description", "")
    target_position  = state.get("target_position", "")

    all_raw_issues = []
    for dim in dimension_scores:
        for issue_text in dim.get("issues", []):
            all_raw_issues.append(f"[{dim['dimension']}] {issue_text}")
    raw_issues_text = "\n".join(f"- {i}" for i in all_raw_issues) or "（暂无）"

    reasoning_trace = ""                              # Think 前置推理（可失败）
    try:
        dimension_scores_summary = "\n".join(
            f"- {d['dimension']}：{d['score']}分 — 问题：{', '.join(d.get('issues', [])[:2])}"
            for d in dimension_scores
        )
        think_prompt = DIAGNOSE_THINK_PROMPT.format(
            dimension_scores_summary=dimension_scores_summary,
            raw_issues=raw_issues_text,
            job_description=job_description,
        )
        think_llm = get_llm("resume", temperature=0)
        think_resp = await think_llm.ainvoke([HumanMessage(content=think_prompt)])
        reasoning_trace = (
            think_resp.text if hasattr(think_resp, "text") and not callable(think_resp.text)
            else str(think_resp.content)
        ).strip()
    except Exception as e:
        logger.warning("diagnose_think.failed", error=str(e))

    think_context = f"\n\n【诊断前宏观分析】\n{reasoning_trace}" if reasoning_trace else ""

    prompt = DIAGNOSE_ISSUES_PROMPT.format(
        resume_text=raw_text[:3000],
        structured_summary=_build_structured_summary(
            structured,
            target_position=target_position,
            job_description=job_description,
        ),
        raw_issues=raw_issues_text,
        job_description=job_description,
    ) + think_context

    try:
        structured_llm = get_structured_llm("resume", IssueList)
        result: IssueList = await structured_llm.ainvoke([
            SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])
        issues = [item.model_dump() for item in result.items]
    except Exception as e:
        logger.warning("diagnose_issues.failed", error=str(e))
        issues = [                                    # 降级：用维度问题，统一 medium
            {"priority": "medium", "dimension": dim["dimension"], "description": issue,
             "location": "简历全文", "suggestion": "请参考评审建议修改"}
            for dim in dimension_scores for issue in dim.get("issues", [])
        ]

    priority_order = {"high": 0, "medium": 1, "low": 2}          # 按优先级排序
    issues.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 2))
    issues = issues[:8]                                          # 只保留最重要的 6-8 条，这里统一截断
    logger.info("diagnose_issues.done", total=len(issues),
                high=sum(1 for i in issues if i.get("priority") == "high"))
    return {"issues": issues}


# ── 节点⑦：generate_summary —— 整体评价 ──
async def generate_summary_node(state: ResumeState) -> dict:
    """综合结构化信息、评分、问题，生成面向学员的整体评价。"""
    structured       = state.get("structured") or {}
    dimension_scores = state.get("dimension_scores", [])
    issues           = state.get("issues", [])
    weighted_score   = state.get("weighted_score", 0.0)
    target_position  = state.get("target_position", "")
    job_description  = state.get("job_description", "")

    high_issues = [i["description"] for i in issues if i.get("priority") == "high"][:5]
    high_issues_text = "\n".join(f"- {i}" for i in high_issues) or "（无高优先级问题）"
    scores_text = "\n".join(
        f"- {d['dimension']}：{d['score']}分（权重{int(d['weight'] * 100)}%）" for d in dimension_scores)

    prompt = GENERATE_SUMMARY_PROMPT.format(
        structured_summary=_build_structured_summary(
            structured,
            target_position=target_position,
            job_description=job_description,
        ),
        scores_summary=scores_text, weighted_score=round(weighted_score, 1),
        high_issues=high_issues_text,
        target_position=target_position or structured.get("target_position", "未填写"),
        job_description=job_description,
    )
    structured_llm = get_structured_llm("resume", ResumeSummary)
    summary_dict = None
    for attempt in range(2):                           # 结构化输出偶发返回 None → 判空+重试
        try:
            result = await structured_llm.ainvoke([
                SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])
            if result is None:
                raise ValueError("structured output returned None")
            summary_dict = result.model_dump()
            break
        except Exception as e:
            if attempt == 0:
                logger.warning("generate_summary.retry", error=str(e))
                await asyncio.sleep(1)
            else:
                logger.warning("generate_summary.failed", error=str(e))
    if summary_dict is None:
        summary_dict = {                              # 降级默认评价
            "highlights": ["简历内容已完整提交"],
            "core_improvements": high_issues[:2] if high_issues else ["请参考各维度建议修改"],
            "overall_comment": f"综合评分 {round(weighted_score, 1)} 分，请参考各维度详细反馈。",
            "fit_assessment": "与目标岗位匹配度评估暂不可用",
        }
    logger.info("generate_summary.done", highlights_count=len(summary_dict.get("highlights", [])))
    return {"summary": summary_dict}


# ── 节点⑧：save_results —— 持久化结果 ──
async def save_results_node(state: ResumeState) -> dict:
    """把完整结果写入 resume_reviews（JSONB 字段），清理临时文件。"""
    review_id = state["review_id"]

    # 留一份完整结果给上层（API 可直接用）
    structured_output = {
        "review_id": review_id, "student_id": state["student_id"],
        "target_position": state.get("target_position", ""),
        "job_description": state.get("job_description", ""),
        "structured": state.get("structured"),
        "weighted_score": state.get("weighted_score", 0),
        "dimension_scores": state.get("dimension_scores", []),
        "issues": state.get("issues", []),
        "summary": state.get("summary"),
    }

    async with AsyncSessionLocal() as session:        # 用统一的 SQLAlchemy 异步会话
        try:
            await session.execute(
                text("""
                    UPDATE resume_reviews
                    SET structured_data = :structured_data,
                        scores          = :scores,
                        issues          = :issues,
                        summary         = :summary,
                        target_position = :target_position,
                        job_description = :job_description,
                        status          = 'done',
                        updated_at      = NOW()
                    WHERE id = :review_id
                """),
                {
                    # JSONB 列：先 json.dumps 转 JSON 字符串；ensure_ascii=False 保留中文原文
                    "structured_data": json.dumps(state.get("structured"), ensure_ascii=False),
                    "scores": json.dumps(
                        {"dimension_scores": state.get("dimension_scores", []),
                         "weighted_score": state.get("weighted_score", 0)},
                        ensure_ascii=False),
                    "issues":  json.dumps(state.get("issues", []), ensure_ascii=False),
                    "summary": json.dumps(state.get("summary"), ensure_ascii=False),
                    "target_position": state.get("target_position", ""),
                    "job_description": state.get("job_description", ""),
                    "review_id": review_id,
                },
            )
            await session.commit()
            logger.info("save_results.db_written", review_id=review_id)
        except Exception as e:
            await session.rollback()
            logger.error("save_results.db_failed", error=str(e))
            raise

    # 清理本地临时 PDF
    local_path = state.get("pdf_local_path", "")
    if local_path and os.path.exists(local_path):
        os.remove(local_path)
        logger.info("save_results.tmp_cleaned", path=local_path)

    return {"fallback_used": False, "structured_output": structured_output}


# ── 模块自测：实测 PDF 文本提取（离线；其余节点测试见各节）──
if __name__ == "__main__":

    state = {"pdf_local_path": r'D:\job\PythonProjects\Multi-Agent\backend\agents\resume\刘新宇-简历.pdf'}
    res = asyncio.run(extract_text_node({"pdf_local_path": r'D:\job\PythonProjects\Multi-Agent\backend\agents\resume\刘新宇-简历.pdf'}))
    # print(res)
    state.update(res)
    res2 = asyncio.run(extract_structured_node(state))
    state.update(res2)
    res3 = asyncio.run(run_six_dimensions_node(state))
    print(res3)
    # import json
    # async def main():
    #     with open("./resume.json", encoding="utf-8") as f:
    #         state = json.load(f)
    #     result5 = await generate_summary_node(state)
    #     state.update(result5)
    #     with open("./resume.json", "w", encoding="utf-8") as f:
    #         f.write(json.dumps(state, indent=4, ensure_ascii=False))
    # asyncio.run(main())
    # import asyncio, uuid
    # from sqlalchemy import text
    # from backend.dependencies import AsyncSessionLocal
    #
    # rid = str(uuid.uuid4())
    #
    # async def main():
    #     async with AsyncSessionLocal() as s:        # 先插一条 processing 记录
    #         sid = (await s.execute(text("SELECT id FROM users WHERE username='student01'"))).scalar()
    #         await s.execute(text("""INSERT INTO resume_reviews (id,student_id,pdf_minio_path,status)
    #             VALUES (:id,:sid,'resumes/x.pdf','processing')"""), {"id": rid, "sid": sid})
    #         await s.commit()
    #     with open("./resume.json", encoding="utf-8") as f:
    #         state = json.load(f)
    #
    #     dict1 = {"review_id": rid, "student_id": str(sid)}
    #     state.update(dict1)
    #     await save_results_node(state)
    #
    #     async with AsyncSessionLocal() as s:  # 查回验证（用 JSONB 操作符）
    #         row = (await s.execute(text("""
    #                                     SELECT status,
    #                                            (scores ->>'weighted_score') AS ws,
    #                                            (structured_data ->>'name')  AS nm,
    #                                            jsonb_array_length(issues)   AS cnt
    #                                     FROM resume_reviews
    #                                     WHERE id = :id"""), {"id": rid})).mappings().fetchone()
    #         print("status:", row["status"], "| 加权分:", row["ws"], "| 姓名:", row["nm"], "| 问题数:", row["cnt"])
    #
    # asyncio.run(main())
