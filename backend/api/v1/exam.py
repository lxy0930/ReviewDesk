# backend/api/v1/exam.py

import asyncio
import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from pydantic import BaseModel
from langgraph.types import Command
from sqlalchemy import text

from backend.dependencies import get_current_user, AsyncSessionLocal
from backend.core.memory import build_config
from backend.core.orchestrator import AgentType, get_orchestrator
from backend.core.checkpoint import get_postgres_checkpointer
from backend.core.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

orchestrator = get_orchestrator()

# 持有 background task 引用，防止 asyncio GC 回收未完成的任务
_background_tasks: set[asyncio.Task] = set()


@router.post("/submit", status_code=202)
async def submit_exam(
    exam_id: str      = Form(...),
    file:    UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    学员提交作答 Word 试卷，触发 AI 三轨批改（异步后台）。
    立即返回 202 和 submission_id，批改在后台异步完成。
    """
    if not (file.filename or "").endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持 .docx 格式",
        )

    submission_id = str(uuid.uuid4())
    student_id    = current_user["user_id"]
    tmp_path      = os.path.join(tempfile.gettempdir(), f"{submission_id}.docx")

    # 把上传文件保存到临时目录
    content = await file.read()
    with open(tmp_path, "wb") as f:
        f.write(content)

    # ── 验证试卷 ID 是否存在 ─────────────────────────────────────
    async with AsyncSessionLocal() as session:
        exam_row = (await session.execute(
            text("SELECT id FROM exams WHERE id = :exam_id"),
            {"exam_id": exam_id},
        )).fetchone()

    if not exam_row:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"试卷 ID 不存在（{exam_id}）。"
                "本地开发环境请先运行 python scripts/seed_data.py。"
            ),
        )

    # ── 检查是否已有提交记录（同一学员同一试卷只能有一份）────────
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("""
                SELECT id, status FROM exam_submissions
                WHERE exam_id = :exam_id
                  AND student_id = :student_id
            """),
            {
                "exam_id": exam_id,
                "student_id": student_id,
            },
        )).fetchone()

    if row:
        existing_id, existing_status = str(row[0]), row[1]
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return {
            "submission_id": existing_id,
            "status": existing_status,
            "already_submitted": True,
            "message": "该试卷已经提交，返回已有提交记录。",
        }

    # ── 写入提交记录 ─────────────────────────────────────────────
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text("""
                    INSERT INTO exam_submissions
                        (id, exam_id, student_id, status, submitted_at)
                    VALUES
                        (:id, :exam_id, :student_id, 'ai_processing', NOW())
                """),
                {
                    "id":         submission_id,
                    "exam_id":    exam_id,
                    "student_id": student_id,
                },
            )

    config = build_config(current_user["user_id"], submission_id)
    print(f'config: {config}')

    initial_state = {
        "messages":           [],
        "student_id":         current_user["user_id"],
        "session_id":         submission_id,
        "exam_id":            exam_id,
        "submission_id":      submission_id,
        "word_file_path":     tmp_path,
        "parsed_questions":   [],
        "objective_results":  [],
        "subjective_results": [],
        "code_results":       [],
        "pre_review_summary": {},
        "weak_points":        [],
        "weak_points_summary": "",
        "teacher_decision":   None,
        "final_results":      [],
        "structured_output":  None,
        "fallback_used":      False,
        "teacher_notified":   False,
        "published":          False,
    }

    # ── 后台任务的 done callback ──────────────────────────────
    def _on_task_done(t: asyncio.Task):
        _background_tasks.discard(t)   # 从 set 移除，允许 GC
        task_failed = not t.cancelled() and t.exception() is not None

        if task_failed:
            logger.error(
                "exam.background_task_failed",
                submission_id=submission_id,
                error=str(t.exception()),
                exc_info=t.exception(),
            )

        async def _cleanup():
            if task_failed:
                # 批改失败时，把状态回滚为 submitted，允许学员重新提交
                try:
                    async with AsyncSessionLocal() as db_sess:
                        async with db_sess.begin():
                            await db_sess.execute(
                                text("""
                                    UPDATE exam_submissions
                                    SET status = 'submitted', updated_at = NOW()
                                    WHERE id = :sid AND status = 'ai_processing'
                                """),
                                {"sid": submission_id},
                            )
                except Exception as db_err:
                    logger.warning(
                        "exam.status_reset_failed",
                        submission_id=submission_id,
                        error=str(db_err),
                    )
            # 无论成败都清理临时文件
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        cleanup_task = asyncio.ensure_future(_cleanup())
        _background_tasks.add(cleanup_task)
        cleanup_task.add_done_callback(_background_tasks.discard)

    # ── 启动后台批改任务 ──────────────────────────────────────
    # graph.ainvoke 会在 teacher_review_node 处 interrupt，自动返回
    # 此时 task 完成，_on_task_done 被调用；图状态存在 MemorySaver 里等待恢复
    task = asyncio.create_task(
        orchestrator.run(AgentType.EXAM, initial_state, config=config)
    )
    _background_tasks.add(task)
    task.add_done_callback(_on_task_done)

    logger.info(
        "exam.submitted",
        submission_id=submission_id,
        student_id=current_user["user_id"],
        exam_id=exam_id,
    )

    return {
        "submission_id": submission_id,
        "status":        "ai_processing",
        "message":       "试卷已提交，AI 正在批改中，完成后等待教师确认。",
    }


@router.get("/my-submissions")
async def list_my_submissions(
    current_user: dict = Depends(get_current_user),
):
    """学员查询自己所有的试卷提交记录"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT es.id AS submission_id, e.title AS exam_title,
                       es.exam_id, es.status, es.submitted_at
                FROM exam_submissions es
                LEFT JOIN exams e ON e.id = es.exam_id
                WHERE es.student_id = :student_id
                ORDER BY es.submitted_at DESC
                LIMIT 20
            """),
            {"student_id": current_user["user_id"]},
        )
        rows = result.mappings().all()

    return {
        "items": [
            {
                "submission_id": str(r["submission_id"]),
                "exam_id":       str(r["exam_id"]),
                "exam_title":    r["exam_title"] or "",
                "status":        r["status"],
                "submitted_at":  r["submitted_at"].isoformat() if r["submitted_at"] else None,
            }
            for r in rows
        ]
    }


@router.get("/my-submissions/{submission_id}")
async def get_my_submission(
    submission_id: str,
    current_user:  dict = Depends(get_current_user),
):
    """
    学员查询批改状态与结果。
    - 未发布（ai_processing / pending_review）：只返回状态，等待
    - 已发布（published）：返回完整批改结果（逐题 + 薄弱点）
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, status, weak_points, weak_points_summary
                FROM exam_submissions
                WHERE id = :sid AND student_id = :student_id
            """),
            {"sid": submission_id, "student_id": current_user["user_id"]},
        )
        row = result.mappings().fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="提交记录不存在")

    # 未发布：只返回状态，让学员继续轮询
    if row["status"] != "published":
        return {"submission_id": submission_id, "status": row["status"]}

    # 已发布：从 exam_reviews 读取完整结果
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT er.question_id, er.question_type, er.knowledge_tag,
                       er.student_answer, er.ai_score, er.ai_feedback,
                       er.teacher_score, er.teacher_comment, er.final_score,
                       er.needs_review, er.ai_raw_result,
                       q.question_no, q.content, q.correct_answer, q.score AS full_score
                FROM exam_reviews er
                JOIN questions q ON q.id = er.question_id
                WHERE er.submission_id = :sid
                ORDER BY q.question_no
            """),
            {"sid": submission_id},
        )
        reviews = result.mappings().all()

    by_question      = []
    total_score      = 0
    full_score_total = 0

    for r in reviews:
        import json as _json
        raw = r["ai_raw_result"] or {}
        if isinstance(raw, str):
            try:
                raw = _json.loads(raw)
            except Exception:
                raw = {}
        final = r["final_score"] if r["final_score"] is not None else r["ai_score"]
        by_question.append({
            "question_id":       str(r["question_id"]),
            "question_no":       r["question_no"],
            "question_type":     r["question_type"],
            "content":           r["content"] or "",
            "full_score":        r["full_score"],
            "score":             r["ai_score"],
            "final_score":       final,
            "student_answer":    r["student_answer"] or "",
            "correct_answer":    r["correct_answer"] or "",
            "ai_feedback":       r["ai_feedback"] or "",
            "teacher_comment":   r["teacher_comment"] or "",
            "needs_review":      r["needs_review"],
            "point_results":     raw.get("point_results", []),
            "quality_feedback":  raw.get("quality_feedback", []),
        })
        total_score      += final or 0
        full_score_total += r["full_score"] or 0

    weak_points         = row["weak_points"] if isinstance(row["weak_points"], list) else []
    weak_points_summary = row["weak_points_summary"] or ""

    return {
        "submission_id": submission_id,
        "status":        "published",
        "pre_review_summary": {
            "total_score": total_score,
            "full_score":  full_score_total,
            "score_rate":  round(total_score / full_score_total, 4) if full_score_total else 0,
            "by_question": by_question,
        },
        "weak_points":         weak_points,
        "weak_points_summary": weak_points_summary,
    }


