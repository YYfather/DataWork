# DataWork 1.5.0（V1.5）

DataWork 是面向实验数据的跨平台统计分析与可复现项目工作区。统计核心使用 Python、SciPy 和 statsmodels，应用层使用 FastAPI，网页界面使用 Vue 3 + TypeScript。

> 当前可运行版本为 `1.5.0`。V1.5 已在专业模式实现处理—对照配对映射、配对计算列、联合因变量分组、完整交互分支比较和分层执行审核；旧 v1.0 计划继续按原语义读取。

## V1.5 正式版

- 每个计划允许一个配对方案：处理水平与对照水平一一映射，可按最多 10 个标签及显式样本 ID 或不可变原始行序配对；任何已映射组样本不一致都会在执行前停止整次分析。
- 最多建立 10 个配对计算列，每列只使用同一指标的处理值、对照值、常量、括号及 `+ - * /`，结果最多保留 8 位小数；配对列只能作为因变量。
- 普通自定义列可在配对后引用处理侧原始数值列或配对列，但仍禁止自定义列互相引用；依赖顺序固定为“原始列 → 配对列 → 普通自定义列 → 因变量”。
- 联合方法支持给因变量建立互斥命名组，并与因素组合、拆分维度组成任务树；执行审核明确展示原始行、有效配对、排除项、计算列和最终任务数。
- MANOVA 新增显式 `branch_all` 跟进策略，可复现参考 R 脚本的交互分支比较，同时保留旧计划的保守默认策略。
- R 4.6.1 与 Python 核心的开发期双验证已覆盖全部 47 种方法（133 个比较字段）以及农业数据 108 对、36 个 Type III ANOVA 效应和 18 个 Wilks MANOVA 效应；R 不进入正式依赖。
- 完整设计、兼容边界和验收证据见 [`DataWork V1.5 更新计划与实施记录`](docs/V1.5_UPDATE_PLAN.md)及[`可复现性记录`](docs/REPRODUCIBILITY.md)。

## v1.0 基线能力

- v1.0 首次统一 Python、前端、桌面外壳、服务器健康接口和发布清单版本来源。
- 专业模式支持最多 10 个自定义计算列，每列最多引用 10 个原始数值列；允许基础算术和括号，统一保留最多 8 位小数，禁止自定义列互相引用。
- 自定义列只能作为因变量，并继承来源原始列及全局拆分的排列组合；不作为分类因素、协变量或自定义拆分列。
- 服务器部署版与通用源码分支继续隔离；从 0.4.9 升级时保留经哈希验证、可自动备份和回滚的服务器热补丁。
- 项目组统计方法手册新增全部 47 种方法与 SciPy、statsmodels、Patsy 等计算依赖的逐项映射及升级复核规则。

## 0.4.9 黄金数据集、计算核心复核与普通用户参数优化

- `golden_datasets/` 现含 29 个冻结 CSV、52 个黄金案例和 425 个独立参考断言，覆盖全部 47 个当前可执行统计方法，并保留旧析因计划迁移案例。
- 参考结果来自 SciPy、statsmodels 或明确公式；数据文件使用 SHA-256 锁定，禁止直接用当前程序输出覆盖期望值。
- 修复 t 检验被包装成无方向 F 结果、Fleiss κ 使用 `p=1` 占位、推断结果提前舍入、经典混合 ANOVA 成对比较使用占位区间等计算与结果语义问题。
- 默认参数进一步收敛：普通模式每个方法最多显示 1–2 个常用设置，并提供推荐理由和选项级一句话解释；全部高级参数继续保留但默认隐藏。
- 单因素 ANOVA 默认“自动”选择 Tukey/Games–Howell；析因 ANOVA 与 MANOVA 默认 Tukey；MANOVA 默认只显示较稳健的 Pillai。
- 修复 AI 悬浮窗八方向缩放命中区域被后置 CSS 覆盖的问题，并通过真实 Chromium 拖动与缩放验证。
- 移除与单因素、双因素、三因素 ANOVA 重复的统一阶数控制入口；旧 `factorial_anova` 计划会自动迁移到对应固定方法。
- 批次结果改为“结果总览 / 逐批查看”双页面；参数后移，下载的 Excel 按总览、各批次、失败与警告、分析设置拆分为多个子表。
- 260 项自动化测试、344 组高级参数、387 组数据结构变体（190 个合法配置）和浏览器全流程审查通过。

