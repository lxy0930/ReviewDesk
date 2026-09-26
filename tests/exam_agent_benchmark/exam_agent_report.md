# Exam Agent 测试报告

## 测试指标

- 主指标：每份试卷平均绝对误差
- 公式：`mean(abs(AI试卷总分 - 人工试卷总分))`
- 满分：单选 3、多选 4、判断 2、简答 10、代码 12

## 测试数据

- 运行试卷：100 份
- 逐题评分点：2000 个
- 每份试卷：8 单选 + 4 多选 + 3 判断 + 3 简答 + 2 代码
- 答卷难度：strong、mixed、weak 三档
- 题目来源：C-Eval、MMLU、HumanEval、MBPP 和本地题库
- 人工分数是 mock 基准分数，不是真实教师评分

## 测试结果

| 指标 | 结果 |
| --- | ---: |
| 每份试卷平均绝对误差 | 2.61 分 |
| 逐题 MAE（辅助） | 0.3505 分/题 |
| 平均单份批改耗时 | 8.78 秒 |
| 最快单份批改耗时 | 3.15 秒 |
| 最慢单份批改耗时 | 20.61 秒 |
| 测试累计耗时 | 869.10 秒 |

### 分题型

| 题型 | MAE |
| --- | ---: |
| code | 2.0650 |
| judge | 0.0000 |
| multi_choice | 0.0000 |
| short_answer | 0.9400 |
| single_choice | 0.0075 |

### 分答卷难度

| 难度 | MAE |
| --- | ---: |
| mixed | 0.9727 |
| strong | 0.0868 |
| weak | 0.0000 |

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
