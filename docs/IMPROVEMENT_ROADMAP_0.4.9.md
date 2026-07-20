# DataWork 0.4.9 改进路线图

> 状态：计划文档
>
> 适用版本：`0.4.9`
>
> 更新时间：2026-07-20
>
> 本文只定义改进目标、优先级、实施顺序和验收标准，不直接修改产品行为。实施前应再次以当前源码和测试结果校准本文。

## 1. 背景与目标

DataWork 当前是一个以 Python 统计引擎为核心、由 FastAPI 提供 Web API、Vue 3 提供前端、Tauri 提供桌面壳的分层单体应用。核心数据流已经形成：

```text
数据文件
  → DatasetService
  → AnalysisPlan
  → 预检与校验
  → executor / engine
  → StatisticalResult
  → report bundle
  → SQLite + 文件系统
```

当前改进重点不是立即扩展统计方法，而是降低已有系统的维护成本，提高核心行为的可验证性，并增强版本升级和发布的可靠性。

### 总体目标

1. 让核心统计行为有稳定、快速、可定位的测试保护。
2. 让应用层依赖稳定的抽象，而不是直接绑定 SQLite、具体 AI provider 等基础设施细节。
3. 明确 Streamlit 遗留 UI 的生命周期，避免长期维护两套前端。
4. 建立可信的文档、数据库迁移和发布验证流程。
5. 保持当前单机/本地部署场景的简单性，避免无明确需求的过度架构化。

## 2. 当前问题清单

| 编号 | 问题 | 影响 | 优先级 |
|---|---|---|---|
| P1 | 核心模块和应用服务的单元测试边界不完整 | 修改 `method_registry`、校验、服务编排时风险较高 | 高 |
| P2 | `WorkspaceRepository` 直接绑定 `sqlite3` | 持久化实现难以替换，应用层测试不够隔离 | 高 |
| P3 | 应用和设计模块直接依赖具体 AI provider | provider 替换、mock 和故障测试需要修改多个模块 | 中高 |
| P4 | `datawork/ui.py` 仍保留 Streamlit legacy UI | 形成 Vue 与 Streamlit 双 UI 维护成本 | 中高 |
| P5 | 文档存在版本滞后、重复和历史计划未归档 | 新开发者难以判断哪份文档有效 | 中 |
| P6 | SQLite schema 版本为 1，迁移策略不明确 | 工作区升级可能出现兼容性风险 | 高 |
| P7 | `frontend/` 与 `datawork/web/static/` 并存 | 可能出现源码与实际服务资源不同步 | 中高 |
| P8 | 局域网监听和远程 AI 配置的安全边界需要强化 | 可能意外暴露服务或数据 | 高 |
| P9 | 旧参数 `factor_model_order` 的迁移逻辑仍在主流程中 | 增加分支复杂度，阻碍后续模型演进 | 中 |
| P10 | 源码目录混有缓存、构建和测试产物 | 发布、审查和问题定位容易误判 | 中 |

## 3. 范围与非目标

### 本计划包含

- 测试基线和核心回归保护
- repository 与 AI provider 的最小抽象
- Streamlit legacy UI 的处置
- 文档分类和版本治理
- SQLite schema migration 机制
- 前端静态资源同步检查
- Web 暴露面和远程 AI 的安全检查
- 旧迁移逻辑的清理
- 发布前和多平台验证流程

### 本计划暂不包含

- 将当前应用拆分为微服务
- 引入 Celery、Redis 或其他任务队列
- 将 `scipy`/`statsmodels` 统计后端抽象成可替换的 R 或 PyTorch 后端
- 将全部方法元数据迁移到 YAML/JSON
- 大规模重写统计算法
- 与当前问题无关的 UI 重设计

这些事项只有在部署规模、性能或产品需求发生变化时再单独立项。

## 4. 设计原则

