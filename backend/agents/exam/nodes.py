# backend/agents/exam/nodes.py

import asyncio
import json
import uuid
from typing import Any

import httpx
from sqlalchemy import text
from langchain_core.messages import HumanMessage, SystemMessage

from langgraph.types import interrupt

from backend.agents.exam.state import (
    ExamState,
    SubjectiveReviewResult,
    WeakPointsReport,
)
from backend.agents.exam.prompts import (
    SYSTEM_PROMPT,
    SUBJECTIVE_REVIEW_PROMPT,
    SUBJECTIVE_THINK_PROMPT,
    CODE_REVIEW_PROMPT,
    WEAK_POINTS_ANALYSIS_PROMPT,
)
from backend.core.llm_factory import get_llm, get_structured_llm
from backend.core.logger import get_logger
from backend.dependencies import AsyncSessionLocal

logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────

def _get_message_content(msg) -> str:
    """统一获取消息文本内容（兼容 text 属性和 content 属性）"""
    if hasattr(msg, "text") and not callable(getattr(msg, "text", None)):
        return msg.text
    if isinstance(msg.content, str):
        return msg.content
    return str(msg.content)


def _chinese_to_int(s: str) -> int:
    """中文数字转整数，转换失败时直接 int()，仍失败时返回1"""
    cn_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    try:
        return int(s)
    except ValueError:
        # print("强转失败")
        return cn_map.get(s, 1)


# ──────────────────────────────────────────────────────────────
# 节点1：parse_word — 解析学员作答 Word 文件
# ──────────────────────────────────────────────────────────────

def _sync_parse_word(word_path: str) -> list:
    """
    同步解析 Word 文件（在线程池中运行，避免阻塞事件循环）。

    返回 list[dict]，每个 dict 包含：
        question_no:    题号（int）
        header_text:    原始题目行文本
        student_answer: 学员作答文本（代码题为代码字符串）
        is_code:        True 表示代码题（仅代码题有此字段）
    """
    from docx import Document
    import re

    doc = Document(word_path)
    parsed_questions = [] # 最终结果：所有题目组成的列表
    current_question  = None # 当前正在解析的题目
    current_answer_lines = [] # 当前题【答案】
    in_code_block = False # 是否正处于代码内部
    code_buffer   = [] # 当前代码块累积的内容

    for para in doc.paragraphs:
        para_text = para.text.strip()
        # print(f'para_text: {para_text}')
        # 空行：代码块内保留，其他忽略
        if not para_text:
            if in_code_block:
                code_buffer.append("")
            continue
        # 判断是否是题目开头行（支持 "第X题" / "Q.X" / "题目X"）
        is_question_header = re.match(
            r"^(第?\s*[一二三四五六七八九十\d]+\s*[题、。.]|Q\.?\s*\d+|题目\s*\d+)",
            para_text,
            re.IGNORECASE,
        )
        # print(f'is_question_header-->{is_question_header} ')

        if is_question_header:
            # print(f'1current_question:{current_question}')
            # 保存上一题（如果有）
            if current_question is not None:
                if not current_question.get("is_code"):
                    answer_text = "\n".join(code_buffer) if in_code_block \
                        else "\n".join(current_answer_lines)
                    current_question["student_answer"] = answer_text.strip()
                parsed_questions.append(current_question)
            # print(f'2current_question:{current_question}')
            # print(f'parsed_questions-->{parsed_questions}')
            # 提取题号（优先数字，其次中文数字）
            match = re.search(r"[一二三四五六七八九十\d]+", para_text)
            # print(f'match-->{match}')
            # print(f'match.group()-->{match.group()}')
            q_no = _chinese_to_int(match.group()) if match else len(parsed_questions) + 1
            # print(f'q_no-->{q_no}')

            current_question     = {"question_no": q_no, "header_text": para_text, "student_answer": ""}
            current_answer_lines = []
            code_buffer          = []
            in_code_block        = False
            # print(f'current_question-->{current_question}')

        elif para_text.startswith("```"):
            # 代码块开关：遇到第二个 ``` 时闭合，保存代码内容
            # print(f'1in_code_block-->{in_code_block}')
            in_code_block = not in_code_block
            # print(f'3current_question-->{current_question}')
            if not in_code_block and current_question:
                current_question["student_answer"] = "\n".join(code_buffer).strip()
                current_question["is_code"] = True

        elif in_code_block:
            # 代码块内部：保留原始缩进（不 strip）
            # print(f'2in_code_block-->{in_code_block}')
            code_buffer.append(para.text)
            # print(f"code_buffer-->{code_buffer}")

        elif current_question is not None:
            # 跳过纯模板提示行（不含实际答案）
            # print(f'4current_question-->{current_question}')
            skip_prefixes = ["作答区", "请在此处"]
            if any(para_text.startswith(p) for p in skip_prefixes):
                pass
            else:
                # 提取 "答：X" 格式的答案内容（只取冒号后部分）
                answer_prefixes = ["答：", "答:", "Answer:"]
                extracted = None
                for prefix in answer_prefixes:
                    if para_text.startswith(prefix):
                        rest = para_text[len(prefix):].strip()
                        if rest:
                            extracted = rest
                        break   # 无论是否有内容都不再把整行加入
                # print(f'extracted-->{extracted}')
                if extracted is not None:
                    current_answer_lines.append(extracted)
                elif not any(para_text.startswith(p) for p in answer_prefixes):
                    current_answer_lines.append(para_text)
        #         print(f'current_answer_lines-->{current_answer_lines}')
        # print("*"*60)
    # print(f'parsed_questions: {parsed_questions}')
    # print("*"*80)
    # print(f'last_current_question: {current_question}')
    # 保存最后一题
    if current_question is not None:
        if not current_question.get("is_code"):
            answer_text = "\n".join(code_buffer) if in_code_block \
                else "\n".join(current_answer_lines)
            current_question["student_answer"] = answer_text.strip()
        parsed_questions.append(current_question)

    return parsed_questions

