# DataWork 0.3 架构

## 目标

1. 统计方法与任何界面彻底解耦。
2. 同一分析计划在即时网页、项目工作区、CLI 和桌面外壳中产生相同结果。
3. 所有错误具有稳定代码，未实现方法不能静默降级。
4. 统计运行可以追溯到源文件、清洗步骤、参数和运行环境。
5. Windows、Linux、macOS 使用同一源码和同一工作区格式。

## 分层

```text
Vue / CLI / Streamlit / Future Tauri
                 │
                 ▼
         application services
  DatasetService / DesignService / AnalysisService
            ReportService / WorkspaceService
                 │
      ┌──────────┼──────────┐
      ▼          ▼          ▼
 core domain   engines   infrastructure
 plan/roles    scipy      SQLite / paths
 validation    statsmodels file repository
 errors        result     atomic storage
 provenance
```

### Core

- `AnalysisPlan`：唯一分析意图模型。
- `method_registry`：方法状态、输入约束和执行器标识的唯一来源。
- `validation`：在执行前生成结构化问题列表。
- `errors`：稳定错误代码和 HTTP/CLI 可复用错误负载。
- `provenance`：计划、数据和运行环境指纹。
- `roles`：统一变量角色枚举。

### Application

- `DatasetService`：文件读取、保守清洗、画像、清洗日志和哈希。
- `DesignService`：把规则推断转换为统一角色模型，并执行计划预检。
- `AnalysisService`：通过执行器注册表执行计划，返回结果和可复现信封。
- `ReportService`：生成报告文件并计算每个产物的哈希。
- `WorkspaceService`：协调项目、数据集、计划、运行和报告。

### Infrastructure

SQLite 工作区只保存元数据和 JSON；原始上传文件及报告按相对路径存放在工作区内。数据库使用外键、事务和 WAL。Schema 版本记录在 `workspace_meta`，为后续迁移预留入口。

## 执行链

```text
source bytes
  → DatasetService
  → cleaned DataFrame + profile + cleaning log + fingerprint
  → AnalysisPlan
  → ValidationReport
  → MethodSpec.executor
  → StatisticalResult
  → ReproducibilityMetadata
  → workspace run / report bundle
```

## 扩展统计方法的硬性要求

1. 在方法注册表登记状态和执行器标识；
2. 在 `application/executors.py` 注册执行器；
3. 增加与权威实现对照的统计测试；
4. 明确更新输入角色和限制；
5. 更新 API/界面；
6. 禁止使用其他方法作为回退。

## AI 辅助边界（0.3.1）

`AISettingsService` 负责非敏感配置和密钥存储，`AIAssistantService` 负责操作解释、上下文隐私过滤和结果 Guard。统计执行器不依赖 AI，因此关闭 AI、网络失败或密钥缺失都不会影响统计分析。
