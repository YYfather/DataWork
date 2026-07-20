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