async def parse_word_node(state: ExamState) -> dict:
    """
    解析学员提交的 Word 试卷文件，提取各题作答内容。

    python-docx 内部有文件 I/O（打开 .docx zip）和 XML 解析（ElementTree），
    两者都是同步阻塞操作，不能直接在 async 函数里调用。
    用 run_in_executor(None, ...) 放入默认线程池，asyncio 事件循环继续处理
    其他协程，线程完成后 await 恢复。
    """
    word_path = state["word_file_path"]

    try:
        loop = asyncio.get_running_loop()
        parsed_questions = await loop.run_in_executor(None, _sync_parse_word, word_path)

        logger.info(
            "parse_word.done",
            file=word_path,
            questions_found=len(parsed_questions),
        )

        return {"parsed_questions": parsed_questions}

    except Exception as e:
        logger.error("parse_word.failed", error=str(e), file=word_path)
        # 优雅降级：文件损坏或格式不符时，返回空列表。
        # 后续 load_questions_meta_node 从 DB 补全题目信息，
        # student_answer 全部为空字符串，教师人工补批。
        return {"parsed_questions": []}

# ──────────────────────────────────────────────────────────────
# 节点2：加载题目元数据（含标准答案、得分点、知识点标签）
# ──────────────────────────────────────────────────────────────

async def load_questions_meta_node(state: ExamState) -> dict:
    """
    从数据库加载试卷的完整题目元数据（含标准答案、得分点、知识点标签），
    与解析出的学员答案合并，覆盖写入 parsed_questions。
    """
    exam_id = state["exam_id"]
    parsed  = state["parsed_questions"]   # parse_word_node 的输出

    async with AsyncSessionLocal() as session:
        # ── ① 加载题目列表 ──────────────────────────────────────
        result = await session.execute(
            text("""
                SELECT id, question_no, question_type, content,
                       correct_answer, score, knowledge_tag
                FROM questions
                WHERE exam_id = :exam_id
                ORDER BY question_no
            """),
            {"exam_id": exam_id},
        )
        questions = result.mappings().all()
        # print(f'questions: {len(questions)}')
        # print(f'*'*60)
        # print(f'questions: {questions}')
        # print(f'*' * 60)
        # ── ② 加载得分点（仅简答题有）──────────────────────────
        question_ids = [str(q["id"]) for q in questions]
        # print(f'question_ids: {question_ids}')
        # print(f'*' * 60)
        scoring_points_rows = []
        if question_ids:
            # 动态构造 IN 子句（避免 asyncpg 的 ANY(:qids::uuid[]) 类型不兼容问题）
            param_names = [f":qid_{i}" for i in range(len(question_ids))]
            # print(f'param_names: {param_names}')
            # print(f'*' * 60)
            qid_params = {f"qid_{i}": qid for i, qid in enumerate(question_ids)}
            # print(f'qid_params: {qid_params}')
            # print(f'*' * 60)
            sp_result = await session.execute(
                text(f"""
                            SELECT id, question_id, point_desc, point_score
                            FROM scoring_points
                            WHERE question_id IN ({", ".join(param_names)})
                              AND is_active = TRUE
                            ORDER BY question_id, id
                        """),
                qid_params,
            )
            scoring_points_rows = sp_result.mappings().all()
            # print(f'scoring_points_rows: {scoring_points_rows}')

        # ── ③ 按 question_id 聚合得分点 ─────────────────────────────
    sp_by_question: dict[str, list] = {}
    for sp in scoring_points_rows:
        qid = str(sp["question_id"])
        sp_by_question.setdefault(qid, []).append({
            "id": str(sp["id"]),
            "desc": sp["point_desc"],
            "score": sp["point_score"],
        })

    # print(f'sp_by_question: {sp_by_question}')
    # print("*"*80)
    # parsed_by_no = {p["question_no"]: p for p in parsed}
    # print(f'parsed_by_no: {parsed_by_no}')

    # ── ④ 以 DB 题目为主，合并解析结果 ─────────────────────────
    parsed_by_no = {p["question_no"]: p for p in parsed}
    merged_questions = []

    for q in questions:
        q_no = q["question_no"]
        merged_questions.append({
            "question_id": str(q["id"]),
            "question_no": q_no,
            "question_type": q["question_type"],
            "content": q["content"],
            "student_answer": parsed_by_no.get(q_no, {}).get("student_answer", ""),
            "correct_answer": q["correct_answer"] or "",
            "scoring_points": sp_by_question.get(str(q["id"]), []),
            "full_score": q["score"],
            "knowledge_tag": q["knowledge_tag"] or "",
        })

    logger.info(
        "load_questions_meta.done",
        exam_id=exam_id,
        total_questions=len(merged_questions),
    )

    return {"parsed_questions": merged_questions}

# ── 客观题答案标准化 ──────────────────────────────────────────

def _normalize_answer(answer: str) -> str:
    """
    标准化答案字符串，消除大小写/空格/标点差异，使多选题选项顺序无关。
    处理步骤：
        1. 统一大写（A/a → A）
        2. 去除所有空格、中文逗号、英文逗号
           "A, B, C" → "ABC"，"A，B，C" → "ABC"
        3. 字符排序（多选题 "BA" 和 "AB" 视为等价）
           sorted("ABC") → ['A','B','C'] → "ABC"
    """
    cleaned = answer.upper().replace(" ", "").replace("，", "").replace(",", "")
    return "".join(sorted(cleaned))

