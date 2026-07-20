# DataWork 黄金数据集

本目录保存发布前计算核心回归所使用的冻结数据与独立参考结果。

## 设计原则

- CSV 输入固定且带 SHA-256，防止基准数据被无意修改；
- 期望值来自 SciPy、statsmodels 或专项审查中列出的独立公式；
- 不调用 DataWork 的统计执行函数生成期望值；
- 同时覆盖默认路径和关键参数分支；
- 核心内部保留完整浮点精度，界面与报告仅负责格式化显示；
- 不允许因为当前输出变化而直接覆盖黄金期望值。

## 当前覆盖

- 29 个确定性 CSV；
- 52 个黄金案例；
- 425 个统计量、自由度、p 值、模型系数、拟合指标、CLD 或空值语义断言；
- 覆盖全部 47 个可执行统计方法；
- 额外覆盖多事后检验、加权 Kappa、McNemar 渐近模式和 MANOVA 推荐默认 Pillai。

详细审查见 `docs/GOLDEN_DATASET_AUDIT_0.4.9.md`。

## 运行

```bash
python scripts/run_golden_validation.py
pytest -q tests/unit/test_golden_datasets.py
```

筛选单个案例：

```bash
python scripts/run_golden_validation.py --case oneway_anova_default
```

## 更新规则

`scripts/build_golden_datasets.py` 只重建确定性 CSV，不会更新 `manifest.json`。任何参考值变更都必须：

1. 说明是数据变更、依赖库变更还是算法修复；
2. 使用独立参考实现重新计算；
3. 人工复核差异；
4. 更新专项审查文档；
5. 运行完整测试矩阵。
