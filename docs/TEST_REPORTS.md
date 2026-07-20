# DataWork 测试报告总档

本文件独立保存发布测试状态和历史验证入口。详细原始审计仍保留在对应版本文件中，避免在多个规范文档中复制结论。

## 1. 0.4.9 当前发布候选

验证日期：2026-07-21

| 维度 | 状态 | 结果/范围 | 入口 |
|---|---|---|---|
| 完整自动化回归 | 通过 | 260 passed | `pytest -q` |
| AI 上下文与前端契约 | 通过 | 55 passed | `tests/unit/test_ai_report_context.py`、AI API 与前端契约 |
| 结果时间戳交互回归 | 通过 | 31 passed | `tests/integration/test_frontend_interaction_contract.py` |
| 前端生产构建 | 通过 | Vue TypeScript 与 Vite 构建完成 | `npm run build` |
| 真实浏览器流程 | 通过 | 文件读取、Welch 分析、小助手证据范围切换；控制台无错误 | Playwright 本地审查 |
| 黄金数据 | 通过 | 52 个冻结案例、425 个参考断言 | `scripts/run_golden_validation.py` |
| 高级参数矩阵 | 通过 | 344 组参数变体 | `scripts/audit_method_parameters.py` |
| 数据结构矩阵 | 通过 | 387 组变体；190 个合法配置均成功 | `scripts/audit_data_variants.py` |
| 结构与版本一致性 | 通过 | 版本、方法/执行器、静态资源与发布必需文件 | `scripts/check_release_readiness.py` |
| 源码归档完整性 | 通过 | 文件级 SHA-256、ZIP SHA-256、缓存排除 | `scripts/package_source.py` |

说明：完整回归仅有 Starlette `TestClient` 关于未来 `httpx2` 迁移的上游弃用警告，不影响当前测试结论。

## 2. 测试维度覆盖

- 统计：t 检验、ANOVA/MANOVA、重复/混合设计、回归、分类数据、非参数、事后比较、CLD、效应量与前提检验。
- 数据：CSV/TSV/XLSX、编码、缺失、重复、常数、极端值、非法角色、拆分与批量组合。
- 工作流：即时分析、项目、计划修订、预检、运行、报告、下载、跨运行比较与旧状态失效。
- 报告：排序、三张规范表、效应量归并、校正前后语义、Guard、AI 回退与 canonical JSON。
- 安全：本地 AI 访问边界、密钥不回显、隐私过滤、数值一致性与推断层级守卫。
- 发布：版本一致性、前端静态资源、sidecar 契约、源码排除规则、清单与哈希。

## 3. 历史测试与审计索引

| 版本/主题 | 记录 |
|---|---|
| 0.4.9 计算核心复核 | `COMPUTATIONAL_CORE_REAUDIT_0.4.9.md` |
| 0.4.9 黄金数据 | `GOLDEN_DATASET_AUDIT_0.4.9.md` |
| 0.4.9 跨模型校正 | `CROSS_MODEL_CORRECTION_AUDIT_0.4.9.md` |
| 0.4.9 发布就绪 | `RELEASE_READINESS_AUDIT_0.4.9.md` |
| 0.4.8 参数、报告与交互 | `INTERACTION_REPORT_AUDIT_0.4.8.md`、`RELEASE_READINESS_AUDIT_0.4.8.md` |
| 0.4.7 MANOVA 固定方法与发布 | `MANOVA_FIXED_METHODS_AUDIT_0.4.7.md`、`RELEASE_READINESS_AUDIT_0.4.7.md` |
| 0.4.6 全链路与计算核心 | `RELEASE_READINESS_AUDIT_0.4.6.md` |
| 0.4.5 因素阶数、事后与 CLD | `FACTOR_ORDER_POSTHOC_CLD_AUDIT_0.4.5.md` |
| 0.4.4 ANOVA/MANOVA 组合 | `ANOVA_MANOVA_COMBINATION_AUDIT_0.4.4.md` |
| 0.4.3 MANOVA 与混合设计 | `MANOVA_MIXED_DESIGN_AUDIT_0.4.3.md` |
| 0.4.2 MANOVA | `MANOVA_AUDIT_0.4.2.md` |
| 0.4.1 全交互与全方法 | `INTERACTION_AUDIT.md` |
| 0.4.0 第三阶段最终审查 | `PHASE3_FINAL_AUDIT_RELEASE.md` |

## 4. 发布判定

源码发布门禁通过。Windows、macOS、Linux 原生安装包仍需分别在目标平台执行构建、签名和安装生命周期测试；该平台工作不由源码测试状态替代。
