# DataWork 发布与部署指南

统一收录源码、桌面端、跨平台包、发布检查和部署说明。个人网站专用部署材料只随网站部署包交付。

> 本文件由同类历史文档完整合并而成；下列“原文档”标题用于保留历史来源。


---

## 原文档：CROSS_PLATFORM.md

# 跨平台与部署说明

## 本地模式

Windows、Linux、macOS 均运行同一个 FastAPI 服务并通过系统浏览器访问。统计核心、API 和工作区格式完全一致。

```bash
datawork-web
```

便携模式：

```bash
datawork-web --workspace ./DataWorkWorkspace
```

项目数据使用相对路径，因此整个工作区可整体备份或迁移。迁移前应停止 DataWork，避免复制正在写入的 SQLite/WAL 文件。

## 默认工作区

- Windows：`%LOCALAPPDATA%\DataWork`
- macOS：`~/Library/Application Support/DataWork`
- Linux：`${XDG_DATA_HOME:-~/.local/share}/datawork`

路径全部使用 `pathlib.Path`，源文件名只用于显示，实际存储使用生成的 ID，避免路径穿越和跨系统非法字符。

## 文件和数据库

- CSV 尝试 UTF-8 BOM、UTF-8、GB18030、GBK；
- 自动识别逗号、制表符和分号；
- 上传大小默认限制为 100 MB；
- 原始文件先写临时文件，再原子替换；
- SQLite 开启外键、事务和 WAL；
- 工作区带 Schema 版本；
- 运行和报告前后校验 SHA-256。

## 服务器模式

```bash
datawork-web --host 0.0.0.0 --no-browser
```

生产环境应配置：

- Nginx/Caddy/企业网关；
- HTTPS；
- 身份认证和项目级授权；
- 上传、存储和备份策略；
- 单独的后台任务进程；
- 日志、审计和限流。

当前工作区 API 默认面向本机或受信任网络，不应直接暴露在公网。

## CI 和发布

`.github/workflows/ci.yml` 覆盖：

- Windows、Ubuntu、macOS；
- Python 3.11、3.12、3.13；
- Vue 生产构建；
- Python wheel/sdist 构建。

PyInstaller 仍需在目标系统原生构建，不能用 Linux 生成可信的 Windows/macOS 可执行文件。

## Tauri

Tauri 2 将只承担窗口、系统菜单、安装、签名、自动更新和 Python sidecar 生命周期，不重写 Vue 或统计核心。接入前需要先完成长任务队列、端口认证和进程退出清理。

---

## 原文档：DESKTOP_PACKAGING_PREPARATION_0.4.9.md

# DataWork 0.4.9 独立程序准备记录

准备日期：2026-07-21

## 已完成

- 前端生产资源已内置到 Python 包；
- PyInstaller Windows x64 单文件 sidecar 构建完成；
- sidecar 已复制为 Tauri externalBin 所需 target triple 名称；
- 从源码目录之外启动 sidecar，验证 `/api/health`、46 个统计方法、真实单因素 ANOVA 和完整报告 ZIP；
- 生成 Windows x64 便携 ZIP，并从解压后的 `DataWork.exe` 再次完成同一冒烟；
- 生成并验证 Python wheel，静态前端和报告模板均可从安装目录读取；
- 新增 `desktop/package-lock.json`，桌面 Node 依赖可由 `npm ci` 复现；
- 发布检查会要求 sidecar 冒烟脚本、便携打包脚本和桌面锁文件存在；
- 源码包排除平台 sidecar、`node_modules`、Rust `target`、`dist` 和 `build`。
- Windows 安装器固定为简体中文，NSIS 保留安装目录选择页面；
- Tauri 桌面窗口启动时默认最大化；
- 使用独立的全新 Cargo target 完成 Windows x64 MSI 与 NSIS release 构建。

## 当前产物

