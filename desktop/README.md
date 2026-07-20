# DataWork Tauri 2 桌面外壳

该目录提供 Windows、Linux、macOS 共用的 Tauri 2 外壳。桌面程序启动由 PyInstaller 生成的 `datawork-sidecar`，等待 `/api/health` 可用后，再加载同一套 DataWork 网页界面。

## 构建原则

- 必须在目标操作系统原生构建，不进行伪交叉编译；
- 先在仓库根目录运行 `scripts/check_release_readiness.py`；
- 运行 `scripts/build_release.py` 生成当前平台 Python sidecar；
- 将 sidecar 复制为 Tauri target triple 名称；
- 安装 Rust、系统 WebView 和 Tauri 依赖后，在本目录运行 `npm ci && npm run build`；
- Windows/macOS 正式分发配置代码签名和公证；Linux 按目标发行版测试 AppImage/deb/rpm。

## 快速流程

```bash
# 仓库根目录
python -m pip install -e '.[desktop-build]'
python scripts/check_release_readiness.py
python scripts/build_release.py --skip-frontend   --tauri-target x86_64-unknown-linux-gnu

cd desktop
npm ci --no-audit --no-fund
npm run build
```

Windows/macOS 请把 target triple 替换为对应值。完整说明见根目录 `docs/PACKAGING.md`。

## 验证要求

在 Tauri 打包前先直接启动 sidecar 并验证：

- `/api/health`；
- `/api/capabilities`；
- CSV/XLSX 读取；
- 预检和至少一种统计分析；
- Markdown/Excel 报告下载；
- 中文路径与用户可写目录。

当前仓库交付可审计外壳源码和 sidecar 契约。0.4.6 审查环境没有 Rust 工具链，因此不伪造未经编译验证的三系统安装包；每个平台必须按发布清单完成原生验证。
