import asyncio
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import text

from backend.core.logger import get_logger
from backend.core.orchestrator import AgentType, get_orchestrator
from backend.dependencies import AsyncSessionLocal, get_current_user

router = APIRouter()
logger = get_logger(__name__)

orchestrator = get_orchestrator()

# ── GC 保护：模块级集合持有后台任务的强引用，防止被垃圾回收 ──
_background_tasks: set[asyncio.Task] = set()
RESUME_REVIEW_TIMEOUT_SECONDS = 15 * 60          # 审查超时阈值：15 分钟


async def _mark_review_failed(review_id: str, error_msg: str) -> None:
    """把仍处于 processing 的记录标记为 failed（幂等：仅当当前是 processing 才改）。"""
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                UPDATE resume_reviews
                SET status = 'failed', error_msg = :error_msg, updated_at = NOW()
                WHERE id = :review_id AND status = 'processing'
            """),
            {"review_id": review_id, "error_msg": error_msg[:1000]},
        )
        await session.commit()


@router.post("/upload", status_code=202)         # 202 Accepted：已接受、正在处理
async def upload_resume(
    file: UploadFile = File(...),                # 上传的文件
    target_position: str = Form("", description="目标岗位名称"),
    job_description: str = Form(..., description="目标岗位完整描述"),
    current_user: dict = Depends(get_current_user),   # 鉴权：拿到当前用户
):
    """上传 PDF 简历，触发异步审查，立即返回 review_id。"""
    if not file.filename.lower().endswith(".pdf"):       # 只收 PDF
        raise HTTPException(status_code=400, detail="仅支持 PDF 格式")

    target_position = target_position.strip()
    job_description = job_description.strip()
    if not job_description:
        raise HTTPException(status_code=400, detail="请填写目标岗位描述")
    if len(job_description) > 5000:
        raise HTTPException(status_code=400, detail="目标岗位描述不能超过 5000 字")

    review_id  = str(uuid.uuid4())
    student_id = current_user["user_id"]

    # 1. 读取并校验文件（用 await 读，避免阻塞事件循环）
    MAX_PDF_SIZE = 20 * 1024 * 1024              # 20MB 上限
    file_bytes = await file.read()
    if len(file_bytes) > MAX_PDF_SIZE:
        raise HTTPException(status_code=413, detail="文件过大，最大支持 20MB")
    if not file_bytes:
        raise HTTPException(status_code=400, detail="上传文件为空")

    # 暂存到临时目录
    import tempfile
    tmp_path = os.path.join(tempfile.gettempdir(), f"{review_id}_upload.pdf")
    with open(tmp_path, "wb") as f:
        f.write(file_bytes)
    logger.info("upload_resume.file_saved", review_id=review_id, tmp_path=tmp_path)

    # 2. 写入 resume_reviews 初始记录（status=processing）
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO resume_reviews (
                    id, student_id, pdf_minio_path,
                    target_position, job_description, status
                )
                VALUES (
                    :id, :student_id, :pdf_minio_path,
                    :target_position, :job_description, 'processing'
                )
            """),
            {"id": review_id, "student_id": student_id,
             "pdf_minio_path": f"resumes/{student_id}/{review_id}.pdf",
             "target_position": target_position,
             "job_description": job_description},
        )
        await session.commit()

    # 3. 准备初始 State，后台启动图执行
    initial_state = {
        "messages": [], "student_id": student_id,
        "review_id": review_id, "pdf_minio_path": "", "pdf_local_path": tmp_path,
        "target_position": target_position, "job_description": job_description,
        "raw_text": "", "page_count": 0, "structured": None,
        "dimension_scores": [], "weighted_score": 0.0, "issues": [],
        "summary": None, "fallback_used": False, "structured_output": None,
    }

    def _on_task_done(t: asyncio.Task):
        """任务结束回调：移除引用、清理临时文件、失败则标记 failed。"""
        _background_tasks.discard(t)                  # 从集合移除（释放强引用）
        if os.path.exists(tmp_path):                  # 清理临时 PDF
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        mark_failed_msg = None
        if t.cancelled():                             # 任务被取消（如服务重启）
            mark_failed_msg = "审查任务被服务重启中断，请重试。"
            logger.warning("resume.background_task_cancelled", review_id=review_id)
        else:
            exc = t.exception()                       # 任务抛了异常
            if exc:
                mark_failed_msg = f"审查任务执行失败：{exc}"
                logger.error("resume.background_task_failed", review_id=review_id,
                             error=str(exc), exc_info=exc)
        if mark_failed_msg:                           # 异步把记录标记为 failed
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_mark_review_failed(review_id, mark_failed_msg))
            except RuntimeError:
                pass                                  # 循环已关闭：下次查询走超时兜底

    task = asyncio.create_task(
        orchestrator.run(AgentType.RESUME, initial_state)
    )
    _background_tasks.add(task)                       # GC 保护：持有强引用
    task.add_done_callback(_on_task_done)             # 注册完成回调
    logger.info("upload_resume.task_started", review_id=review_id)

    return {                                          # 立即返回（不等审查完成）
        "review_id": review_id, "status": "processing",
        "message": "简历已上传，正在审查中，预计 30-60 秒完成。",
    }