| 产物 | SHA-256 |
|---|---|
| `dist/datawork-sidecar.exe` | `724a36ae2bdd5ee5072cc79740c9b808aa3413dd2ab7f3c46c36335cf8baebf7` |
| `dist/release/DataWork-v0.4.9-Windows-x64-中文便携版.zip` | `d39a907c51dc729efd9012f2760941f08a91fa87598a14ef4cf7126f93c19d6b` |
| `dist/release/DataWork-v0.4.9-Windows-x64-中文安装版.exe` | `72537fe0667de9411a31ba782e51f379fa41fa79cf102790aa6c05dc8975ffa9` |
| `dist/release/DataWork-v0.4.9-Windows-x64-中文安装版.msi` | `f5052d0cc25b1dbf6b8c145d853ec60e9247eadb460edd72374c826fdd716f91` |

便携 ZIP 内的 `DataWork.exe` 与 sidecar 二进制完全一致，包内 `SHA256SUMS.txt` 已复核。
Tauri externalBin 与 `dist/datawork-sidecar.exe` 的 SHA-256 完全一致。

## 原生安装包状态

Windows 构建环境已具备 Rust、Cargo、Visual Studio 2022 Build Tools、MSVC 19.44、
MSBuild 17.14 和 Windows SDK 10.0.26100。全新隔离构建已生成：

- `DataWork_0.4.9_x64_zh-CN.msi`；
- `DataWork_0.4.9_x64-setup.exe`。

NSIS 生成脚本已复核包含简体中文语言资源和安装目录选择页面。当前安装包未使用
Authenticode 代码签名，因此个人测试可直接使用，公开分发前仍应配置签名证书并完成
安装、升级、卸载与 SmartScreen 验证。

复现命令：

```powershell
python scripts/build_release.py --skip-frontend --reuse-sidecar --tauri-target x86_64-pc-windows-msvc
Set-Location desktop
npm ci --no-audit --no-fund
npm run build
```

正式发布仍需完成安装、升级、卸载、中文路径、无网络启动、代码签名、SmartScreen 和恶意软件扫描。

## 验证命令

```powershell
python scripts/smoke_sidecar.py dist/datawork-sidecar.exe --expected-version 0.4.9
python scripts/package_portable.py
python scripts/check_release_readiness.py
python -m pytest tests/integration/test_desktop_scaffold.py tests/integration/test_release_workflow.py -q
```

---

## 原文档：PACKAGING.md

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

Windows 安装器固定使用简体中文。NSIS 安装器面向当前用户安装，不要求管理员权限，
并保留安装目录选择页面；Tauri 桌面窗口启动时默认最大化。MSI 使用 `zh-CN`，NSIS
使用 `SimpChinese`，相关配置位于 `desktop/src-tauri/tauri.conf.json`。

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

产物位于 `dist/release/`，文件名以 `中文便携版.zip` 结尾。ZIP 内含重命名后的
`DataWork.exe`、中文使用说明和可执行文件 SHA-256；ZIP 本身也生成独立 `.sha256`。
便携版不执行安装，可解压到任意有写权限的位置。

## 8. 生成分平台中文发布包

当前发布策略不生成 macOS DMG，也不把不同平台文件混在同一个压缩包中。Windows
使用中文 NSIS Setup，macOS 使用中文 `.command` 命令包，Linux 使用单用户服务器包，
另行提供完整源码包：

```bash
python scripts/package_platform_releases.py
```

固定产物名称：

```text
datework_window_setup.exe
datework_macos_command.zip
datework_linux_server.zip
datework_source.zip
```

Linux 服务器包是面向宝塔面板的纯文件包，只包含运行源码、静态资源、依赖清单、
固定监听 `127.0.0.1` 的启动入口和中文说明，不包含 Docker、systemd 或自动改配置
脚本。服务器部署支持最多 3 个单进程匿名会话，并对持久项目工作区实施所有者密码
认证；即时分析仍可公开使用。不得把 8765 端口直接暴露到公网，通过域名访问必须使用
HTTPS，并保持 Supervisor 单进程。详细说明见
`docs/PLATFORM_PACKAGES.md` 和包内 `宝塔面板部署说明.txt`。

