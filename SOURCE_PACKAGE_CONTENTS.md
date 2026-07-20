# DataWork 0.4.9 完整源码包说明

本压缩包是可继续开发、审计和在目标平台构建独立程序的完整工程源码，不是预编译的三系统安装包。

## 主要目录

- `datawork/`：统计引擎、计划/预检、应用服务、FastAPI、AI、工作区和报告源码；
- `frontend/`：Vue 3 + TypeScript 前端源码；
- `datawork/web/static/`：已通过生产构建的网页资源，普通 Python 启动不要求 Node.js；
- `desktop/`：Tauri 2 桌面外壳和 sidecar 契约；
- `packaging/`：PyInstaller spec；
- `tests/`：单元、集成、工作流和计算交叉验证测试；
- `scripts/`：安装、启动、参数/数据/浏览器审查、发布检查和构建脚本；
- `docs/`：用户、统计方法、AI、架构、打包、发布清单及各版本审查；
- `examples/`：示例数据；
- `.github/workflows/`：CI 配置；
- `pyproject.toml`：Python 依赖和命令入口；
- `SOURCE_MANIFEST_SHA256.txt`：源码文件 SHA-256 清单。

文档采用分层治理：`docs/PROJECT_STANDARD.md` 为统一工程规范，`docs/TEST_REPORTS.md` 独立归档测试状态，`docs/DEVELOPMENT_LOG.md` 保存开发决策，根目录 `CHANGELOG.md` 汇总全部版本变动，`docs/RELEASE_MANIFEST.md` 记录发布包含/排除范围。

## 0.4.9 发布重点

- `golden_datasets/`：冻结输入、哈希、52 个案例和 425 个参考断言；
- `scripts/run_golden_validation.py`：可独立运行黄金验证；
- `tests/unit/test_golden_datasets.py`：黄金数据纳入常规回归；
- `docs/GOLDEN_DATASET_AUDIT_0.4.9.md`：计算核心参考、发现与修复；
- `docs/USABILITY_OPTIMIZATION_0.4.9.md`：简洁/专业参数层级与选项解释；
- `docs/RELEASE_READINESS_AUDIT_0.4.9.md`：发布验证结论。

## 0.4.8 发布重点

- MANOVA 拆分为单因素、双因素、三因素三个固定入口；
- 修复必要设置误报和特殊因素名交互解析；
- 固定阶数组合实验不再展示最小/最大阶数；
- 保留旧统一 MANOVA 计划自动迁移。
- 全工作流、交互、数据一致性和参数传递审查；
- t 检验、秩检验、Dunn、Logistic、重复测量和 MANOVA 校正核心修复；
- Tukey、Type III ANOVA、MANOVA 和 Logistic 独立参考交叉验证；
- ANOVA/MANOVA 因素阶数、组合实验、事后检验多选和 CLD；
- 独立 sidecar 构建脚本、发布就绪检查、打包指南和发布清单。

## 包内不包含

- `node_modules`；
- Python、pytest、Vite 缓存；
- 本地虚拟环境；
- 本机构建的 `build/`、`dist/`；
- `.audit`、`.tmp`、`.ui-*` 和测试临时工作区；
- 本地平台 sidecar（须在目标平台重新构建）；
- API 密钥、用户数据库和临时工作目录；
- 未经目标平台编译和签名的原生安装包。

## 开发安装

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e '.[dev]'
pytest -q
```

## 发布前检查

```bash
python scripts/check_release_readiness.py
python scripts/audit_method_parameters.py
python scripts/audit_data_variants.py
```

独立程序构建请阅读 `docs/PACKAGING.md`；正式发布逐项检查请阅读 `docs/RELEASE_CHECKLIST.md`。
