# 可复现性记录

## 开发期 R 对照

`scripts/compare_r_reference.py` 使用 `tests/reference/r/` 中的固定数据与 R 脚本，对照派生列、专业拆分摘要及统计核心结果。该脚本仅用于开发审计，不是应用运行、服务器部署或正式发布依赖。默认优先检测 `C:\Program Files\R\R-4.6.1\bin\Rscript.exe`，也可通过 `--rscript` 显式指定。

当前包含两套参考：

- `derived_split_factor.csv`：验证自定义列、专业拆分摘要和单因素 ANOVA。
- `agronomy_example_2.csv`：源自“测试数据2”，保留原始额外空列和一个噪声单元格，验证前 7 列读取、108 组 CK/T 配对、NDR/Delta 派生值、按年份拆分的 36 个 Type III 双因素 ANOVA 效应及 18 个 Wilks MANOVA 效应。

此外，`scripts/compare_all_methods_r.py` 会读取固定 golden manifest，逐一覆盖注册表中的全部 47 种可运行方法，使用独立 R 实现对照 Python 核心的统计量、p 值和自由度，并先检查方法集合完全一致。R 依赖安装在项目内忽略目录 `.r-validation-lib`，不进入运行依赖或发布包：

```powershell
& "C:\Program Files\R\R-4.6.1\bin\Rscript.exe" scripts\install_r_validation_deps.R .
python scripts\compare_all_methods_r.py --rscript "C:\Program Files\R\R-4.6.1\bin\Rscript.exe"
$env:DATAWORK_RUN_R_REFERENCE="1"
$env:DATAWORK_RSCRIPT="C:\Program Files\R\R-4.6.1\bin\Rscript.exe"
python -m pytest tests\integration\test_r_all_methods_reference.py -q
```

农业参考 R 脚本只依赖 R 自带的 `stats`，以 Sum 对比和完整析因模型计算，不要求安装 `car`、`dplyr`、`readr` 或 `emmeans`。运行命令：

```powershell
python scripts\compare_r_reference.py --rscript "C:\Program Files\R\R-4.6.1\bin\Rscript.exe"
```

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
