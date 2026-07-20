# 可复现性记录

每次运行自动生成：

- `run_id`；
- 分析计划规范化 JSON 的 SHA-256；
- 原始文件 SHA-256；
- 清洗后 DataFrame SHA-256；
- 文件大小、行列数、工作表名；
- 百分比转换等清洗日志；
- 完整运行参数；
- Python、操作系统、CPU 架构和关键依赖版本；
- 可选随机种子。

单次分析报告 ZIP 中包含：

```text
statistical_report.md
canonical_result.json
results.xlsx
reproducibility/
├── analysis_plan.json
├── provenance.json
└── environment.txt
```

DataWork 的哈希用于检测输入和计划变化，不等同于电子签名。正式受监管流程仍应使用版本控制、只读归档和组织级审计系统。