详细记录见 [`docs/QUALITY_AUDIT_RECORDS.md`](docs/QUALITY_AUDIT_RECORDS.md)、[`docs/DEVELOPMENT_RECORDS.md`](docs/DEVELOPMENT_RECORDS.md) 和 [`docs/QUALITY_AUDIT_RECORDS.md`](docs/QUALITY_AUDIT_RECORDS.md)。

## 0.4.8 简洁工作流、统一下载与 AI 窗口修复

- 所有即时单次分析均可生成结果 Excel 和完整报告 ZIP，简单检验不再缺少下载入口。
- 默认使用简洁模式，仅显示方法、变量角色和推荐设置摘要；专业参数按需展开。
- 结果页默认展示核心结论，详细数值和扩展表格可切换查看或从报告中下载。
- AI 操作助手支持八方向调整大小、稳定拖动、左右停靠、最大化/还原和越界自动修正。

详细记录见 [`docs/QUALITY_AUDIT_RECORDS.md`](docs/QUALITY_AUDIT_RECORDS.md)。

## 0.4.7 固定 MANOVA 方法与必要设置修复

- 将原统一的“单/双/三因素 MANOVA + 阶数参数”拆分为三个清晰方法：单因素 MANOVA、双因素 MANOVA、三因素 MANOVA；方法本身固定需要 1、2、3 个分类因素。
- 修复已选因素后仍提示“缺少必要设置”的前端缺失项判断、预检初筛和计划规范化不一致。
- 超额因素不再改变模型阶数；只在用户确认后作为候选池，分别按 `C(n,1)`、`C(n,2)`、`C(n,3)` 执行同阶组合模型。
- 对固定因素数的方法隐藏“最小阶数/最大阶数”，界面仅显示“方法固定为 N 个因素/模型”。
- 旧版统一 `manova` 计划会根据保存的 `factor_model_order` 或原因素数量自动迁移，不破坏已有项目。
- 修复 MANOVA 交互效应名称还原中的列名边界问题，避免 `MF2` 等因素名被错误转换为 `MMF2` 并导致简单效应阶段失败。
- 205 项自动化测试全部通过，前端 TypeScript 与生产构建通过，全部 47 个可见统计方法均通过 HTTP 预检与执行矩阵。

专项记录见 [`docs/QUALITY_AUDIT_RECORDS.md`](docs/QUALITY_AUDIT_RECORDS.md)。

## 0.4.6 发布前全链路与计算核心审查

- 从数据导入、变量角色、因素阶数、组合确认、预检、执行、事后检验、CLD、AI 解释、项目保存恢复到报告导出完成端到端审查；
- 修正 t 检验 η²、配对 Hedges 校正自由度、零标准误比较、Mann–Whitney 秩二列方向、Kruskal–Wallis Dunn 跟进、Logistic McFadden R²、重复测量对比区间标签和跨任务 MANOVA 校正族等计算问题；
- Tukey–Kramer、双因素 Type III ANOVA、四种 MANOVA 统计量和 Logistic 拟合指标已与 SciPy/statsmodels 独立参考计算交叉验证；
- 新增发布就绪检查、独立程序构建脚本、打包说明和发布检查清单；PyInstaller sidecar 名称已与 Tauri `externalBin` 契约统一为 `datawork-sidecar`；
- 最终交互优化增加工作流进度、结果失效说明、缺失角色即时提示、推荐角色恢复、多选参数状态、组合任务明细预览和 Esc 关闭弹窗；
- 155 项自动化测试、236 组高级参数实际执行和 360 组数据结构变体完成验证；180 个合法数据配置全部成功执行，浏览器完整工作流与前端生产构建通过。

