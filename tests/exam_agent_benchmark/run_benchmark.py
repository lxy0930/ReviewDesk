"""Seed and run the Exam Agent benchmark with one test account.

The same test account submits all generated Word answer files. Each file
uses a different exam_id, so the database unique key (exam_id, user_id)
does not conflict. The script then fetches AI pre-review scores, compares them
with the human benchmark scores, and writes a concise Markdown report.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

import asyncpg
import httpx

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_settings

ROOT = Path(__file__).resolve().parent
GENERATED_DIR = ROOT / "generated"
DATASET_PATH = GENERATED_DIR / "benchmark_dataset.json"
MANIFEST_PATH = GENERATED_DIR / "manifest.json"
HUMAN_SCORES_PATH = GENERATED_DIR / "ground_truth" / "all_human_scores.csv"
RAW_RESULT_PATH = GENERATED_DIR / "benchmark_results.json"
REPORT_PATH = ROOT / "exam_agent_report.md"


def postgres_dsn() -> str:
    settings = get_settings()
    return (
        f"postgresql://{settings.db_user}:{settings.db_password}"
        f"@{settings.db_host}:{settings.db_port}/{settings.db_name}"
    )


def question_content_for_database(question: dict[str, Any]) -> str:
    """Append choice options because the questions table has no options column."""
    content = question["content"]
    options = question.get("options") or []
    if question["question_type"] not in {"single_choice", "multi_choice"}:
        return content
    if not options:
        return content

    option_lines = [
        f"{'ABCD'[index]}. {option}"
        for index, option in enumerate(options)
    ]
    return f"{content}\n\n选项：\n" + "\n".join(option_lines)


async def seed_questions(
    dataset: dict[str, Any],
    teacher_username: str,
) -> None:
    connection = await asyncpg.connect(postgres_dsn())
    try:
        teacher_id = await connection.fetchval(
            "SELECT id FROM users WHERE username = $1 LIMIT 1",
            teacher_username,
        )
        if teacher_id is None:
            raise RuntimeError(
                f"测试账号不存在：{teacher_username}，请先创建该账号"
            )

        for paper in dataset["papers"]:
            await connection.execute(
                """
                INSERT INTO exams (
                    id, title, description, created_by, is_active
                )
                VALUES ($1, $2, $3, $4, TRUE)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    created_by = EXCLUDED.created_by,
                    is_active = TRUE,
                    updated_at = NOW()
                """,
                uuid.UUID(paper["exam_id"]),
                f"IT 综合能力测试 {paper['paper_id']}",
                "ReviewDesk Exam Agent benchmark",
                teacher_id,
            )

            for question in paper["questions"]:
                await connection.execute(
                    """
                    INSERT INTO questions (
                        id, exam_id, question_no, question_type,
                        content, correct_answer, score, knowledge_tag
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (id) DO UPDATE SET
                        exam_id = EXCLUDED.exam_id,
                        question_no = EXCLUDED.question_no,
                        question_type = EXCLUDED.question_type,
                        content = EXCLUDED.content,
                        correct_answer = EXCLUDED.correct_answer,
                        score = EXCLUDED.score,
                        knowledge_tag = EXCLUDED.knowledge_tag
                    """,
                    uuid.UUID(question["question_id"]),
                    uuid.UUID(paper["exam_id"]),
                    question["question_no"],
                    question["question_type"],
                    question_content_for_database(question),
                    question["answer"],
                    question["max_score"],
                    question.get("knowledge_tag", ""),
                )

                for index, point in enumerate(
                    question.get("scoring_points", []),
                    start=1,
                ):
                    await connection.execute(
                        """
                        INSERT INTO scoring_points (
                            id, question_id, point_desc,
                            point_score, is_active
                        )
                        VALUES ($1, $2, $3, $4, TRUE)
                        ON CONFLICT (id) DO UPDATE SET
                            question_id = EXCLUDED.question_id,
                            point_desc = EXCLUDED.point_desc,
                            point_score = EXCLUDED.point_score,
                            is_active = TRUE
                        """,
                        uuid.uuid5(
                            uuid.UUID(question["question_id"]),
                            f"point:{index}",
                        ),
                        uuid.UUID(question["question_id"]),
                        point["desc"],
                        point["score"],
                    )
    finally:
        await connection.close()


def login(
    client: httpx.Client,
    base_url: str,
    username: str,
    password: str,
) -> str:
    response = client.post(
        f"{base_url}/auth/login",
        json={"username": username, "password": password},
    )
    response.raise_for_status()
    return response.json()["access_token"]


def submit(
    client: httpx.Client,
    base_url: str,
    token: str,
    exam_id: str,
    file_path: Path,
) -> str:
    with file_path.open("rb") as file:
        response = client.post(
            f"{base_url}/exam/submit",
            headers={"Authorization": f"Bearer {token}"},
            data={"exam_id": exam_id},
            files={
                "file": (
                    file_path.name,
                    file,
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document",
                )
            },
        )
    response.raise_for_status()
    return response.json()["submission_id"]


def wait_for_review(
    client: httpx.Client,
    base_url: str,
    token: str,
    submission_id: str,
    timeout_seconds: int,
) -> None:
    started = time.perf_counter()
    headers = {"Authorization": f"Bearer {token}"}

    while True:
        response = client.get(
            f"{base_url}/exam/my-submissions/{submission_id}",
            headers=headers,
        )
        response.raise_for_status()
        status = response.json()["status"]

        if status in {"pending_review", "published"}:
            return
        if status in {"submitted", "failed"}:
            raise RuntimeError(
                f"批改失败：submission_id={submission_id}, status={status}"
            )
        if time.perf_counter() - started > timeout_seconds:
            raise TimeoutError(
                f"批改超时：submission_id={submission_id}, status={status}"
            )
        time.sleep(1.0)


def fetch_ai_scores(
    client: httpx.Client,
    base_url: str,
    token: str,
    submission_id: str,
) -> dict[int, float]:
    response = client.get(
        f"{base_url}/exam/submissions/{submission_id}/review",
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    questions = response.json()["pre_review_summary"]["by_question"]
    return {
        int(item["question_no"]): float(item["score"])
        for item in questions
    }


def load_human_scores() -> dict[tuple[str, int], dict[str, Any]]:
    scores: dict[tuple[str, int], dict[str, Any]] = {}
    with HUMAN_SCORES_PATH.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            key = (row["case_id"], int(row["question_no"]))
            scores[key] = {
                **row,
                "question_no": int(row["question_no"]),
                "max_score": float(row["max_score"]),
                "human_score": float(row["human_score"]),
            }
    return scores


def save_raw_results(results: list[dict[str, Any]]) -> None:
    RAW_RESULT_PATH.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_report(results: list[dict[str, Any]]) -> str:
    diffs = [abs(item["human_score"] - item["ai_score"]) for item in results]
    overall_mae = statistics.fmean(diffs)

    by_type: dict[str, list[float]] = defaultdict(list)
    by_profile: dict[str, list[float]] = defaultdict(list)
    by_paper_elapsed: dict[str, float] = defaultdict(float)
    by_paper_human: dict[str, float] = defaultdict(float)
    by_paper_ai: dict[str, float] = defaultdict(float)
    for item in results:
        diff = abs(item["human_score"] - item["ai_score"])
        by_type[item["question_type"]].append(diff)
        by_profile[item["profile"]].append(diff)
        by_paper_elapsed[item["paper_id"]] += item["elapsed_seconds"]
        by_paper_human[item["paper_id"]] += item["human_score"]
        by_paper_ai[item["paper_id"]] += item["ai_score"]

    paper_count = len({item["paper_id"] for item in results})
    elapsed_seconds = sum(item["elapsed_seconds"] for item in results)
    effective_paper_times = [
        duration
        for duration in by_paper_elapsed.values()
        if duration >= 1.0
    ]
    average_paper_seconds = (
        statistics.fmean(effective_paper_times)
        if effective_paper_times
        else 0.0
    )
    fastest_paper_seconds = min(effective_paper_times, default=0.0)
    slowest_paper_seconds = max(effective_paper_times, default=0.0)
    paper_signed_errors = [
        by_paper_ai[paper_id] - by_paper_human[paper_id]
        for paper_id in by_paper_human
    ]
    mean_paper_absolute_error = statistics.fmean(
        abs(error) for error in paper_signed_errors
    )

    type_rows = "\n".join(
        f"| {question_type} | {statistics.fmean(values):.4f} |"
        for question_type, values in sorted(by_type.items())
    )
    profile_rows = "\n".join(
        f"| {profile} | {statistics.fmean(values):.4f} |"
        for profile, values in sorted(by_profile.items())
    )

    return f"""# Exam Agent 测试报告

## 测试指标

- 主指标：每份试卷平均绝对误差
- 公式：`mean(abs(AI试卷总分 - 人工试卷总分))`
- 满分：单选 3、多选 4、判断 2、简答 10、代码 12

## 测试数据

- 运行试卷：{paper_count} 份
- 逐题评分点：{len(results)} 个
- 每份试卷：8 单选 + 4 多选 + 3 判断 + 3 简答 + 2 代码
- 答卷难度：strong、mixed、weak 三档
- 题目来源：C-Eval、MMLU、HumanEval、MBPP 和本地题库
- 人工分数是 mock 基准分数，不是真实教师评分

## 测试结果

| 指标 | 结果 |
| --- | ---: |
| 每份试卷平均绝对误差 | {mean_paper_absolute_error:.2f} 分 |
| 逐题 MAE（辅助） | {overall_mae:.4f} 分/题 |
| 平均单份批改耗时 | {average_paper_seconds:.2f} 秒 |
| 最快单份批改耗时 | {fastest_paper_seconds:.2f} 秒 |
| 最慢单份批改耗时 | {slowest_paper_seconds:.2f} 秒 |
| 测试累计耗时 | {elapsed_seconds:.2f} 秒 |

### 分题型

| 题型 | MAE |
| --- | ---: |
{type_rows}

### 分答卷难度

| 难度 | MAE |
| --- | ---: |
{profile_rows}

## 如何测试

```powershell
# 1. 生成公开基准数据
python tests/exam_agent_benchmark/generate_benchmark.py --papers 100

# 2. 使用环境变量中的测试账号完成导入、提交、MAE 计算和报告生成
$env:BENCHMARK_USERNAME = "<test-user>"
$env:BENCHMARK_PASSWORD = "<test-password>"
python tests/exam_agent_benchmark/run_benchmark.py ^
  --papers 100
```

脚本使用同一个测试账号提交所有试卷；不同试卷使用不同 `exam_id`，不创建额外账号。
"""


def run(args: argparse.Namespace) -> None:
    if not DATASET_PATH.exists() or not MANIFEST_PATH.exists():
        raise SystemExit("请先运行 generate_benchmark.py")

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    human_scores = load_human_scores()
    profiles = {
        paper["paper_id"]: paper["profile"]
        for paper in dataset["papers"]
    }

    if not args.skip_seed:
        import asyncio

        asyncio.run(
            seed_questions(
                dataset,
                teacher_username=args.username,
            )
        )

    selected = manifest["papers"][: args.papers]
    results: list[dict[str, Any]] = []

    with httpx.Client(timeout=args.request_timeout) as client:
        token = login(
            client,
            args.base_url,
            args.username,
            args.password,
        )

        for index, paper in enumerate(selected, start=1):
            started = time.perf_counter()
            submission_id = submit(
                client,
                args.base_url,
                token,
                paper["exam_id"],
                GENERATED_DIR / paper["submission_file"],
            )
            wait_for_review(
                client,
                args.base_url,
                token,
                submission_id,
                args.grading_timeout,
            )
            ai_scores = fetch_ai_scores(
                client,
                args.base_url,
                token,
                submission_id,
            )
            elapsed = time.perf_counter() - started

            for question_no, ai_score in ai_scores.items():
                human = human_scores[(paper["case_id"], question_no)]
                results.append(
                    {
                        "paper_id": paper["paper_id"],
                        "case_id": paper["case_id"],
                        "submission_id": submission_id,
                        "question_no": question_no,
                        "question_type": human["question_type"],
                        "profile": profiles[paper["paper_id"]],
                        "max_score": human["max_score"],
                        "human_score": human["human_score"],
                        "ai_score": ai_score,
                        "elapsed_seconds": elapsed / len(ai_scores),
                    }
                )

            save_raw_results(results)
            current_mae = statistics.fmean(
                abs(item["human_score"] - item["ai_score"])
                for item in results
            )
            print(
                f"[{index}/{len(selected)}] {paper['paper_id']} "
                f"elapsed={elapsed:.2f}s mae={current_mae:.4f}"
            )

    REPORT_PATH.write_text(
        build_report(results),
        encoding="utf-8",
    )
    overall_mae = statistics.fmean(
        abs(item["human_score"] - item["ai_score"])
        for item in results
    )
    paper_human: dict[str, float] = defaultdict(float)
    paper_ai: dict[str, float] = defaultdict(float)
    for item in results:
        paper_human[item["paper_id"]] += item["human_score"]
        paper_ai[item["paper_id"]] += item["ai_score"]
    paper_mae = statistics.fmean(
        abs(paper_ai[paper_id] - paper_human[paper_id])
        for paper_id in paper_human
    )
    print(f"paper_mae={paper_mae:.4f}")
    print(f"question_mae={overall_mae:.4f}")
    print(f"report={REPORT_PATH}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument(
        "--username",
        default=os.getenv("BENCHMARK_USERNAME", ""),
    )
    parser.add_argument(
        "--password",
        default=os.getenv("BENCHMARK_PASSWORD", ""),
    )
    parser.add_argument("--papers", type=int, default=100)
    parser.add_argument("--request-timeout", type=float, default=60.0)
    parser.add_argument("--grading-timeout", type=int, default=600)
    parser.add_argument("--skip-seed", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    parsed_args = parse_args()
    if not parsed_args.username or not parsed_args.password:
        raise SystemExit(
            "请通过 BENCHMARK_USERNAME/BENCHMARK_PASSWORD 环境变量"
            "或 --username/--password 参数提供测试账号"
        )
    run(parsed_args)