# ── 第一轨：规则引擎（客观题）────────────────────────────────
async def _run_objective_track(questions: list[dict]) -> list[dict]:
    """
    客观题规则批改。虽然声明为 async，内部没有 await，
    但保持 async 统一接口方便在 asyncio.gather 中与其他两轨并行。
    """
    results = []
    for q in questions:
        student_ans = _normalize_answer(q["student_answer"])
        correct_ans = _normalize_answer(q["correct_answer"])
        is_correct  = (student_ans == correct_ans)

        results.append({
            "question_id":    q["question_id"],
            "question_no":    q["question_no"],
            "question_type":  q["question_type"],
            "knowledge_tag":  q.get("knowledge_tag", ""),
            "content":        q.get("content", ""),
            "student_answer": q["student_answer"],
            "correct_answer": q["correct_answer"],
            "is_correct":     is_correct,
            "score":          q["full_score"] if is_correct else 0,
            "full_score":     q["full_score"],
            "needs_review":   False,          # 客观题不需要教师复核
            "ai_feedback":    "正确" if is_correct else f"正确答案：{q['correct_answer']}",
        })

    return results

# ── 第二轨：LLM 语义评分（简答题）────────────────────────────
async def _review_one_subjective(q: dict) -> dict:
    """批改单道简答题，两步流程：先 Think Tool 推理，再结构化评分。"""
    # 构造得分点描述文本
    scoring_points_text = "\n".join([
        f"  {i + 1}. [{sp['score']}分] {sp['desc']}"
        for i, sp in enumerate(q["scoring_points"])
    ]) or "  （无预设得分点，请综合评分）"
    # print("*"*60)
    # print(f'scoring_points_text: {scoring_points_text}')
    student_answer_text = q["student_answer"] or "（学员未作答）"

    # ── 第一步：Think Tool 推理分析 ───────────────────────────
    reasoning_trace = ""
    try:
        think_prompt = SUBJECTIVE_THINK_PROMPT.format(
            question_content=q["content"],
            scoring_points=scoring_points_text,
            student_answer=student_answer_text,
        )
        think_llm = get_llm("exam_subjective", temperature=0)
        think_resp = await think_llm.ainvoke([HumanMessage(content=think_prompt)])
        reasoning_trace = _get_message_content(think_resp).strip()
        logger.debug("subjective_think.done", question_no=q.get("question_no"))
    except Exception as e:
        # 推理失败不影响主评分，降级为直接评分
        logger.warning("subjective_think.failed", error=str(e))

    # ── 第二步：结构化评分（附带推理结论）────────────────────
    think_context = (
        f"\n\n【批改前分析】\n{reasoning_trace}" if reasoning_trace else ""
    )
    review_prompt = SUBJECTIVE_REVIEW_PROMPT.format(
        question_content=q["content"],
        scoring_points=scoring_points_text,
        full_score=q["full_score"],
        student_answer=student_answer_text,
    ) + think_context

    structured_llm = get_structured_llm("exam_subjective", SubjectiveReviewResult)
    result: SubjectiveReviewResult = await structured_llm.ainvoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=review_prompt),
    ])
    # print(f'result: {result}')

    return {
        "question_id": q["question_id"],
        "question_no": q["question_no"],
        "question_type": "short_answer",
        "knowledge_tag": q.get("knowledge_tag", ""),
        "content": q.get("content", ""),
        "student_answer": q["student_answer"],
        "score": result.total_score,
        "full_score": result.full_score,
        "needs_review": result.confidence < 0.7,  # 低把握度标记教师复核
        "confidence": result.confidence,
        "ai_feedback": result.overall_comment,
        "point_results": [p.model_dump() for p in result.point_results],
    }

async def _run_subjective_track(questions: list[dict]) -> list[dict]:
    """
    简答题批改，每 3 题一组并行处理。

    并行策略：
        把 N 道简答题切成 ⌈N/3⌉ 个组，组内 asyncio.gather 并行，
        组间顺序执行。目的是避免同时发起几十个 LLM 请求导致 API 限速。
    """
    if not questions:
        return []

    GROUP_SIZE = 3
    groups = [questions[i:i + GROUP_SIZE] for i in range(0, len(questions), GROUP_SIZE)]

    all_results = []
    for group in groups:
        group_results = await asyncio.gather(
            *[_review_one_subjective(q) for q in group],
            return_exceptions=True,
        )
        for q, result in zip(group, group_results):
            if isinstance(result, Exception):
                # 单题失败降级：标记 needs_review=True，不阻断整批
                logger.warning(
                    "subjective_track.question_failed",
                    question_id=q["question_id"],
                    error=str(result),
                )
                all_results.append({
                    "question_id":    q["question_id"],
                    "question_no":    q["question_no"],
                    "question_type":  "short_answer",
                    "knowledge_tag":  q.get("knowledge_tag", ""),
                    "content":        q.get("content", ""),
                    "student_answer": q["student_answer"],
                    "score":          0,
                    "full_score":     q["full_score"],
                    "needs_review":   True,
                    "confidence":     0.0,
                    "ai_feedback":    "AI 评分失败，已标记需教师人工批改",
                    "point_results":  [],
                })
            else:
                all_results.append(result)

    return all_results


# ── 第三轨：LLM（代码题）────────────────────────────
# backend/agents/exam/nodes.py（接 6.6）
async def _run_code_track(questions: list[dict]) -> list[dict]:
    """
    代码题批改入口：顺序逐题批改（代码题一般数量少，不必并行）。

    参数 questions：本卷里所有「代码题」的合并题目字典列表（来自 6.4 的合并结果，
                    已按题型筛选，这里只会收到 question_type == "code" 的题）。
    返回：每道代码题的批改结果字典组成的列表。
    """
    if not questions:                       # 没有代码题（空列表）
        return []                           # 直接返回空，省去后续循环
    results = []                            # 收集每道题的批改结果
    for q in questions:                     # 逐道代码题处理
        results.append(await _review_one_code(q))   # 调用单题批改，await 等它出结果
    return results                          # 返回全部代码题的批改结果