详细记录见 [`docs/QUALITY_AUDIT_RECORDS.md`](docs/QUALITY_AUDIT_RECORDS.md)，独立程序构建见 [`docs/RELEASE_DEPLOYMENT_GUIDE.md`](docs/RELEASE_DEPLOYMENT_GUIDE.md)。

## 0.4.5 阶数控制、事后检验多选与显著性字母分组

- 普通析因 ANOVA 与 MANOVA 均新增独立的 1/2/3 阶模型控制；候选因素超过阶数时，必须确认后才按 `C(n,k)` 展开组合实验。
- Tukey、Duncan、Games–Howell、Dunnett、Holm 等事后检验可单选或多选，每种方法独立输出成对比较。
- 新增紧凑显著性字母分组（CLD），网页、Markdown、Excel 和批量汇总均可显示 `a / ab / b`。
- Duncan 保留农业领域兼容性提示；Dunnett 因不覆盖全部组对，不补造完整字母分组。

完整验证见 [`docs/QUALITY_AUDIT_RECORDS.md`](docs/QUALITY_AUDIT_RECORDS.md)。

## 0.4.4 因素组合确认与 MANOVA 定义一致性修复

- MANOVA 明确以 **至少两个联合因变量** 建模，界面会自动补足候选因变量并显示联合选择要求；
- 单因素方法超额选择因素时，确认后执行所有单因素模型；双因素方法确认后执行全部二因素组合；三因素方法同理；
- 组合分析默认关闭，第一次超出方法因素上限时必须在弹窗中确认，弹窗会给出组合数、执行规则和 Holm 跨模型校正；
- MANOVA 的 EMM、对比校正和因素组合现已前后端贯通；
- 显著交互自动进入校正后的条件简单效应，不再把跨条件边际主效应比较作为主要后续分析；
- Bartlett 改为残差相关结构诊断，条件数基于标准化因变量，Box's M 使用独立严格阈值；
- Dunnett 支持按因素分别指定对照；报告同步输出简单效应原始与校正后 p 值。

完整验证见 [`docs/QUALITY_AUDIT_RECORDS.md`](docs/QUALITY_AUDIT_RECORDS.md)。

## 0.4.3 智能设计审查、扩展 MANOVA 与自适应混合模型

- 新增结构化“智能统计设计审查”：在执行前说明当前研究对象、预计分析引擎、完整单元数、最小重复数、平衡比、残差自由度、主要风险和建议动作；
- AI 助手同步解释当前数据和方法究竟研究什么，并读取设计审查结论，但仍不参与统计数值计算；
- MANOVA 扩展为 **1–3 个对象间分类因素**，使用完整析因模型检验主效应、两两交互和三因素交互；
- 新增 Box's M、Mardia 残差多元正态近似诊断、Bartlett 相关矩阵球形检验、因变量相关矩阵和条件数诊断；
- MANOVA 可按主要多元判据自动执行单变量 Type I/II/III 跟进，并对跨因变量/效应 p 值进行 Holm、Bonferroni、Šidák 或 FDR-BH 校正；
- 统一事后比较体系：Tukey–Kramer、Games–Howell、Holm、Bonferroni、Šidák、FDR-BH、Scheffé、Duncan、Fisher protected LSD 和 Dunnett；
- 双/三因素 ANOVA 与 MANOVA 的主效应比较改为模型估计边际均值；显著交互存在时会阻止或警示误导性的主效应自动解释；
- 混合设计升级为自适应分析：完整平衡的单对象间因素设计保留经典混合 ANOVA；不平衡、部分缺测或两个对象间因素时自动切换为受试者随机截距 MixedLM；
- MixedLM 明确报告 Wald χ²、随机效应方差、收敛状态、AIC/BIC、模型 EMM 和多重比较，不把 Wald χ²伪装为经典 F；
- 后端 125 项自动化测试、193 组高级参数变体和 350 组数据变体全部通过；前端 TypeScript、生产构建和浏览器交互审查通过。