@router.get("/submissions/{submission_id}/review")
async def get_submission_review(
    submission_id: str,
    current_user:  dict = Depends(get_current_user),
):
    """教师获取 AI 预批改详情（从 MemorySaver 读取图暂停时的 State）"""
    config = {"configurable": {"thread_id": await _get_thread_id(submission_id)}}

    try:
        graph = orchestrator.get_graph(AgentType.EXAM)
        state_snapshot = await graph.aget_state(config)
        print(f'state: {state_snapshot}')
        print(f'state: {state_snapshot.values}')
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"找不到该提交记录的批改状态：{e}")

    if not state_snapshot or not state_snapshot.values:
        raise HTTPException(status_code=404, detail="批改尚未完成或记录不存在")

    sv = state_snapshot.values
    return {
        "submission_id":       submission_id,
        "student_id":          sv.get("student_id", ""),
        "pre_review_summary":  sv.get("pre_review_summary", {}),
        "weak_points":         sv.get("weak_points", []),
        "weak_points_summary": sv.get("weak_points_summary", ""),
    }


@router.get("/submissions/{submission_id}/result")
async def get_submission_final_result(
    submission_id: str,
    current_user: dict = Depends(get_current_user),
):
    """教师查看某个学生已发布的最终批改结果。"""
    async with AsyncSessionLocal() as session:
        submission = (await session.execute(
            text("""
                SELECT es.status, u.username AS student_name,
                       es.weak_points, es.weak_points_summary
                FROM exam_submissions es
                JOIN users u ON u.id = es.student_id
                WHERE es.id = :sid
            """),
            {"sid": submission_id},
        )).mappings().fetchone()

    if not submission:
        raise HTTPException(status_code=404, detail="提交记录不存在")

    if submission["status"] != "published":
        raise HTTPException(status_code=409, detail="该试卷尚未发布最终结果")

    async with AsyncSessionLocal() as session:
        reviews = (await session.execute(
            text("""
                SELECT er.question_id, er.question_type, er.knowledge_tag,
                       er.student_answer, er.ai_score, er.ai_feedback,
                       er.teacher_score, er.teacher_comment, er.final_score,
                       er.needs_review, er.ai_raw_result,
                       q.question_no, q.content, q.correct_answer,
                       q.score AS full_score
                FROM exam_reviews er
                JOIN questions q ON q.id = er.question_id
                WHERE er.submission_id = :sid
                ORDER BY q.question_no
            """),
            {"sid": submission_id},
        )).mappings().all()

    by_question = []
    total_score = 0
    full_score_total = 0

    for r in reviews:
        import json as _json
        raw = r["ai_raw_result"] or {}
        if isinstance(raw, str):
            try:
                raw = _json.loads(raw)
            except Exception:
                raw = {}

        final = r["final_score"] if r["final_score"] is not None else r["ai_score"]
        by_question.append({
            "question_id":      str(r["question_id"]),
            "question_no":      r["question_no"],
            "question_type":    r["question_type"],
            "knowledge_tag":    r["knowledge_tag"] or "",
            "content":          r["content"] or "",
            "full_score":       r["full_score"],
            "score":            r["ai_score"],
            "final_score":      final,
            "student_answer":   r["student_answer"] or "",
            "correct_answer":   r["correct_answer"] or "",
            "ai_feedback":      r["ai_feedback"] or "",
            "teacher_comment":  r["teacher_comment"] or "",
            "point_results":    raw.get("point_results", []),
            "quality_feedback": raw.get("quality_feedback", []),
        })
        total_score += final or 0
        full_score_total += r["full_score"] or 0

    weak_points = submission["weak_points"] or []
    if isinstance(weak_points, str):
        import json as _json
        try:
            weak_points = _json.loads(weak_points)
        except Exception:
            weak_points = []

    return {
        "submission_id": submission_id,
        "student_name": submission["student_name"],
        "status": "published",
        "pre_review_summary": {
            "total_score": total_score,
            "full_score": full_score_total,
            "score_rate": round(total_score / full_score_total, 4) if full_score_total else 0,
            "by_question": by_question,
        },
        "weak_points": weak_points,
        "weak_points_summary": submission["weak_points_summary"] or "",
    }