async def _review_one_code(q: dict) -> dict:
    """
    批改「单道代码题」：交给大模型综合评估功能正确性 + 代码质量。
    参数 q：一道代码题的「合并题目字典」（就是 6.4 load_questions_meta_node 产出的那种），
            本函数会读取它的下列键：
        q["question_id"]     题目 ID（str），原样写进批改结果，方便回填数据库
        q["question_no"]     题号（int）
        q["content"]         题目内容（str），喂给 LLM 当评分依据
        q["student_answer"]  学员提交的代码（str）
        q["correct_answer"]  标准答案（str）：这道题的「满分参考实现」，给 LLM 当对照标杆
        q["full_score"]      该题满分（int）
        q["knowledge_tag"]   知识点标签（str，可能缺省，用 .get 兜底）
    返回：一道代码题的批改结果字典（含 score / confidence / needs_review / quality_feedback 等）。
    """
    student_code       = q["student_answer"]                # 取出学员代码
    # print(f'student_code: {student_code}')
    reference_solution = q.get("correct_answer", "") or ""  # 取出参考实现（缺省给空串）
    # print(f'reference_solution: {reference_solution}')

    # 交给大模型评分：返回（逐条评语, 得分, 把握度）三元组
    feedback, score, confidence = await _llm_code_review(
        question_content=q["content"],          # 题目内容
        student_code=student_code,              # 学员代码
        full_score=q["full_score"],             # 该题满分（评分上限）
        reference_solution=reference_solution,  # 参考实现（对照标杆）
    )
    # ── 组装批改结果字典返回 ───────────────────────────────────
    return {
        "question_id":      q["question_id"],           # 题目 ID
        "question_no":      q["question_no"],           # 题号
        "question_type":    "code",                     # 题型固定 code
        "knowledge_tag":    q.get("knowledge_tag", ""), # 知识点（缺省空串）
        "content":          q.get("content", ""),       # 题目内容（缺省空串）
        "student_answer":   student_code,               # 学员代码
        "score":            score,                      # 本题最终得分（0~full_score）
        "full_score":       q["full_score"],            # 本题满分
        "confidence":       confidence,                 # LLM 评分把握度（0~1）
        "needs_review":     confidence < 0.7,           # 把握度低于 0.7 → 标记教师复核
        "quality_feedback": feedback,                   # LLM 逐条评语（list[str]，下游会用到）
        "ai_feedback":      "\n".join(feedback),        # 评语拼成单个字符串，方便展示
    }

async def _llm_code_review(
    question_content:   str,        # 题目内容
    student_code:       str,        # 学员代码
    full_score:         int,        # 该题满分（评分上限）
    reference_solution: str = "",   # 参考实现（默认空串）
) -> tuple[list[str], int, float]:
    """
    大模型综合评估代码：功能正确性 + 代码质量。

    返回一个三元组 (feedback, score, confidence)：
        feedback：  list[str]，逐条评语（功能正确性 + 四个质量维度）
        score：     int，得分，范围 0 ~ full_score
        confidence：float，LLM 自报的评分把握度，范围 0 ~ 1（越不确定越低）
    """
    # 用模板拼出完整 Prompt（把题目 / 参考实现 / 学员代码 / 满分填进去）
    prompt = CODE_REVIEW_PROMPT.format(
        question=question_content,                                  # {question}
        reference_solution=reference_solution or "（无参考实现，仅按代码本身评估）",  # {reference_solution}，没有就填兜底语
        code=student_code or "（未提交代码）",                       # {code}，没提交就填兜底语
        full_score=full_score,                                      # {full_score}：满分制
    )

    llm      = get_llm("exam_code")             # 从 llm_factory 取「代码评估」用的模型实例
    response = await llm.ainvoke([              # 异步调用大模型
        SystemMessage(content=SYSTEM_PROMPT),   # 系统提示（统一人设/规则）
        HumanMessage(content=prompt),           # 把上面拼好的 Prompt 作为用户消息
    ])
    # print(f'response: {response}')
    # 取出回复纯文本，并去掉模型可能多带的 ```json 代码围栏，方便 json.loads
    raw = _get_message_content(response).strip().replace("```json", "").replace("```", "").strip()
    # print(f'raw: {raw}')
    # print(json.loads(raw))
    try:                                        # 解析可能失败，包 try
        data       = json.loads(raw)            # 把回复解析成字典
        feedback   = data.get("feedback", [])   # 取逐条评语列表（缺省空列表）
        score      = min(int(data.get("score", 0)), full_score)  # 取分数，封顶到满分
        confidence = float(data.get("confidence", 0))            # 取把握度（缺省 0）
    except Exception:                           # 模型没返回合法 JSON
        # JSON 解析失败时的降级：不崩，给 0 分 + 把握度 0（→ 必复核）+ 提示人工
        feedback   = ["代码评估结果解析失败，请教师人工复核"]
        score      = 0
        confidence = 0.0

    return feedback, score, confidence          # 返回（评语列表, 得分, 把握度）



# ──────────────────────────────────────────────────────────────
# 节点3：run_three_tracks — 三轨并行批改
# ──────────────────────────────────────────────────────────────

