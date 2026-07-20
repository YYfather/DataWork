# 项目工作区

## 存储位置

默认目录：

- Windows：`%LOCALAPPDATA%\DataWork`
- macOS：`~/Library/Application Support/DataWork`
- Linux：`${XDG_DATA_HOME:-~/.local/share}/datawork`

可通过环境变量或启动参数覆盖：

```bash
DATAWORK_HOME=/path/to/workspace datawork-web
# 或
datawork-web --workspace /path/to/workspace
```

把工作区放在移动硬盘或同步目录即可形成便携模式，但同一 SQLite 文件不应被多台机器同时写入。团队服务器应使用单一服务进程组访问共享工作区，而不是让客户端直接打开数据库文件。

## 内容

```text
workspace/
├── workspace.sqlite3
├── files/<project-id>/datasets/<dataset-id>.<ext>
├── reports/<run-id>/...
└── cache/
```

数据库保存：

- 项目；
- 数据集元数据、数据画像、源文件和清洗后 SHA-256；
- 清洗审计日志；
- 分析计划 JSON、哈希、修订号和复制来源；
- 每次运行的状态、结果、错误和 provenance；
- 报告 ZIP 的路径、大小和 SHA-256。

## 一致性保护

- 上传文件先写入临时文件，再原子替换到目标路径；
- 每次分析前重新计算源文件 SHA-256；
- 不匹配时立即停止，不复用旧元数据；
- 报告下载前再次验证 ZIP 哈希；
- 数据库操作使用事务和外键。

## API 流程

```text
POST /api/projects
POST /api/projects/{project_id}/datasets
POST /api/projects/{project_id}/plans
POST /api/plans/{plan_id}/runs
POST /api/runs/{run_id}/reports
GET  /api/reports/{report_id}/download
```

完整接口可在运行后访问 `/docs` 查看。