将当前个人主页副本与 DataWork 组合为 `/datework/` 完整部署包时，单独执行：

```powershell
python scripts/package_homepage_subproject.py --homepage-root "E:\studywork\Web"
```

该命令保持个人主页源目录只读，只修改压缩包内的主页副本，生成
`datework_homepage_subproject_deploy.zip` 及其 `.sha256`。

## 9. Wheel 验证

Wheel 不是桌面安装包，但可验证 Python 包是否脱离源码目录运行：

```bash
python -m pip wheel . --no-deps -w wheelhouse
python -m pip install --no-deps --target /tmp/datawork-wheel-check wheelhouse/datawork-*.whl
PYTHONPATH=/tmp/datawork-wheel-check python -c   "import datawork; from importlib.resources import files; print(datawork.__version__); print(files('datawork.web').joinpath('static/index.html').is_file())"
```

## 10. 产物命名

```text
datework_window_setup.exe
datework_macos_command.zip
datework_linux_server.zip
datework_source.zip
*.sha256
```

## 11. 安全与数据边界

- API 密钥不得写入源码、安装包或项目文件；
- AI 密钥使用系统密钥环或运行时输入；
- 默认只监听 `127.0.0.1`；开放局域网前必须评估身份验证、文件上传和数据合规；
- 安装包发布前进行恶意软件扫描、依赖漏洞扫描和签名验证；
- 用户项目数据库和报告目录必须位于可写用户目录，不能写入只读安装目录。

## 12. 当前审查边界

0.4.9 已验证 Python sidecar 构建、独立进程冒烟、Windows x64 中文便携包、
简体中文 NSIS 安装器、`zh-CN` MSI、内置生产前端和 Tauri 配置一致性。
Windows 安装包尚未进行 Authenticode 签名和真实安装/升级/卸载验证。macOS 当前只
提供需要 Python 3.11+ 的命令包，不提供 DMG；Linux 提供宝塔纯文件服务器包，仍应
在用户实际服务器发行版、独立虚拟环境和 Nginx 反向代理下完成部署验证。

---

## 原文档：PLATFORM_PACKAGES.md

# DataWork 分平台中文发布包

DataWork 0.4.9 采用按使用场景拆分的发布方式，不把不同平台文件混在同一个压缩包中。

## 发布文件

| 文件 | 用途 |
|---|---|
| `datework_window_setup.exe` | Windows x64 中文 Setup，可选择安装目录，当前用户安装 |
| `datework_macos_command.zip` | macOS 中文命令包，使用 Python 3.11+ 本地安装和启动 |
| `datework_linux_server.zip` | Linux 单用户纯文件服务器包，包含宝塔中文部署说明和独立启动入口 |
| `datework_homepage_subproject_deploy.zip` | 将 DataWork 挂载到 `1490473838.cn/datework/` 的完整包，包含修改后的主页生产副本，原主页目录只读 |
| `datework_source.zip` | 不含构建缓存、二进制和用户数据的完整源码包 |

每个文件旁均生成同名 `.sha256` 文件。压缩包内部另有逐文件 SHA-256 清单。
所有最终文件统一位于 `dist/platform-release/`，不会与历史构建产物混放。

## 一键生成

先完成 Windows NSIS 中文安装包构建，然后在仓库根目录执行：

```powershell
python scripts/package_platform_releases.py
```

如 Windows 安装包不在默认发布目录，可明确指定：

```powershell
python scripts/package_platform_releases.py `
  --windows-setup "完整路径\DataWork_0.4.9_x64-setup.exe"