async def run_three_tracks_node(state: ExamState) -> dict:
    """
    三轨并行批改：
        第一轨：规则引擎（客观题：单选/多选/判断）
        第二轨：LLM 语义评分（简答题，按3题一组并行）
        第三轨：LLM 代码质量评估（代码题，顺序执行）

    asyncio.gather(return_exceptions=True)：
        某一轨抛异常不会中断其他轨，异常作为返回值处理。
        失败的轨结果置为空列表，其余轨正常写入 State。
    """
    questions = state["parsed_questions"]

    objective_qs  = [q for q in questions if q["question_type"] in
                     ("single_choice", "multi_choice", "judge")]
    subjective_qs = [q for q in questions if q["question_type"] == "short_answer"]
    code_qs       = [q for q in questions if q["question_type"] == "code"]

    logger.info(
        "three_tracks.start",
        objective=len(objective_qs),
        subjective=len(subjective_qs),
        code=len(code_qs),
    )

    # 三轨并行启动，任何一轨失败不影响其他轨
    raw = await asyncio.gather(
        _run_objective_track(objective_qs),
        _run_subjective_track(subjective_qs),
        _run_code_track(code_qs),
        return_exceptions=True,
    )

    objective_results  = raw[0] if not isinstance(raw[0], Exception) else []
    subjective_results = raw[1] if not isinstance(raw[1], Exception) else []
    code_results       = raw[2] if not isinstance(raw[2], Exception) else []

    # 记录失败信息（不影响正常流程）
    for name, exc in zip(["objective", "subjective", "code"], raw):
        if isinstance(exc, Exception):
            logger.error(f"three_tracks.{name}_failed", error=str(exc))

    logger.info(
        "three_tracks.done",
        objective_done=len(objective_results),
        subjective_done=len(subjective_results),
        code_done=len(code_results),
    )

    return {
        "objective_results":  objective_results,
        "subjective_results": subjective_results,
        "code_results":       code_results,
    }

# ──────────────────────────────────────────────────────────────
# 节点4：aggregate_results — 汇总预批改结果
# ──────────────────────────────────────────────────────────────
async def aggregate_results_node(state: ExamState) -> dict:
    """
    合并三轨结果，按题号排序，计算总分和需复核题数。

    pre_review_summary 是后续 HitL 展示给教师的核心数据结构。
    """
    all_results = (
        state.get("objective_results", [])
        + state.get("subjective_results", [])
        + state.get("code_results", [])
    )
    all_results.sort(key=lambda x: x.get("question_no", 0))

    total_score        = sum(r.get("score", 0) for r in all_results)
    full_score         = sum(r.get("full_score", 0) for r in all_results)
    score_rate         = round(total_score / full_score, 4) if full_score > 0 else 0.0
    needs_review_count = sum(1 for r in all_results if r.get("needs_review", False))

    summary = {
        "total_score":        total_score,
        "full_score":         full_score,
        "score_rate":         score_rate,
        "needs_review_count": needs_review_count,
        "by_question":        all_results,
    }

    logger.info(
        "aggregate_results.done",
        total_score=total_score, full_score=full_score,
        score_rate=score_rate, needs_review=needs_review_count,
    )

    return {"pre_review_summary": summary}


# ──────────────────────────────────────────────────────────────
# 节点5：analyze_weak_points — 知识薄弱点分析
# ──────────────────────────────────────────────────────────────
async def analyze_weak_points_node(state: ExamState) -> dict:
    """
    分析学员知识薄弱点。

    路径1：有 knowledge_tag 的失分题 → 按标签直接聚合
    路径2：无 knowledge_tag 的失分题 → 全量失分题交 LLM 推断知识点 + 生成 suggestion
    两路合并，去重，按 wrong_count 降序排列。
    """
    all_results = state.get("pre_review_summary", {}).get("by_question", [])
    # print(f'all_results={all_results}')
    # print("*"*80)
    # 收集失分题（得分 < 满分）
    wrong_questions = [
        r for r in all_results
        if r.get("score", 0) < r.get("full_score", 1)
    ]
    # print(f"len(wrong_questions):{len(wrong_questions)}")
    # print(f"wrong_questions[0]:{wrong_questions[0]}")
    if not wrong_questions:
        logger.info("analyze_weak_points.no_wrong_questions", submission_id=state["submission_id"])
        return {
            "weak_points": [],
            "weak_points_summary": "本次试卷全部答对，表现优秀！",
        }
    # ── 路径1：有标签 → 直接聚合 ─────────────────────────────
    tagged   = [r for r in wrong_questions if r.get("knowledge_tag")]
    # print(f"len(tagged):{len(tagged)}")
    untagged = [r for r in wrong_questions if not r.get("knowledge_tag")]
    # print(f'len(untagged):{len(untagged)}')

    tagged_weak: dict[str, dict] = {}
    for r in tagged:
        tag = r["knowledge_tag"]
        if tag not in tagged_weak:
            tagged_weak[tag] = {
                "tag":          tag,
                "wrong_count":  0,
                "total_count":  0,
                "question_nos": [],
                "suggestion":   "",
            }
        tagged_weak[tag]["wrong_count"]  += 1
        tagged_weak[tag]["total_count"]  += 1
        tagged_weak[tag]["question_nos"].append(r["question_no"])

    # print(f'tagged_weak:{tagged_weak}')
    # print("*"*60)
    # ── 路径2：全量失分题交 LLM（同时生成 suggestion 和 summary）
    llm_weak_points: list[dict] = []
    llm_summary = ""

    questions_for_llm = tagged + untagged
    if questions_for_llm:
        wrong_desc = "\n".join([
            f"第{r['question_no']}题（{r['question_type']}，{r['score']}/{r['full_score']}分）："
            f"\n  题目：{r.get('content', r.get('ai_feedback', ''))[:200]}"
            f"\n  AI反馈：{r.get('ai_feedback', '')[:150]}"
            for r in questions_for_llm
        ])

        prompt = WEAK_POINTS_ANALYSIS_PROMPT.format(wrong_questions=wrong_desc)
        structured_llm = get_structured_llm("exam_subjective", WeakPointsReport)

        try:
            report: WeakPointsReport = await structured_llm.ainvoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])
            # print(f'report:{report}')
            llm_weak_points = [wp.model_dump() for wp in report.weak_points]
            llm_summary = report.overall_summary
        except Exception as e:
            logger.warning("analyze_weak_points.llm_failed", error=str(e))
            llm_summary = "薄弱点分析失败，请教师根据错题情况人工判断。"

    # print(f"*"*80)
    # print(f'llm_weak_points:{llm_weak_points}')
    # print(f'llm_summary:{llm_summary}')

    # ── 合并两路结果，去重 ────────────────────────────────────
    # LLM 输出中可能包含已打标签的知识点，优先用规则聚合的结果，
    # LLM 的 suggestion 补充到规则聚合结果里。
    merged_tags = set(tagged_weak.keys())
    final_weak_points = []

    for llm_wp in llm_weak_points:
        tag = llm_wp.get("tag", "")
        if tag in tagged_weak:
            # 规则聚合的知识点，用 LLM 补充 suggestion
            tagged_weak[tag]["suggestion"] = llm_wp.get("suggestion", "")
        elif tag not in merged_tags:
            # 纯 LLM 推断的知识点（无标签题目）
            final_weak_points.append(llm_wp)
            merged_tags.add(tag)
    # print(f'*'*80)
    # print(f'final_weak_points-->{final_weak_points}')
    # print(f'merged_tags-->{merged_tags}')

    # 规则聚合结果（补充了 suggestion）加入最终列表
    for wp in tagged_weak.values():
        if not wp["suggestion"]:
            wp["suggestion"] = f"建议重点复习 {wp['tag']} 相关知识点。"
        final_weak_points.append(wp)
    # print(f'final_weak_points-->{final_weak_points}')

    # 按 wrong_count 降序排列（最薄弱的知识点排在前面）
    final_weak_points.sort(key=lambda x: x.get("wrong_count", 0), reverse=True)

    logger.info(
        "analyze_weak_points.done",
        submission_id=state["submission_id"],
        weak_count=len(final_weak_points),
    )

    return {
        "weak_points":         final_weak_points,
        "weak_points_summary": llm_summary or "已完成薄弱点分析，请查看详情。",
    }


