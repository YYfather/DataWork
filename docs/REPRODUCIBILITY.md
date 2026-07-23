# 可复现性记录

## 开发期 R 对照

[`scripts/compare_r_reference.py`](../scripts/compare_r_reference.py) 使用 [`tests/reference/r/`](../tests/reference/r/) 中的固定数据与 R 脚本，对照派生列、专业拆分摘要及 Python 统计核心结果。R 与 Python 各自独立计算，再由对照入口比较统计量、自由度、p 值和派生结果。该链路仅用于开发期双重校对，不是应用运行、服务器部署或正式发布依赖。默认优先检测 `C:\Program Files\R\R-4.6.1\bin\Rscript.exe`，也可通过 `--rscript` 显式指定。

当前包含三套参考：

- [`derived_split_factor.csv`](../tests/reference/r/derived_split_factor.csv)：验证自定义列、专业拆分摘要和单因素 ANOVA，R 参考见 [`validate_derived_split_factor.R`](../tests/reference/r/validate_derived_split_factor.R)。
- [`agronomy_example_2.csv`](../tests/reference/r/agronomy_example_2.csv)：源自“测试数据2”，有效前 7 列与用户提供的农业数据一致；保留原始额外空列和一个噪声单元格，验证前 7 列读取、108 组 CK/T 配对、NDR/Delta 派生值、按年份拆分的 36 个 Type III 双因素 ANOVA 效应及 18 个 Wilks MANOVA 效应。R 参考见 [`validate_agronomy_example_2.R`](../tests/reference/r/validate_agronomy_example_2.R)，Python 应用服务回归见 [`test_agronomy_reference_dataset.py`](../tests/integration/test_agronomy_reference_dataset.py)。
- [`validate_pairing_abs_v16.R`](../tests/reference/r/validate_pairing_abs_v16.R)：使用 6 组正数、负数、零与缺失值，对照 `abs(T)`、`abs(CK)`、`abs(T-CK)` 和 `abs((T-CK)/CK)`。Python 比较入口为 [`compare_pairing_abs_r.py`](../scripts/compare_pairing_abs_r.py)。

此外，[`scripts/compare_all_methods_r.py`](../scripts/compare_all_methods_r.py) 会读取固定 golden manifest，调用 [`validate_all_methods.R`](../tests/reference/r/validate_all_methods.R)，逐一覆盖注册表中的全部 47 种可运行方法，使用独立 R 实现对照 Python 核心的统计量、p 值和自由度，并先检查方法集合完全一致。R 依赖安装在项目内忽略目录 `.r-validation-lib`，不进入运行依赖或发布包：

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
python scripts\compare_pairing_abs_r.py --rscript "C:\Program Files\R\R-4.6.1\bin\Rscript.exe"
```

V1.6 保留 V1.5 配对映射、联合因变量组和完整事后分支语义，并新增配对公式数学绝对值。2026-07-23 使用 R 4.6.1 完成验收：全部 47 种注册方法共比较 133 个字段，失败 0；农业参考数据得到 108 对，Python 与 R 对 36 个 Type III ANOVA 效应和 18 个 Wilks MANOVA 效应一致；V1.6 的 6 组绝对值数据、4 类公式逐项一致。联合因变量组、拆分与因素模型的任务展开由 Python 应用层验证，R 只提供独立统计值对照。

V1.7 在同日重新运行全部 47 个注册方法的独立 R 对照，方法集合检查与全部统计字段比较均通过。因变量自动组合本身是确定性的应用层任务展开，不改变单个 MANOVA 的数值定义；组合计数、稳定顺序、V1.5/V1.6 迁移、因素/拆分笛卡尔积、200/1000 阈值、API、报告和 Excel 标识由 Python 单元与集成测试验证。MANOVA 新增的秩与残差自由度检查只把原先含义不明的失败转换为明确错误，不修改可识别模型的统计量。

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