# ── 辅助函数：从 DB 获取 thread_id ───────────────────────────

async def _get_thread_id(submission_id: str) -> str:
    """从 exam_submissions 读 student_id，拼出 MemorySaver 的 thread_id"""
    from backend.core.memory import build_thread_id
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT student_id FROM exam_submissions WHERE id = :sid"),
                {"sid": submission_id},
            )
            row = result.fetchone()
            if row:
                return build_thread_id(str(row[0]), submission_id)
    except Exception as e:
        logger.warning("exam.get_thread_id_failed", submission_id=submission_id, error=str(e))
    return f"student_unknown_session_{submission_id}"


async def _get_published_result(submission_id: str) -> dict:
    """从数据库读取已发布结果，用于教师确认接口的幂等返回。"""
    async with AsyncSessionLocal() as session:
        submission = (await session.execute(
            text("""
                SELECT status, weak_points, weak_points_summary
                FROM exam_submissions
                WHERE id = :sid
            """),
            {"sid": submission_id},
        )).mappings().fetchone()

        if not submission:
            return {"submission_id": submission_id, "status": "missing"}

        score = {
            "final_score": 0,
            "full_score": 0,
        }

        if submission["status"] == "published":
            score = (await session.execute(
                text("""
                    SELECT
                        COALESCE(SUM(er.final_score), 0) AS final_score,
                        COALESCE(SUM(q.score), 0)         AS full_score
                    FROM exam_reviews er
                    JOIN questions q ON q.id = er.question_id
                    WHERE er.submission_id = :sid
                """),
                {"sid": submission_id},
            )).mappings().fetchone()

    import json as _json
    weak_points = submission["weak_points"]
    if isinstance(weak_points, str):
        try:
            weak_points = _json.loads(weak_points)
        except Exception:
            weak_points = []
    weak_points = weak_points or []

    final_score = int(score["final_score"] or 0)
    full_score = int(score["full_score"] or 0)

    return {
        "submission_id":       submission_id,
        "status":              submission["status"],
        "final_score":         final_score,
        "full_score":          full_score,
        "score_rate":          round(final_score / full_score, 4) if full_score else 0,
        "weak_points":         weak_points,
        "weak_points_summary": submission["weak_points_summary"] or "",
        "already_published":   True,
    }