# ──────────────────────────────────────────────────────────────
# 节点6：notify_teacher — 通知教师，更新提交状态
# ──────────────────────────────────────────────────────────────
async def notify_teacher_node(state: ExamState) -> dict:
    """
    将提交状态推进到 pending_review，等待教师确认。

    职责：
        1. 更新 exam_submissions.status = 'pending_review'
        2. 记录日志
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text("""
                    UPDATE exam_submissions
                    SET status = 'pending_review', updated_at = NOW()
                    WHERE id = :submission_id
                """),
                {"submission_id": state["submission_id"]},
            )

    logger.info("notify_teacher.done", submission_id=state["submission_id"])
    return {"teacher_notified": True}


# ──────────────────────────────────────────────────────────────
# 节点7：teacher_review — Human-in-the-Loop 暂停点
# ──────────────────────────────────────────────────────────────
async def teacher_review_node(state: ExamState) -> dict:
    """
    Human-in-the-Loop 核心节点。

    interrupt(display_data) 做两件事：
        1. 把 display_data 暴露给外部（教师可通过 GET 接口读取）
        2. 冻结图执行，State 自动保存到 MemorySaver

    图在此暂停，直到教师通过 POST /confirm 传入 Command(resume=decision) 恢复。
    恢复后，interrupt() 的返回值就是 decision（teacher_decision 字段）。
    """
    display_data = {
        "submission_id":       state["submission_id"],
        "student_id":          state["student_id"],
        "pre_review_summary":  state.get("pre_review_summary", {}),
        "weak_points":         state.get("weak_points", []),
        "weak_points_summary": state.get("weak_points_summary", ""),
        "message":             "请检查 AI 预批改结果和知识薄弱点分析，确认无误后点击发布。",
    }

    # interrupt() 在此暂停图执行
    teacher_decision = interrupt(display_data)

    logger.info(
        "teacher_review.resumed",
        submission_id=state["submission_id"],
        action=teacher_decision.get("action", "unknown"),
    )

    return {"teacher_decision": teacher_decision}



# ──────────────────────────────────────────────────────────────
# 节点8：apply_teacher_decision — 合并教师修改
# ──────────────────────────────────────────────────────────────
async def apply_teacher_decision_node(state: ExamState) -> dict:
    """
    将教师决策合并到批改结果中。

    approve：直接把 AI 分数作为最终分数
    modify： 按 modifications 列表覆盖指定题目的得分和评语
    """
    decision      = state.get("teacher_decision", {})
    action        = decision.get("action", "approve")
    modifications = decision.get("modifications", [])

    # 取 pre_review_summary 中的完整题目列表作为基础
    all_results = list(state.get("pre_review_summary", {}).get("by_question", []))

    # 每道题先用 AI 分数初始化 final_score
    for r in all_results:
        r["final_score"] = r.get("score", 0)

    # modify 时，按 question_id 找到对应题目，覆盖分数和评语
    if action == "modify" and modifications:
        # print(f'modify: {modifications}')
        # print("*"*80)
        id_to_idx = {r["question_id"]: i for i, r in enumerate(all_results)}
        # print(f'id_to_idx: {id_to_idx}')
        # print("*"*80)
        for mod in modifications:
            qid = mod.get("question_id")
            if qid in id_to_idx:
                idx = id_to_idx[qid]
                if "new_score" in mod:
                    all_results[idx]["teacher_score"] = mod["new_score"]
                    all_results[idx]["final_score"]   = mod["new_score"]   # 教师分覆盖 AI 分
                if "comment" in mod:
                    all_results[idx]["teacher_comment"] = mod["comment"]
                all_results[idx]["reviewed_by"] = decision.get("teacher_id", "")

    logger.info(
        "apply_teacher_decision.done",
        action=action,
        modifications_count=len(modifications),
    )

    return {"final_results": all_results}


# ──────────────────────────────────────────────────────────────
# 节点9：publish_results — 发布批改结果
# ──────────────────────────────────────────────────────────────
async def publish_results_node(state: ExamState) -> dict:
    """
    将最终批改结果写入数据库，发布给学员。

    写入逻辑：
        exam_reviews  ── 先删后插（幂等），每道题一行
        exam_submissions ── 更新 status='published' + weak_points JSON
    """
    final_results = state.get("final_results", [])
    submission_id = state["submission_id"]
    teacher_id    = state.get("teacher_decision", {}).get("teacher_id", "") or None
    weak_points   = state.get("weak_points", [])

    async with AsyncSessionLocal() as session:
        async with session.begin():

            # ── 逐题写入 exam_reviews ─────────────────────────
            for r in final_results:
                # 先删后插：避免重复发布时产生重复记录
                await session.execute(
                    text("""
                        DELETE FROM exam_reviews
                        WHERE submission_id = :submission_id
                          AND question_id   = :question_id
                    """),
                    {"submission_id": submission_id, "question_id": r["question_id"]},
                )
                await session.execute(
                    text("""
                        INSERT INTO exam_reviews (
                            id, submission_id, question_id, question_type,
                            knowledge_tag, student_answer,
                            ai_score, ai_feedback, ai_raw_result,
                            teacher_score, teacher_comment, final_score,
                            needs_review, reviewed_by, reviewed_at
                        ) VALUES (
                            :id, :submission_id, :question_id, :question_type,
                            :knowledge_tag, :student_answer,
                            :ai_score, :ai_feedback, :ai_raw_result,
                            :teacher_score, :teacher_comment, :final_score,
                            :needs_review, :reviewed_by, NOW()
                        )
                    """),
                    {
                        "id":              str(uuid.uuid4()),
                        "submission_id":   submission_id,
                        "question_id":     r["question_id"],
                        "question_type":   r["question_type"],
                        "knowledge_tag":   r.get("knowledge_tag", ""),
                        "student_answer":  r.get("student_answer", ""),
                        "ai_score":        r.get("score", 0),
                        "ai_feedback":     r.get("ai_feedback", ""),
                        "ai_raw_result":   json.dumps(r),           # 完整原始结果存 JSON
                        "teacher_score":   r.get("teacher_score"),  # None 表示未修改
                        "teacher_comment": r.get("teacher_comment"),
                        "final_score":     r.get("final_score", r.get("score", 0)),
                        "needs_review":    r.get("needs_review", False),
                        "reviewed_by":     teacher_id,
                    },
                )

            # ── 更新提交状态为已发布 ─────────────────────────
            await session.execute(
                text("""
                    UPDATE exam_submissions
                    SET status               = 'published',
                        published_at         = NOW(),
                        updated_at           = NOW(),
                        weak_points          = :weak_points,
                        weak_points_summary  = :weak_points_summary
                    WHERE id = :submission_id
                """),
                {
                    "submission_id":       submission_id,
                    "weak_points":         json.dumps(weak_points),
                    "weak_points_summary": state.get("weak_points_summary", ""),
                },
            )

    total_final = sum(r.get("final_score", 0) for r in final_results)
    full_score  = sum(r.get("full_score", 0) for r in final_results)

    logger.info(
        "publish_results.done",
        submission_id=submission_id,
        final_score=total_final,
        weak_points_count=len(weak_points),
    )

    # structured_output 供 API 层直接返回给教师确认接口
    return {
        "published": True,
        "structured_output": {
            "submission_id":       submission_id,
            "final_score":         total_final,
            "full_score":          full_score,
            "score_rate":          round(total_final / full_score, 4) if full_score else 0,
            "weak_points":         weak_points,
            "weak_points_summary": state.get("weak_points_summary", ""),
            "published":           True,
        },
    }



if __name__ == '__main__':
    #todo: 测试AI的批改结果示例
    # state = {"word_file_path": "./student_answer.docx"}
    # import asyncio
    # async def main():
    #     # parsed_questions = await parse_word_node(state)
    #     # a = {"exam_id":"e0000001-0000-0000-0000-000000000001"}
    #     # state.update(a)
    #     # state.update(parsed_questions)
    #     # print(f'state={state}')
    #     # merge_results = await load_questions_meta_node(state)
    #     # print(f"{merge_results}")
    #     # print("*"*80)
    #     # objective_qs = [q for q in merge_results['parsed_questions'] if q["question_type"] in  # 客观题：单选/多选/判断
    #     #                 ("single_choice", "multi_choice", "judge")]
    #     # # print(f'objective_qs={objective_qs}')
    #     # result3 =  await  _run_objective_track(objective_qs)
    #     # print(result3)
    #     # 获取简单题内容：取索引
    #     # print(f'merge_results["parsed_questions"][3]-->{merge_results["parsed_questions"][3]}')
    #     # result4 = await _review_one_subjective(merge_results["parsed_questions"][3])
    #     # result5 = await _run_subjective_track([merge_results["parsed_questions"][3],merge_results["parsed_questions"][3],merge_results["parsed_questions"][3]])
    #     # print(f"result5: {result5}")
    #     # 评估一个代码题：
    #     # result6 = await _run_code_track([merge_results["parsed_questions"][4]])
    #     # print(result6)
    #     # 三轨并行：
    #     # result7 = await run_three_tracks_node(merge_results)
    #     # # print(f'result7 = {result7}')
    #     # result8 = await aggregate_results_node(result7)
    #     # print(f"result8: {result8}")
    #     # result9 = await analyze_weak_points_node(result8)
    #     # state = {"submission_id": "b1e441d8-83ec-49d6-838c-ba5bbc61be96"}
    #     result = await notify_teacher_node(state)
    #
    #
    #     print(result)
    # asyncio.run(main())
    # todo:测试合并教师审核结果；这里可以直接用前面AI执行的结果
    # ══════════════════════════════════════════════════════════
    # apply_teacher_decision_node 测试
    # ══════════════════════════════════════════════════════════
    # import asyncio
    # async def a_test():
    #     # 公共题目数据（simulate pre_review_summary.by_question）
    #     BY_QUESTION = [
    #         {
    #             "question_id": "q-001", "question_type": "short_answer",
    #             "score": 7, "full_score": 10,
    #             "ai_feedback": "基本正确", "student_answer": "答案A",
    #         },
    #         {
    #             "question_id": "q-002", "question_type": "short_answer",
    #             "score": 5, "full_score": 10,
    #             "ai_feedback": "答案不完整", "student_answer": "答案B",
    #         },
    #     ]
    #
    #     async def atest_apply_approve():
    #         """approve：final_score 直接用 AI score，teacher_score 不存在"""
    #         print("\n" + "=" * 55)
    #         print("【apply_teacher_decision_node】用例① approve")
    #         print("=" * 55)
    #
    #         import copy
    #         state = {
    #             "teacher_decision": {
    #                 "action": "approve",
    #                 "modifications": [],
    #                 "teacher_id": "teacher-001",
    #             },
    #             "pre_review_summary": {"by_question": copy.deepcopy(BY_QUESTION)},
    #         }
    #         r = await apply_teacher_decision_node(state)
    #         results = r["final_results"]
    #         print(results)
    #         print("✅ approve 用例通过")
    #     async def atest_apply_modify_single():
    #         """modify 单题：只改 q-002，q-001 保持 AI 分"""
    #         print("\n" + "=" * 55)
    #         print("【apply_teacher_decision_node】用例② modify 单题")
    #         print("=" * 55)
    #
    #         import copy
    #         state = {
    #             "teacher_decision": {
    #                 "action": "modify",
    #                 "modifications": [
    #                     {
    #                         "question_id": "q-002",
    #                         "new_score": 8,
    #                         "comment": "逻辑正确，扣分过严，调高至8分",
    #                     }
    #                 ],
    #                 "teacher_id": "teacher-001",
    #             },
    #             "pre_review_summary": {"by_question": copy.deepcopy(BY_QUESTION)},
    #         }
    #         r = await apply_teacher_decision_node(state)
    #         print(r["final_results"])
    #         results = {x["question_id"]: x for x in r["final_results"]}
    #         print("✅ modify 单题用例通过")
    #
    #     await atest_apply_approve()
    #     print("*"*50)
    #     await atest_apply_modify_single()
    #
    # asyncio.run(a_test())
    async def atest_publish_results():
      print("\n" + "=" * 55)
      print("【publish_results_node】真实 PostgreSQL 写入验证")
      print("=" * 55)

      import uuid
      from sqlalchemy import text
      from backend.dependencies import AsyncSessionLocal

      test_sub_id = str(uuid.uuid4())

      # ── 1. 准备：查真实 question_id + 插测试 submission ──────
      async with AsyncSessionLocal() as session:
          async with session.begin():
              # 从 questions 表取一条真实 question_id（避免 FK 报错）
              row = await session.execute(
                  text("SELECT id FROM questions LIMIT 1")
              )
              real_qid = str(row.scalar())

              # 插入测试 submission（exam_id/student_id 不传，允许 NULL）
              await session.execute(
                  text("""
                      INSERT INTO exam_submissions
                          (id, source, status)
                      VALUES
                          (:id, 'word', 'pending_review')
                  """),
                  {"id": test_sub_id},
              )
      print(f"测试 submission_id : {test_sub_id}")
      print(f"真实 question_id   : {real_qid}")

      # ── 2. 构造 state（模拟 apply_teacher_decision_node 的输出）
      state = {
          "submission_id": test_sub_id,
          "final_results": [
              {
                  "question_id":     real_qid,
                  "question_type":   "short_answer",
                  "score":           7,           # AI 分
                  "final_score":     8,           # 教师修改后
                  "full_score":      10,
                  "ai_feedback":     "基本正确，表述不完整",
                  "student_answer":  "递归是函数调用自身的过程",
                  "knowledge_tag":   "递归算法",
                  "teacher_score":   8,
                  "teacher_comment": "核心概念正确，调高至8分",
                  "needs_review":    False,
              },
          ],
          # teacher_id 为空字符串 → or None → reviewed_by 写 NULL，跳过 FK 检查
          "teacher_decision":    {"action": "modify", "teacher_id": ""},
          "weak_points":         ["递归算法", "时间复杂度分析"],
          "weak_points_summary": "学员对递归理解薄弱，建议补充练习",
      }

      # ── 3. 执行节点 ────────────────────────────────────────
      result = await publish_results_node(state)
      print(f'result-->{result}')

      #
      # # ── 7. 清理测试数据（exam_reviews 通过 ON DELETE CASCADE 自动删除）
      # async with AsyncSessionLocal() as session:
      #     async with session.begin():
      #         await session.execute(
      #             text("DELETE FROM exam_submissions WHERE id = :id"),
      #             {"id": test_sub_id},
      #         )
      # print("测试数据已清理")
      # print("✅ publish_results_node 测试通过")

    asyncio.run(atest_publish_results())
