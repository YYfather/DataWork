# DataWork 0.4.9 独立程序构建指南

## 1. 构建架构

DataWork 原生桌面程序由两部分组成：

1. `datawork-sidecar`：PyInstaller 打包的 Python/FastAPI/统计引擎；
2. Tauri 2 外壳：启动 sidecar、等待 `/api/health`，再加载本地网页界面。

网页静态资源已内置到 Python 包。独立程序不依赖外部浏览器服务器，也不需要用户安装 Python、Node.js 或统计依赖。

## 2. 不能伪交叉编译

PyInstaller 必须在目标操作系统上构建。Tauri 安装包也应在对应平台或官方 CI runner 上编译：

- Windows：Windows x64/ARM64 runner；
- macOS：对应 Intel 或 Apple Silicon runner；
- Linux：与目标 glibc、WebKitGTK 和包格式兼容的 runner。

Windows 生成的 `.exe` 不能由 Linux PyInstaller 可靠产生；macOS 应用签名、公证也只能在 macOS 环境完成。

## 3. 构建前检查

在仓库根目录执行：

```bash
python scripts/check_release_readiness.py
python -m pytest tests/unit/test_release_computational_audit.py -q
python -m pytest tests/integration/test_release_workflow.py -q
```

前端源码改变后执行：

```bash
cd frontend
npm ci --no-audit --no-fund
npm run build
cd ..
```

构建结果会复制到 `datawork/web/static/`。

## 4. 构建 Python sidecar

安装构建依赖：

```bash
python -m pip install -e '.[desktop-build]'
```

构建当前平台：

```bash
python scripts/build_release.py --skip-frontend
```

构建中断但 `dist/datawork-sidecar[.exe]` 已完整生成时，可复用产物补做哈希、冒烟和 Tauri 复制：

```bash
python scripts/build_release.py --skip-frontend --reuse-sidecar --tauri-target x86_64-pc-windows-msvc
```

构建脚本默认从源码目录之外启动 sidecar，并验证健康接口、46 个方法、一次真实 ANOVA 和报告 ZIP。只有在单独排查构建问题时才使用 `--skip-smoke`。

不使用 `--skip-frontend` 时，脚本会先运行前端生产构建。

产物：

```text
dist/datawork-sidecar        # Linux/macOS
dist/datawork-sidecar.exe    # Windows
```

脚本同时生成 `.sha256` 文件。

### Sidecar 冒烟测试

```bash
./dist/datawork-sidecar --host 127.0.0.1 --port 8876 --no-browser
```

另一个终端检查：

```bash
curl http://127.0.0.1:8876/api/health
curl http://127.0.0.1:8876/api/capabilities
```

也可直接运行自动化冒烟：

```bash
python scripts/smoke_sidecar.py dist/datawork-sidecar.exe --expected-version 0.4.9
```

还应上传一个小型 CSV，完成预检、分析和报告下载。发布级冒烟至少覆盖：

- 一个普通单变量模型；
- 一个双因素 MANOVA，确认四种多元统计量可用；
- 同时选择 Tukey 与 Duncan，确认分别生成 CLD；
- 工作区保存计划、运行并下载包含 Markdown 与 XLSX 的报告 ZIP；
- 根页面显示的版本号与 `/api/health` 一致。

## 5. 准备 Tauri externalBin

Tauri 要求文件名包含 target triple。可让构建脚本自动复制：

```bash
python scripts/build_release.py --skip-frontend --tauri-target x86_64-unknown-linux-gnu
```

常见名称：

```text
datawork-sidecar-x86_64-pc-windows-msvc.exe
datawork-sidecar-x86_64-apple-darwin
datawork-sidecar-aarch64-apple-darwin
datawork-sidecar-x86_64-unknown-linux-gnu
```

文件放入：

```text
desktop/src-tauri/binaries/
```

`desktop/src-tauri/tauri.conf.json` 的 `bundle.externalBin` 已配置为 `binaries/datawork-sidecar`。

## 6. 构建 Tauri 原生安装包

安装 Rust、平台 WebView 和 Tauri 依赖后：

```bash
cd desktop
npm ci --no-audit --no-fund
npm run build
```

Windows 构建前可用 `npx tauri info` 检查 WebView2、Rust/Cargo、MSVC Build Tools 和 Windows SDK。缺少其中任何一项时，不应把 sidecar 通过误写成安装包已经完成。

正式分发还需要：

- Windows：代码签名证书，验证 MSI/NSIS 安装、卸载和 SmartScreen 行为；
- macOS：Developer ID 签名、Hardened Runtime、公证和 stapling；
- Linux：在目标发行版测试 AppImage/deb/rpm、WebKitGTK 与文件选择器。

## 7. 生成 Windows 便携版

便携版不需要 Rust 或 MSVC，可直接封装已经通过冒烟的 sidecar：

```bash
python scripts/package_portable.py
```

产物位于 `dist/release/`，ZIP 内含重命名后的 `DataWork.exe`、使用说明和可执行文件 SHA-256；ZIP 本身也生成独立 `.sha256`。

## 8. Wheel 验证

Wheel 不是桌面安装包，但可验证 Python 包是否脱离源码目录运行：

```bash
python -m pip wheel . --no-deps -w wheelhouse
python -m pip install --no-deps --target /tmp/datawork-wheel-check wheelhouse/datawork-*.whl
PYTHONPATH=/tmp/datawork-wheel-check python -c   "import datawork; from importlib.resources import files; print(datawork.__version__); print(files('datawork.web').joinpath('static/index.html').is_file())"
```

## 9. 产物命名建议

```text
DataWork-v0.4.9-Full-Source.zip
DataWork-v0.4.9-<platform>-sidecar[.exe]
DataWork-v0.4.9-<platform>-installer.<ext>
DataWork-v0.4.9-RELEASE_READINESS_AUDIT.md
SHA256SUMS.txt
```

## 10. 安全与数据边界

- API 密钥不得写入源码、安装包或项目文件；
- AI 密钥使用系统密钥环或运行时输入；
- 默认只监听 `127.0.0.1`；开放局域网前必须评估身份验证、文件上传和数据合规；
- 安装包发布前进行恶意软件扫描、依赖漏洞扫描和签名验证；
- 用户项目数据库和报告目录必须位于可写用户目录，不能写入只读安装目录。

## 11. 当前审查边界

0.4.9 已验证 Python sidecar 构建、独立进程冒烟、Windows x64 便携包契约、内置生产前端和 Tauri 配置一致性。当前 Windows 审查环境没有 Rust/Cargo 和带 Windows SDK 的 MSVC Build Tools，因此不把“外壳源码完整”表述为“Tauri 原生安装包已经编译验证”。每个平台仍需按本指南完成原生构建、签名和安装冒烟测试。