@router.get("/pending-reviews")
async def get_pending_reviews(
    current_user: dict = Depends(get_current_user),
):
    """教师获取所有待确认的提交（status=pending_review）"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT
                    es.id           AS submission_id,
                    es.student_id,
                    u.username      AS student_name,
                    e.title         AS exam_title,
                    es.submitted_at
                FROM exam_submissions es
                JOIN users u ON u.id = es.student_id
                JOIN exams e ON e.id = es.exam_id
                WHERE es.status    = 'pending_review'
                ORDER BY es.submitted_at DESC
            """),
        )
        rows = result.mappings().all()

    items = []
    for row in rows:
        submission_id = str(row["submission_id"])
        pre_review    = {"total_score": 0, "full_score": 0, "needs_review_count": 0}
        weak_points   = []

        # 从 MemorySaver 读取 AI 预批改结果（图暂停时保存的 State）
        try:
            thread_id = await _get_thread_id(submission_id)
            config    = {"configurable": {"thread_id": thread_id}}
            graph     = orchestrator.get_graph(AgentType.EXAM)
            snapshot  = await graph.aget_state(config)
            if snapshot and snapshot.values:
                sv         = snapshot.values
                summary    = sv.get("pre_review_summary", {})
                pre_review = {
                    "total_score":        summary.get("total_score", 0),
                    "full_score":         summary.get("full_score", 0),
                    "needs_review_count": summary.get("needs_review_count", 0),
                }
                weak_points = sv.get("weak_points", [])
        except Exception as _e:
            logger.warning("exam.pending_review_state_read_failed",
                           submission_id=submission_id, error=str(_e))

        items.append({
            "submission_id": submission_id,
            "student_name":  row["student_name"],
            "exam_title":    row["exam_title"],
            "submitted_at":  row["submitted_at"].isoformat() if row["submitted_at"] else None,
            "pre_review":    pre_review,
            "weak_points":   weak_points[:3],  # 列表只显示前3条
        })

    return {"items": items, "total": len(items)}