完整验证见 [`docs/QUALITY_AUDIT_RECORDS.md`](docs/QUALITY_AUDIT_RECORDS.md)。

## 0.4.2 MANOVA 完善重点

- 明确支持单因素与双因素对象间 MANOVA；
- 双因素模型自动检验两个主效应及交互作用；
- 多元检验统计量可选：全部、Pillai、Wilks、Hotelling–Lawley、Roy；
- 结果表显示统计量值、近似 F、自由度和 p 值；
- 修复旧版 MANOVA 因字段名和统计量名称不匹配而无法输出完整结果的问题；
- 数值编码处理水平强制按分类因素建模；
- 明确区分对象间双因素 MANOVA 与重复测量混合 MANOVA。
- 本版本最终回归：121 项自动化测试、105 组高级参数变体和 350 组数据变体通过。

完整验证见 [`docs/QUALITY_AUDIT_RECORDS.md`](docs/QUALITY_AUDIT_RECORDS.md)。

## 0.4.1 全交互审查重点

- 43 种方法均通过应用服务和 HTTP 上传分析路径；
- 350 组缺失、极小样本、常数、文本误选、批量极小子集和角色冲突数据变体完成回归；
- 100 组非默认高级参数完成实际执行；
- 修复单列 CSV 读取、比例 z 单侧备择假设和有序回归扩展链接函数；
- 批量预检逐个验证真实子任务，分类水平、配对、分层、有序和退化数据错误在执行前拦截；
- 即时分析与工作区的读取、预检、执行、保存、运行和报告均增加等待动画、阶段说明和重复提交保护；
- 方法、变量、参数或文件改变后旧结果自动失效；
- 错误提示支持重试、关闭和返回定位，并保留当前选择；
- 新增三个可重复发布审查脚本。

完整记录见 [`docs/QUALITY_AUDIT_RECORDS.md`](docs/QUALITY_AUDIT_RECORDS.md)。

## 0.4.0 第三阶段重点

- 最终全面审查并修复注册、运行时验证、跨任务校正、REML 指标和跨平台字体问题；
- **43 种方法定义全部可执行**，方法注册表与执行器有自动一致性测试；
- 重复测量 ANOVA 新增 Mauchly 球形性检验、Greenhouse–Geisser/Huynh–Feldt 校正和重复水平对比；
- 混合设计 ANOVA 支持一个对象间因素 × 一个对象内因素的完整平衡设计；
- 线性混合模型支持随机截距和最多两个随机斜率，并记录随机方差/协方差、ICC 与收敛状态；
- ANOVA、ANCOVA、回归和混合模型支持估计边际均值（EMM）及 Holm/Bonferroni/FDR 对比校正；
- 网页和报告支持残差、Q–Q、尺度位置、影响点和交互作用诊断图；
- 分类因素组合、多个因变量和任意拆分列继续使用通用批处理，不依赖固定列名；
- 新增 `/api/capabilities` 和 `desktop/` Tauri 2 sidecar 外壳源码，为三系统原生安装包建立稳定接口；
- AI、分析前检查、项目工作区、报告和可复现元数据均已兼容第三阶段字段。

## 支持平台

同一套程序支持：

- Windows、Linux、macOS 本地浏览器运行；
- 服务器或受信任局域网部署；
- 即时上传分析；
- SQLite 项目工作区与分析历史；
- CLI 自动化；
- 可选 AI 操作和结果阅读助手。

Python 要求：**3.11 或更高**。普通用户运行已构建网页时不需要 Node.js。

## 快速安装

### 自动安装