1. **先建立行为基线，再重构边界**：先用测试固定当前正确行为，避免抽象改造改变统计结果。
2. **最小抽象**：只抽象已有替换需求或测试隔离确实需要的边界，不为假设的未来需求增加接口。
3. **兼容优先**：已有工作区、分析计划和报告格式必须有明确的兼容策略。
4. **核心路径不依赖网络**：AI 失败、未配置或不可用时，统计分析流程仍可运行。
5. **发布产物可验证**：源码、构建静态资源、sidecar 和安装包必须有可重复的检查步骤。
6. **每阶段可独立回滚**：每个阶段都应保持项目可运行，并有独立的验收命令。

## 5. 分阶段实施计划

## 阶段 0：建立基线

### 目标

在任何结构性修改前，确认当前源码、测试、构建和发布产物的真实状态。

### 任务

- 确认唯一活跃源码目录为 `DataWork-v0.4.9-Full-Source/`。
- 清点 `datawork/`、`frontend/`、`desktop/`、`tests/`、`scripts/` 和 `docs/` 的职责。
- 统一测试数量、黄金数据集断言数量和发布审查口径。
- 记录当前后端测试、前端构建和发布检查的基线结果。
- 将缓存、测试临时目录、构建产物与发布源码区分开。
- 建立技术债清单，记录责任范围、优先级、预计收益和完成标准。

### 验收标准

- 能从一份文档中找到推荐安装、运行、测试和发布命令。
- 测试和审查报告使用同一套统计口径。
- 任何构建产物都能追溯到对应源码和构建命令。

## 阶段 1：质量与安全底座

### 目标

先保护最重要的行为，再进行依赖边界重构。

### 任务

#### 1.1 补充核心单元测试

优先为以下模块建立测试：

- `datawork/core/method_registry.py`
- `datawork/core/validation.py`
- `datawork/core/errors.py`
- `datawork/core/plan.py`
- `datawork/application/analysis_service.py`
- `datawork/application/dataset_service.py`
- `datawork/application/preflight_service.py`
- `datawork/application/report_service.py`
- `datawork/infrastructure/workspace_repository.py`
- `datawork/ai/settings.py`
- `datawork/ai/provider.py`

测试重点不是追求行覆盖率，而是保护：

- 方法注册与 executor 注册的一致性
- 非法参数和变量角色的错误代码
- 数据指纹和清洗结果
- 预检失败时不执行统计计算
- 批量分析的成功、失败和部分失败行为
- workspace 保存、读取、事务回滚和重复运行
- AI 不可用时的降级行为

#### 1.2 固化黄金回归测试

- 保留现有 golden datasets 作为结果级回归测试。
- 为关键统计方法补充边界数据：缺失值、单组、空数据、常数列、极小样本和非法变量类型。
- 区分“数值精确匹配”和“允许浮点误差匹配”。
- 对报告内容只断言稳定字段，不绑定无意义的格式细节。

#### 1.3 安全基线

- 明确默认只监听 `127.0.0.1`。
- 使用 `--host 0.0.0.0` 时给出显式警告和安全说明。
- 为远程 AI 增加配置校验、超时、错误降级和敏感信息日志脱敏。
- 检查上传文件大小、路径、扩展名和报告下载路径，防止路径穿越。
- 在文档中明确：局域网部署不等于有身份认证。

### 验收标准

```powershell
pytest -q
python scripts/check_release_readiness.py
cd frontend; npm run build
```

上述命令应有明确、可记录的通过结果；新增测试必须覆盖关键失败路径，而不仅是成功路径。

## 阶段 2：架构边界治理

### 目标

以最小改动隔离应用层与可替换基础设施，同时保持统计结果和外部 API 兼容。

### 2.1 workspace repository 抽象

建议引入最小的 repository 协议或抽象接口，接口应描述应用层实际需要的操作，而不是复制整个 SQLite 类。

```text
application service
      ↓
WorkspaceRepositoryProtocol
      ↓
SqliteWorkspaceRepository
```

实施要点：

