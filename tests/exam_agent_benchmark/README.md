# Exam Agent Benchmark

这个目录用于对 ReviewDesk 的 Exam Agent 做可重复的 MAE 评测。

## 基准结构

默认生成 100 份试卷，每份试卷 20 题，共 2000 个题目评分点：

```text
8 道单选   <- C-Eval / MMLU
4 道多选   <- 由 C-Eval / MMLU 同科目选项自动合成
3 道判断   <- 本地固定 IT 知识题库
3 道简答   <- 本地固定 IT 知识题库，每题 10 分
2 道代码   <- HumanEval / MBPP
```

每份试卷包含：

- 一份带标准答案、得分点和参考代码的试卷；
- 一份 mock 学生答卷；
- 一份逐题人工分数，作为 `T_i`；
- AI 批改结果作为 `A_i`；
- 主指标是每份试卷平均绝对误差：

```text
mean(abs(AI试卷总分 - 人工试卷总分))
```

## 数据来源

- [C-Eval](https://huggingface.co/datasets/ceval/ceval-exam)
- [MMLU](https://huggingface.co/datasets/cais/mmlu)
- [HumanEval](https://huggingface.co/datasets/openai/openai_humaneval)
- [MBPP](https://huggingface.co/datasets/google-research-datasets/mbpp)

公开数据集只作为题目来源和工程测试数据使用。正式发布或商用前，需要核对各数据集自身的许可证和引用要求。

## 生成数据

在项目根目录执行：

```powershell
python tests/exam_agent_benchmark/generate_benchmark.py
```

生成目录：

```text
tests/exam_agent_benchmark/generated/
├── exam_papers/                 # 100 份试卷 docx
├── answer_keys/                 # 100 份标准答案 JSON
├── submissions/                 # 100 份 mock 学生 Word 答卷
├── ground_truth/
│   └── all_human_scores.csv     # T_i
├── benchmark_dataset.json
└── manifest.json
```

生成结果是确定性的，同一个 `--seed` 会产生相同数据。

## 运行 Exam Agent

后端启动后，使用测试学生账号执行：

```powershell
$env:BENCHMARK_USERNAME = "<test-user>"
$env:BENCHMARK_PASSWORD = "<test-password>"
python tests/exam_agent_benchmark/run_benchmark.py --papers 100
```

脚本会：

1. 导入 100 份试卷和 2000 道题目；
2. 使用同一个测试账号上传 100 份 Word 答卷；
3. 等待每份试卷进入 `pending_review`；
4. 读取 AI 预批改逐题分数；
5. 计算 MAE 并生成 `exam_agent_report.md`。

该步骤会真实调用 LLM，100 份试卷运行时间较长并会产生 API 成本。

如需自定义账号：

```powershell
python tests/exam_agent_benchmark/run_benchmark.py `
  --username <test-user> `
  --password <test-password> `
  --papers 10
```

测试报告会覆盖更新：

```text
tests/exam_agent_benchmark/exam_agent_report.md
```

## 注意

- 多选和判断属于测试基准合成题，不应声称全部来自公开数据集；
- 简答题和代码题的 `T_i` 是人工 mock 分数，不代表真实教师评分；
- 该数据集适合做回归和 MAE 基线，不等价于公开学术 benchmark；
- 运行 100 份试卷前，建议先用 `--papers 5` 生成小规模冒烟数据。
