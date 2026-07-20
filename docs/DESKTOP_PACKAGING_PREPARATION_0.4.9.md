# DataWork 0.4.9 独立程序准备记录

准备日期：2026-07-19

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

## 当前产物

| 产物 | SHA-256 |
|---|---|
| `dist/datawork-sidecar.exe` | `43df28ea75787fb3e4e44792befe9f60abca3ee27e674b61cde1c7a8f264da32` |
| `dist/release/DataWork-v0.4.9-Windows-x64-portable.zip` | `808f457910ad122aba95bebcbf915e1ad75841d347b0b73742cbcb2ddb810c9c` |
| `dist/wheelhouse/datawork-0.4.9-py3-none-any.whl` | `043fe19e0094c9114b35951c16affc6205676b3ca63f73ef4f3bac4700bc544b` |

便携 ZIP 内的 `DataWork.exe` 与 sidecar 二进制完全一致，包内 `SHA256SUMS.txt` 已复核。

## 原生安装包阻塞

`npx tauri info` 已确认 WebView2 和 Tauri CLI 可用，但当前 Windows 环境缺少：

1. Rustup、Rustc 和 Cargo；
2. Visual Studio 2022 Build Tools 的 MSVC C++ 工具集；
3. 与 MSVC 配套的 Windows SDK。

因此当前可交付的是通过冒烟的 Windows x64 便携版，不把尚未编译的 Tauri 外壳表述为 MSI/NSIS 安装包。安装上述工具链后执行：

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