- Windows：运行 `scripts/setup_datawork.bat` 或 `scripts/setup_datawork.ps1`
- Linux：运行 `./scripts/setup_datawork.sh`
- macOS：运行 `scripts/setup_datawork.command`

### 手动安装

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Linux / macOS：

```bash
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
```

## 启动

```bash
datawork-web
```

- 网页：`http://127.0.0.1:8765`
- API 文档：`http://127.0.0.1:8765/docs`

指定工作区：

```bash
datawork-web --workspace ./DataWorkWorkspace
```

## 分类因素组合实验

界面中选择多个分类因素后，可以启用“分类因素组合实验”：

```text
候选因素：A、B、C、D
组合阶数：2
方法：双因素 ANOVA

生成模型：A×B、A×C、A×D、B×C、B×D、C×D
```

最终结果合并到一个工作表，并保留：

- 任务编号；
- 因变量；
- 因素组合和组合阶数；
- 拆分水平；
- 方法与模型公式；
- 高级参数；
- 检验统计量、自由度、p 值和效应量；
- 跨任务校正 p 值；
- 警告或失败原因。

组合数安全上限为 1000。详见 [`docs/FACTOR_COMBINATIONS.md`](docs/FACTOR_COMBINATIONS.md)。

第三阶段能力详见 [`docs/DEVELOPMENT_RECORDS.md`](docs/DEVELOPMENT_RECORDS.md)，最终审查见 [`docs/QUALITY_AUDIT_RECORDS.md`](docs/QUALITY_AUDIT_RECORDS.md)。

## 高级参数

高级参数默认折叠。未展开或未修改时使用方法注册表中的默认值。修改后的参数会进入：

- 分析计划；
- 计划 SHA-256；
- 运行 provenance；
- AI 分析说明；
- 结果汇总表和报告。

## 当前方法类别

| 类别 | 代表方法 |
|---|---|
| 描述与数据概览 | 描述统计 |
| 均值比较（参数） | 单样本 t、Welch t、Student t、配对 t |
| 非参数比较 | Mann–Whitney U、Wilcoxon、Kruskal–Wallis、Friedman |
| 方差分析 | 单因素、Welch、双因素、三因素 ANOVA、ANCOVA |
| 相关分析 | Pearson、Spearman、Kendall |
| 回归分析 | 线性回归、二元 Logistic、线性混合模型 |
| 分类列联与比例 | 卡方/G²、Fisher、Barnard、Boschloo、二项与比例检验 |
| 配对与分层分类 | McNemar、Cochran Q、Bowker、Stuart–Maxwell、CMH、Breslow–Day |
| 分类一致性 | Cohen kappa、Fleiss/Randolph kappa |
| 分类趋势与回归 | Cochran–Armitage、多项 Logistic、有序 Logistic/Probit |
| 多变量分析 | 单/双因素 MANOVA（可选四种多元统计量） |

完整说明及每个参数的用途见 [`docs/STATISTICAL_METHODS.md`](docs/STATISTICAL_METHODS.md)。

## 分析前检查

点击执行后，程序先检查：

- 变量缺失、角色冲突和列是否存在；
- 数值、二元、名义或有序变量是否符合方法要求；
- 因素水平、完整案例和每个组合任务的样本结构；
- 重复测量与配对关系；
- 精确检验、渐近检验和重抽样参数是否兼容；
- 回归是否有预测变量、类别是否正确、模型是否可能分离；
- 因素组合数量和跨任务校正设置。

错误会阻止运行，警告需用户确认，不会静默切换方法。

## CLI 组合分析

```bash
datawork batch data.csv \
  --dependent yield \
  --factor variety --factor treatment --factor year --factor site \
  --method twoway_anova \
  --factor-combinations \
  --min-factor-order 2 \
  --max-factor-order 2 \
  --p-adjust holm \
  --output combined.xlsx
```

方法高级参数使用：

