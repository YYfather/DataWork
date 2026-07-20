# DataWork 0.4.9 发布清单

生成日期：2026-07-21

## 发布对象

- 类型：完整源码发布包
- 版本：0.4.9
- Python：3.11+
- 前端：Vue 3 + TypeScript + Vite
- 桌面：Tauri 2（目标平台原生构建）

## 发布门禁

- [x] 版本号在 VERSION、Python、前端、桌面、Tauri 与 Cargo 中一致
- [x] 生产前端已重新构建
- [x] 完整自动化测试通过
- [x] 黄金数据、参数矩阵与数据变体审计通过
- [x] TODO/FIXME/HACK/XXX 扫描完成，业务源码无遗留项
- [x] 未使用导入与完全重复文档已清理
- [x] 缓存、日志、截图、临时工作区、旧 dist 与旧 sidecar 已从发布源剥离
- [x] 测试报告、开发日志与全局 Changelog 独立保留
- [x] 源码 ZIP 包含文件级 SHA-256 清单，并生成 ZIP SHA-256

## 包含

统计源码、Web API、前端源码及生产静态资源、Tauri 配置、黄金数据、完整测试、构建/审计脚本、用户手册、项目规范、测试总档、开发日志和 Changelog。

## 排除

`.venv`、`node_modules`、Rust `target`、pytest/Python/Vite 缓存、`.audit`、`.tmp`、`.ui-*`、旧 `dist`、平台 sidecar、用户数据库、API 密钥和本地报告工作区。

## 标准目录树

```text
DataWork-v0.4.9-Full-Source/
├─ datawork/
│  ├─ ai/ application/ core/ design/ engine/
│  ├─ infrastructure/ io/ report/ rules/ web/
│  └─ cli.py
├─ frontend/src/
├─ desktop/src-tauri/
├─ golden_datasets/
├─ tests/
├─ scripts/
├─ packaging/
├─ docs/
│  ├─ PROJECT_STANDARD.md
│  ├─ USER_MANUAL.md
│  ├─ STATISTICAL_METHODS.md
│  ├─ TEST_REPORTS.md
│  ├─ DEVELOPMENT_LOG.md
│  ├─ TECHNICAL_DEBT_REPORT.md
│  └─ RELEASE_MANIFEST.md
├─ examples/
├─ .github/workflows/
├─ CHANGELOG.md
├─ README.md
├─ pyproject.toml
└─ VERSION
```

## 构建与校验

```bash
python scripts/check_release_readiness.py
python -m pytest -q
python scripts/run_golden_validation.py
python scripts/audit_method_parameters.py
python scripts/audit_data_variants.py
python scripts/clean_release_workspace.py --apply
python scripts/package_source.py --output-dir dist/release
python scripts/generate_release_manifest.py --release-dir dist/release
```

最终 ZIP 名称、文件数量、大小和 SHA-256 由归档脚本在 `dist/release/RELEASE_MANIFEST.json` 中生成，标准目录树写入 `dist/release/RELEASE_TREE.txt`；包内 `SOURCE_MANIFEST_SHA256.txt` 用于逐文件验证。