- 先从 `WorkspaceService` 实际调用点提取接口。
- 具体 SQLite schema 和 SQL 继续留在 infrastructure 中。
- 通过构造函数注入 repository，生产环境使用 SQLite 实现，测试使用内存或 fake 实现。
- 不在本阶段引入 PostgreSQL；只有接口和替换点，不增加无需求的后端。
- 保证已有 workspace 文件格式和 API 响应不变。

### 2.2 AI provider 抽象

- 在稳定位置定义最小 `LLMProvider` 接口及响应模型。
- `application/ai_assistant_service.py` 和 `design/infer.py` 依赖接口，而不是直接依赖 provider 创建函数。
- 将 provider 选择、配置读取和具体 OpenAI/Ollama 实现留在组合根或 infrastructure 适配位置。
- 增加 fake provider，用于测试成功、超时、网络错误、空响应和安全过滤。
- 保持 AI 为可选能力，不允许 AI provider 进入统计执行的必经路径。

### 2.3 暂不抽象统计库

`engine/` 直接使用 `numpy`、`scipy` 和 `statsmodels` 在当前场景是合理的。此阶段不做“统计后端接口”，以免产生一个无法表达真实统计语义的空泛抽象。只有出现第二种实际计算后端或独立进程执行需求时再评估。

### 验收标准

- 应用层测试不需要启动真实 SQLite 文件或真实 AI 网络请求。
- 替换 SQLite/AI 实现只需修改组合配置，不需修改业务流程。
- 全量测试、黄金数据集和报告回归结果不变。
- 依赖方向文档与实际 import 关系一致。

## 阶段 3：遗留内容与文档治理

### 目标

减少重复入口和过时信息，建立文档的“当前有效”规则。

### 3.1 Streamlit legacy UI

先做使用情况确认，再选择以下策略：

1. 若没有实际用户：在一个版本周期内移除 `ui.py`、legacy 依赖和 CLI 命令。
2. 若仍有用户：冻结功能，只修复阻断性问题，并在 CLI 输出迁移提示。
3. 若必须长期保留：明确它是兼容入口，不再同步新增 Vue 功能。

推荐策略是**冻结后移除**，但必须先确认使用者和发布包兼容要求。

### 3.2 文档分类

将文档分为：

- `current/`：当前架构、运行、开发和发布规范
- `audits/`：历史审计报告，保留版本号
- `archive/`：已废弃或仅供历史参考的计划

重点处理：

- 更新 `docs/ARCHITECTURE.md`，准确描述 0.4.9。
- 标记 `PHASE3.md`、`MIGRATION_ROADMAP.md` 等已完成或过期内容。
- 合并或标记重复的 `INTERACTION_AUDIT.md` 与 `INTERACTION_AUDIT_RELEASE.md`。
- 在 `docs/README.md` 或索引中声明每类文档的权威性。
- 发布文档中只保留当前版本必须执行的检查。

### 3.3 旧迁移逻辑

针对 `factor_model_order`：

- 先统计真实旧工作区和旧计划的使用情况。
- 增加迁移测试，覆盖旧输入到新模型的转换。
- 将迁移代码集中到独立兼容模块。
- 在确认不再需要旧格式后，再从 `preflight_service.py`、`core/plan.py`、`application/executors.py` 和 `method_registry.py` 清理。

### 验收标准

- 新开发者能在 5 分钟内找到当前架构和开发入口。
- 所有历史文档有明确的版本和状态标记。
- 移除或冻结 legacy UI 后，不影响默认 Web、CLI 和桌面流程。
- 旧计划兼容策略有测试和发布日期说明。

## 阶段 4：发布与演进能力

### 目标

让数据库升级、前端构建、桌面打包和多平台验证具备稳定流程。

### 4.1 SQLite schema migration

- 定义 schema 版本表或等效版本记录。
- 为每次结构变化提供单向、可重复执行的 migration。
- 启动时拒绝不支持的未来版本，并给出可理解的错误。
- 升级前创建备份，失败时保持原数据库可恢复。
- 对旧版本 workspace 建立迁移测试。
- 在发布清单中加入 schema 迁移和回滚验证。