@router.get("/reviews/{review_id}")
async def get_review(review_id: str, current_user: dict = Depends(get_current_user)):
    """查询审查状态/结果。processing / done / failed / 404。"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, status, scores, issues, summary, error_msg,
                       target_position, job_description, created_at, updated_at
                FROM resume_reviews
                WHERE id = :review_id AND student_id = :student_id
            """),
            {"review_id": review_id, "student_id": current_user["user_id"]},
        )
        row = result.mappings().fetchone()

    if not row:                                       # 不存在或不属于自己
        raise HTTPException(status_code=404, detail="审查记录不存在")

    if row["status"] == "processing":
        # 超时兜底：防止后台任务中断后长期卡 processing
        last_ts = row["updated_at"] or row["created_at"]
        if isinstance(last_ts, datetime):
            elapsed = (datetime.now(timezone.utc) - last_ts).total_seconds()
            if elapsed >= RESUME_REVIEW_TIMEOUT_SECONDS:
                timeout_msg = "审查任务超时或被中断，请重新上传后重试。"
                await _mark_review_failed(review_id, timeout_msg)
                return {"review_id": review_id, "status": "failed", "error_msg": timeout_msg}
        return {"review_id": review_id, "status": "processing"}

    if row["status"] == "failed":
        return {"review_id": review_id, "status": "failed",
                "error_msg": row.get("error_msg") or "审查任务失败，请重新上传。"}

    # status == done：JSONB 列已被 asyncpg 自动反序列化为 dict/list，无需 json.loads
    def _to_dict(v):
        if v is None:
            return {}
        if isinstance(v, (dict, list)):
            return v
        import json as _json
        return _json.loads(v)

    scores_data = _to_dict(row["scores"])
    return {
        "review_id": review_id, "status": "done",
        "target_position": row["target_position"] or "",
        "job_description": row["job_description"] or "",
        "weighted_score": scores_data.get("weighted_score", 0),
        "dimension_scores": scores_data.get("dimension_scores", []),
        "issues": _to_dict(row["issues"]) if not isinstance(row["issues"], list) else row["issues"],
        "summary": _to_dict(row["summary"]),
    }


@router.delete("/reviews/{review_id}", status_code=204)
async def delete_review(review_id: str, current_user: dict = Depends(get_current_user)):
    """删除审查记录（WHERE 带 student_id，只能删自己的）。"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                DELETE FROM resume_reviews
                WHERE id = :review_id AND student_id = :student_id
            """),
            {"review_id": review_id, "student_id": current_user["user_id"]},
        )
        await session.commit()
    if result.rowcount == 0:                          # 没删到任何行 = 不存在/无权限
        raise HTTPException(status_code=404, detail="记录不存在")


@router.get("/reviews")
async def list_reviews(current_user: dict = Depends(get_current_user)):
    """列出本人历史审查记录（摘要，按时间倒序）。"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, status, target_position, created_at,
                       (scores::jsonb ->> 'weighted_score')::float AS weighted_score
                FROM resume_reviews
                WHERE student_id = :student_id
                ORDER BY created_at DESC
                LIMIT 50
            """),
            {"student_id": current_user["user_id"]},
        )
        rows = result.mappings().all()

    items = [
        {"review_id": row["id"], "status": row["status"],
         "target_position": row["target_position"] or "",
         "created_at": row["created_at"].isoformat() if row["created_at"] else None,
         "weighted_score": row["weighted_score"]}
        for row in rows
    ]
    return {"items": items, "total": len(items)}