```

只生成 macOS、Linux 和源码包：

```powershell
python scripts/package_platform_releases.py --skip-windows
```

## Windows

Windows 文件是 NSIS Setup 安装程序，不是程序本体改名。安装向导使用简体中文，
允许用户选择安装位置，采用当前用户安装模式，启动窗口默认最大化。

当前安装包没有商业代码签名，Windows 可能显示未知发布者提示。发布页应同时提供
SHA-256，方便用户核对下载文件。

## macOS

macOS 暂不生成 DMG。命令包包含中文安装、启动命令和运行源码，需要用户预先安装
Python 3.11 或更高版本。由于没有 Developer ID，首次运行可能需要在 Finder 中
按住 Control 点击命令文件并选择“打开”。

## Linux 服务器

服务器部署支持最多 3 个单进程匿名会话，并可启用所有者工作区密码认证。服务器包
默认只监听 `127.0.0.1`；通过域名部署时必须使用 HTTPS，Supervisor 保持 1 个进程。
包内只有应用源码、静态资源、`requirements.txt`、`bt_start.py` 和中文部署说明，
不包含 Docker、systemd、自动安装脚本，也不会修改服务器配置。宝塔面板推荐将文件
解压到 `/www/wwwroot/datework`，创建项目独立 Python 3.11/3.12 虚拟环境，并使用
Supervisor 守护 `bt_start.py`。

个人使用优先采用 SSH 隧道：

```bash
ssh -L 8765:127.0.0.1:8765 用户名@服务器地址
```

需要通过域名访问时，应在宝塔站点中把请求反向代理到
`http://127.0.0.1:8765`，同时配置 Nginx Basic Auth、HTTPS 和防火墙；仅配置
反向代理不足以保护当前应用。详细操作已写入包内 `宝塔面板部署说明.txt`。

服务器数据默认保存在包内 `data` 目录。升级前应停止服务并完整备份该目录。

## 源码包

源码包排除 `.git`、虚拟环境、依赖目录、缓存、日志、`dist`、Rust `target`、
平台 sidecar、用户数据和密钥。包内 `SOURCE_MANIFEST_SHA256.txt` 记录逐文件校验值。

## 个人主页子项目部署包

`datework_homepage_subproject_deploy.zip` 通过独立命令生成：

```powershell
python scripts/package_homepage_subproject.py --homepage-root "E:\studywork\Web"
```

打包器只读复制个人主页生产文件，并在包内副本的 `index.html` 增加 DataWork 卡片、
在 `sw.js` 放行 `/datework/`；不会写入或清理 `E:\studywork\Web`。包内同时提供只含
这两个文件的增量覆盖目录、排除数据库/日志/密钥的主页完整副本、DataWork 服务文件、
宝塔 Nginx 配置、中文部署和回滚说明。DataWork 前端资源、API 与下载链接都从应用
入口解析，能够在根路径和 `/datework/` 下运行。

---

## 原文档：RELEASE_CHECKLIST.md

# DataWork 发布检查清单

适用于 0.4.9 及后续版本。所有勾选项都应由日志、测试报告、哈希或人工复核记录支持。

## A. 版本与源码

- [ ] `VERSION`、Python、前端、桌面、Tauri、Cargo 版本一致；
- [ ] `CHANGELOG.md`、用户手册、统计方法手册和发布审查已更新；
- [ ] 源码包不含密钥、用户数据、虚拟环境、缓存、`node_modules`、本机构建目录；
- [ ] 生成并复核 `SOURCE_MANIFEST_SHA256.txt`；
- [ ] `python scripts/check_release_readiness.py` 通过。

## B. 计算核心

- [ ] `python scripts/run_golden_validation.py` 全部通过，数据 SHA-256 与 manifest 一致；
- [ ] t/非参数/ANOVA/MANOVA/回归/重复测量/混合模型专项测试通过；
- [ ] 关键统计量至少与一个独立实现或解析结果交叉验证；
- [ ] 零方差、零标准误、常数列、极小样本、缺失、空单元、秩亏等边界数据有明确结果或预检阻断；
- [ ] 多重校正的假设族定义与报告标签一致；
- [ ] 事后检验与 CLD 使用同一显著性矩阵；不完整比较不生成完整 CLD；
- [ ] 随机种子、软件版本和模型公式进入可复现元数据。

