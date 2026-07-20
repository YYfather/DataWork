# 迁移路线

## 已完成：0.2 可信执行基础

- 安全和统计可信度修复；
- AnalysisPlan 与方法注册表；
- FastAPI + Vue 即时分析；
- 本地浏览器模式和跨平台启动；
- PyInstaller 构建基础。

## 已完成：0.3 核心重构与工作区

- Dataset/Design/Analysis/Report/Workspace 应用服务；
- 执行器注册，移除 AnalysisService 方法分支链；
- 统一变量角色、校验问题和错误代码；
- 源数据、清洗数据、计划和环境 provenance；
- SQLite 项目、数据集、计划修订、运行历史、结果对比和报告；
- 跨平台应用数据目录、原子文件写入和数据库 Schema 版本；
- 三系统 CI 测试矩阵。

## 下一阶段：0.4 统计方法

- ANCOVA 与回归斜率同质性检验；
- 重复测量 ANOVA 和球形性校正；
- 线性混合效应模型；
- 真正的模型边际均值与对比；
- 非参数和稳健方法；
- 与 R 参考结果持续对照。

## 后续：0.5 桌面发布

- Tauri 2 外壳与 Python sidecar；
- Windows、macOS、Linux 安装包；
- 自动更新、代码签名和应用生命周期；
- 完全离线模式与本地 Ollama。