@router.get("/submissions")
async def list_all_submissions(
    current_user: dict = Depends(get_current_user),
):
    """教师查看所有试卷提交及当前批改状态。"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT
                    es.id            AS submission_id,
                    es.student_id,
                    u.username       AS student_name,
                    es.exam_id,
                    e.title          AS exam_title,
                    es.status,
                    es.submitted_at,
                    es.published_at
                FROM exam_submissions es
                JOIN users u ON u.id = es.student_id
                JOIN exams e ON e.id = es.exam_id
                ORDER BY es.submitted_at DESC
            """),
        )
        rows = result.mappings().all()

    items = [
        {
            "submission_id": str(row["submission_id"]),
            "student_id": str(row["student_id"]),
            "student_name": row["student_name"],
            "exam_id": str(row["exam_id"]),
            "exam_title": row["exam_title"],
            "status": row["status"],
            "submitted_at": row["submitted_at"].isoformat() if row["submitted_at"] else None,
            "published_at": row["published_at"].isoformat() if row["published_at"] else None,
        }
        for row in rows
    ]
    return {
        "items": items,
        "total": len(items),
        "pending_review_count": sum(1 for item in items if item["status"] == "pending_review"),
        "published_count": sum(1 for item in items if item["status"] == "published"),
    }


@router.delete("/submissions/{submission_id}", status_code=204)
async def delete_submission(
    submission_id: str,
    current_user: dict = Depends(get_current_user),
):
    """教师删除学生试卷提交，同时清理对应的 checkpoint 状态。"""
    if current_user.get("role") not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="仅教师可以删除已发布试卷")

    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("""
                SELECT id, student_id, status
                FROM exam_submissions
                WHERE id = :sid
            """),
            {"sid": submission_id},
        )).mappings().fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="提交记录不存在")

    if row["status"] != "published":
        raise HTTPException(status_code=409, detail="只能删除已发布的试卷提交")

    thread_id = await _get_thread_id(submission_id)
    try:
        checkpointer = get_postgres_checkpointer()
        await checkpointer.adelete_thread(thread_id)
    except Exception as e:
        logger.warning(
            "exam.checkpoint_delete_failed",
            submission_id=submission_id,
            thread_id=thread_id,
            error=str(e),
        )

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text("DELETE FROM exam_submissions WHERE id = :sid"),
                {"sid": submission_id},
            )

    logger.info(
        "exam.submission_deleted",
        submission_id=submission_id,
        teacher_id=current_user["user_id"],
    )


class ConfirmRequest(BaseModel):
    action:        str
    modifications: list[dict] = []


@router.post("/submissions/{submission_id}/confirm")
async def confirm_review(
    submission_id: str,
    req:           ConfirmRequest,
    current_user:  dict = Depends(get_current_user),
):
    """
    教师确认批改结果，恢复 interrupt，触发 apply_teacher_decision → publish_results。
    """
    if req.action not in ("approve", "modify"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="action 只能为 approve 或 modify",
        )

    existing = await _get_published_result(submission_id)
    if existing["status"] == "published":
        return existing

    if existing["status"] == "missing":
        raise HTTPException(status_code=404, detail="提交记录不存在")

    if existing["status"] != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"当前状态为 {existing['status']}，无法确认发布",
        )

    thread_id = await _get_thread_id(submission_id)
    config    = {"configurable": {"thread_id": thread_id}}

    decision = {
        "action":        req.action,
        "modifications": req.modifications,
        "teacher_id":    current_user["user_id"],
    }

    try:
        # Command(resume=decision) 让图从 teacher_review_node 的 interrupt() 处继续
        result = await orchestrator.run(
            AgentType.EXAM,
            Command(resume=decision),
            config=config,
            enable_retry=False,
        )
    except Exception as e:
        logger.error("exam.confirm_failed", submission_id=submission_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"发布失败：{e}",
        )

    structured = result.get("structured_output", {}) or {}

    logger.info(
        "exam.published",
        submission_id=submission_id,
        teacher_id=current_user["user_id"],
        final_score=structured.get("final_score", 0),
    )

    return {
        "submission_id":       submission_id,
        "status":              "published",
        "final_score":         structured.get("final_score", 0),
        "full_score":          structured.get("full_score", 0),
        "score_rate":          structured.get("score_rate", 0),
        "weak_points":         structured.get("weak_points", []),
        "weak_points_summary": structured.get("weak_points_summary", ""),
    }