## C. 参数与数据一致性

- [ ] 方法注册表与执行器一一对应；
- [ ] 所有界面高级参数完成非默认值真实执行；
- [ ] 即时分析、项目工作区、API 和报告使用同一 `AnalysisPlan`；
- [ ] 旧项目字段迁移有测试；
- [ ] 因素阶数、组合确认、跨任务校正、联合因变量和 EMM 参数贯通；
- [ ] 变量/参数/文件改变后旧结果失效。

## D. 用户交互

- [ ] 数据读取、预检、分析、AI、项目和报告均有等待状态与重复点击保护；
- [ ] 预检错误可定位到变量、参数或设计问题；
- [ ] 超额因素组合必须显式确认并显示 `C(n,k)` 任务数；
- [ ] 简洁模式每个方法只显示少量常用参数，专业模式仍能访问全部参数；
- [ ] 常用参数和选项显示推荐理由、适用场景和风险；
- [ ] 多选事后检验显示方法区别、默认值和风险；
- [ ] 网络/API 错误后可重试且不丢失当前选择；
- [ ] 浏览器自动化覆盖核心工作流；
- [ ] 工作流进度、推荐选择恢复、结果失效原因、组合任务清单和 Esc 关闭通过验证；
- [ ] AI 悬浮窗四边/四角缩放、拖动、停靠、最小化和越界约束通过真实浏览器验证；
- [ ] 界面版本号来自健康接口，不存在硬编码旧版本。

## E. 报告

- [ ] 网页、Markdown、Excel、canonical JSON 的核心数值一致；
- [ ] p 值同时标明原始/校正值和校正方法；
- [ ] CLD 标明对应的具体事后方法；
- [ ] MANOVA 区分多元总体检验、单变量跟进和事后比较；
- [ ] MixedLM 的 Wald χ²不标成经典 F；
- [ ] 报告包含警告、样本量、缺失处理、公式和软件版本。

## F. Python 包与 sidecar

- [ ] Wheel 在独立目标目录可导入并找到静态资源和模板；
- [ ] PyInstaller sidecar 在目标系统启动；
- [ ] `/api/health`、`/api/capabilities`、上传分析和报告下载冒烟测试通过；
- [ ] sidecar 文件名与 Tauri target triple 契约一致；
- [ ] 生成并复核 SHA-256。

## G. 原生安装包

- [ ] Windows 中文 NSIS Setup 来自 Windows 原生构建，不使用伪交叉编译；
- [ ] macOS 中文命令包包含安装、启动和安全提示；
- [ ] Linux 纯文件服务器包包含 `requirements.txt`、`bt_start.py` 和宝塔中文部署说明，默认只监听 `127.0.0.1`；
- [ ] 个人主页子项目包只接管 `/datework/`，包含修改后的主页副本、认证、缓存隔离和回滚说明，且原主页源目录哈希不变；
- [ ] `datework_window_setup.exe`、`datework_macos_command.zip`、`datework_linux_server.zip` 和 `datework_source.zip` 已分别生成；
- [ ] 安装、首次启动、升级、卸载和用户数据保留行为通过；
- [ ] 文件选择器、中文路径、长路径和无网络启动通过；
- [ ] 正式签名/公证完成；
- [ ] 安装包及依赖完成安全扫描；
- [ ] 每个平台至少完成一组真实统计分析并与源码运行结果比对。

## H. 发布

- [ ] 发布说明列出新增、修复、兼容性和已知边界；
- [ ] 源码、安装包、审查报告和哈希文件名称一致；
- [ ] 下载后重新计算哈希并验证 ZIP/安装包完整性；
- [ ] 明确支持的平台、架构、最低系统版本和未验证范围；
- [ ] 保留可回滚的上一稳定版本。

---

## 原文档：RELEASE_MANIFEST.md

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