### 4.2 前端静态资源同步

- 明确 `frontend/` 是源码，`datawork/web/static/` 是构建输出。
- 提供单一构建命令生成静态资源。
- 在 CI 或发布脚本中检查静态资源是否由当前前端源码生成。
- 不把过期静态资源误认为最新功能。

### 4.3 Tauri 与 sidecar

- 在目标平台验证 Python sidecar 启动、端口分配、退出和异常重启。
- 验证安装、升级、卸载、权限、路径和报告目录。
- 明确代码签名和发布包生成要求。
- 将“源码测试通过”和“原生安装包验证通过”分成两个发布门槛。

### 4.4 发布检查

统一发布前至少检查：

- 后端测试
- golden datasets
- 前端生产构建
- 静态资源同步
- schema migration
- workspace 备份与恢复
- 本机默认访问
- 显式局域网访问警告
- AI 未配置时的核心流程
- Tauri/sidecar 目标平台验证

## 6. 推荐实施顺序

```text
阶段 0 基线
   ↓
阶段 1 测试与安全底座
   ↓
阶段 2 repository / AI 抽象
   ↓
阶段 3 文档、legacy UI、旧迁移逻辑
   ↓
阶段 4 schema migration 与发布流程
```

依赖关系说明：

- 没有测试基线，不开始大规模抽象重构。
- 没有旧 workspace 兼容测试，不删除迁移逻辑。
- 没有确认 Streamlit 使用情况，不直接删除 `ui.py`。
- 没有明确构建来源，不直接删除 `datawork/web/static/`。
- 没有实际替换需求，不抽象统计计算后端。

## 7. 风险与控制措施

| 风险 | 可能后果 | 控制措施 |
|---|---|---|
| 抽象重构改变调用行为 | 统计结果或 API 变化 | 先补回归测试，保持接口适配层 |
| 删除 legacy UI 影响旧用户 | 用户无法启动旧入口 | 先统计使用情况，冻结一个版本并提供迁移说明 |
| schema migration 失败 | workspace 数据不可用 | 升级前备份、事务执行、失败可恢复 |
| 静态资源不同步 | 用户看到旧前端 | 发布脚本强制重新构建并检查产物 |
| 开放 `0.0.0.0` 暴露服务 | 未授权访问 | 默认 localhost、显式警告、文档说明认证边界 |
| 文档继续膨胀 | 新旧规则冲突 | 建立当前文档索引和历史归档规则 |
| 过早引入复杂基础设施 | 开发和部署成本上升 | 不引入没有当前需求支撑的服务和抽象 |

## 8. 完成定义

本路线图完成不代表所有潜在技术债都已消除，而是达到以下状态：

- 核心统计和应用服务具备稳定的单元及回归测试。
- 应用层不直接绑定具体 workspace 存储和 AI provider 实现。
- Streamlit legacy UI 有明确的冻结、迁移或移除结论。
- 当前架构文档、运行文档和发布文档与 `0.4.9` 实际代码一致。
- SQLite workspace 有可测试的 schema migration 和备份恢复流程。
- 前端源码、静态资源、桌面 sidecar 和发布包之间的关系清晰可验证。
- 网络暴露、远程 AI 和敏感数据处理有明确的安全边界。
- 每个阶段都有独立的测试结果、变更记录和回滚方式。

## 9. 首批执行建议

建议第一轮只做以下五项，避免一次性扩大范围：

1. 记录 `pytest -q`、`npm run build` 和发布检查的基线结果。
2. 为 `method_registry`、`validation`、`AnalysisService` 和 `WorkspaceRepository` 增加最小关键行为测试。
3. 盘点 `factor_model_order` 旧格式的实际兼容需求。
4. 确认 Streamlit UI 是否仍被用户使用。
5. 更新当前架构文档，并建立文档索引和状态标记。

完成这五项后，再开始 repository 和 AI provider 的抽象重构，风险最低、收益最明确。