```bash
--parameter p_value_method=permutation \
--parameter n_resamples=9999 \
--parameter random_seed=2026
```

## AI 助手

AI 为可选辅助层：

- 内置规则始终可解释当前方法、因素组合和高级参数；
- AI 只在用户主动请求时优化说明或辅助阅读结果；
- 统计值由本地统计引擎计算；
- AI 输出经过结构化校验和数值 Guard；
- API 密钥仅保存在当前会话或操作系统密钥库；
- 默认不发送原始数据行；
- 连接测试后拉取 Model ID，并等待用户手动选择。
- 操作助手使用可拖动、可缩放的悬浮窗；支持最小化、恢复默认布局，并在本地保存位置与尺寸。

详见 [`docs/AI_ASSISTANT.md`](docs/AI_ASSISTANT.md)。

## 数据处理约定

- 空标题、`Unnamed`、全空列和空格列在画像前排除；
- 默认不使用低基数启发式填充缺失值；
- 百分号可按百分点 `37% → 37` 或比例 `37% → 0.37` 读取；
- 拆分列通常不能同时进入模型；专业模式仅允许原始分类因素按至少两个合规自定义组同时拆分；
- 不支持的角色不会被静默忽略；
- 未开放方法不会自动降级。

## 测试

```bash
pytest -q
```

0.4.1 最终回归包含 115 项自动化测试。43 种方法均通过服务与 HTTP 路径，另完成 350 个数据变体、100 个非默认高级参数和浏览器端即时分析/工作区交互审查。全项目覆盖率约 70%；排除保留兼容入口后约 80.3%；核心分析主链路约 84.0%。

### R 语言与 Python 双重校对

DataWork 的正式计算核心使用 Python、SciPy、statsmodels 和 Patsy。项目在开发阶段同时使用独立 R 脚本与 Python 计算核心进行双重校对：R 单独计算参考统计量，Python 对照程序逐项比较统计量、自由度、p 值及派生数据。R 不参与应用正式运行，也不属于桌面包或服务器部署依赖。

- [全部 47 种方法的 R 独立参考脚本](tests/reference/r/validate_all_methods.R)
- [全部方法的 R/Python 对照入口](scripts/compare_all_methods_r.py)
- [农业 CK/T 配对、NDR/Delta、Type III ANOVA 与 Wilks MANOVA 的 R 参考脚本](tests/reference/r/validate_agronomy_example_2.R)
- [农业参考数据（与用户测试数据有效前 7 列一致）](tests/reference/r/agronomy_example_2.csv)
- [农业与自定义拆分的 R/Python 对照入口](scripts/compare_r_reference.py)
- [Python 农业数据应用服务回归测试](tests/integration/test_agronomy_reference_dataset.py)
- [开发期双重校对与可复现说明](docs/REPRODUCIBILITY.md)

默认测试不会要求安装 R。需要执行开发期双重校对时，按可复现说明将 R 依赖安装到项目本地忽略目录，再显式运行对应对照入口。

## 完整源码包文档入口

- [项目规范总册](docs/PROJECT_STANDARD.md)
- [质量与审计总档](docs/QUALITY_AUDIT_RECORDS.md)
- [开发记录总档](docs/DEVELOPMENT_RECORDS.md)
- [用户使用手册](docs/USER_MANUAL.md)
- [发布与部署指南](docs/RELEASE_DEPLOYMENT_GUIDE.md)
- [完整源码包内容说明](SOURCE_PACKAGE_CONTENTS.md)
- [系统架构](docs/ARCHITECTURE.md)
- [统计方法与计算核心依赖手册（含项目组方法—依赖矩阵）](docs/STATISTICAL_METHODS.md)
- [V1.5 更新计划与实施记录](docs/V1.5_UPDATE_PLAN.md)
- [R 语言与 Python 双重校对说明](docs/REPRODUCIBILITY.md)
- [AI 助手说明](docs/AI_ASSISTANT.md)
