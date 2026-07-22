# LI-6800 棉花光合参数测定操作教程：方案 B（标准化环境日动态）

> **适用对象**：使用 LI-COR LI-6800，在一天中多个时间点，把棉花叶片置于相同的 CO₂、光照、叶温和水汽压亏缺条件下，比较其标准化气体交换能力。  
> **推荐叶室与光源**：6800-12A 透明小叶室 + 6800-02 红蓝光源；也可使用 6800-01A 荧光叶室。  
> **文档版本**：v1.0，2026-07-11。  
> **重要说明**：方案 B 的数据代表叶片在预设叶室条件下的表现，不等同于自然环境下当时的实际光合速率。叶温依然是关键变量，但在本方案中被控制为相同 setpoint。

---

## 1. 方案目标

方案 B 通过固定叶室条件，尽量排除一天中外界光照、空气温度、湿度和 CO₂ 波动，使不同时间点的数据可用于分析：

- 棉花叶片是否存在独立于即时环境的昼夜节律或生理状态变化；
- 不同处理在相同测量条件下的潜在光合能力；
- 上午、正午和下午的 A、gsw、E、Ci、WUE 差异；
- 高温、干旱、养分或品种处理导致的内在光合能力变化。

该方案不能替代自然日动态。研究“叶温在自然环境下如何变化”应使用方案 A；研究“在相同叶温下，不同时间的能力是否改变”使用方案 B。

---

## 2. 推荐标准化设定

下表是一套可直接用于棉花预试验的默认参数。正式实验前应使用 3–5 株代表性棉花做光响应和稳定时间预试验。

| 控制项目 | 推荐默认值 | 说明 |
|---|---:|---|
| Flow | 500 μmol s⁻¹ | 低通量胁迫叶可预试验后降至 300，但所有组必须一致 |
| ΔP | 0.1 kPa | 可在需要时使用 0.2 kPa |
| Fan | 10,000 rpm | 保证叶室充分混合 |
| CO₂ target | `CO2_s = 400 μmol mol⁻¹` | 也可预先规定 420，但全试验保持一致 |
| H₂O target | `VPDleaf = 1.5 kPa` | 一般可使叶室处于适宜湿度范围；高湿条件注意结露 |
| Leaf temperature | `Tleaf = 30 ℃` | 棉花工作默认值；若研究区或预试验更适合 28 ℃，可改为 28 ℃ |
| Light | 1500 μmol m⁻² s⁻¹ | 棉花向阳叶的起始值，必须用光响应预试验验证 |
| Color Spec | `r90` | 约 90% 红光、10% 蓝光 |
| O₂ | 21% | 普通空气 |
| Geometry | Broadleaf | 棉花阔叶 |
| Leaf area S | 9 cm² 或实际面积 | 3 × 3 cm 完全填满时为 9 cm² |
| K | 0.5，暂用 | 最好用本材料上下表面气孔数据修正 |

### 2.1 为什么光强不能直接照搬

棉花叶片光饱和点受品种、叶龄、氮素、水分和生长光环境影响。文献中常见向阳棉叶在约 1000 μmol m⁻² s⁻¹以上增幅减小，但老叶、遮阴叶和胁迫叶可能更早饱和。1500 是便于排除光限制的工作起点，不是所有棉花的固定真值。

预试验规则：

- 若 1200 与 1500 下 A 差异很小，优先选 1200，减少光抑制和叶温控制负担；
- 若 1500 下 A 仍明显增加且没有光抑制，可用 1500；
- 同一正式实验不能在不同时间点更换光强。

---

## 3. 设备与耗材

### 3.1 必备

- LI-6800 主机；
- LI-6850 分析器头；
- 主机—头部通信电缆与供气管；
- 6800-12A 透明小叶室；
- 6800-02 红蓝光源；
- 3 × 3 cm 孔径和匹配底板；
- 叶温热电偶 `T1`；
- 8 g 高质量、无油 CO₂ 小钢瓶，或外接纯 CO₂ 钢瓶及官方适配器；
- 干燥剂、加湿柱、苏打石灰；
- 电池和备用电池；
- FAT/FAT32 U 盘；
- 标签、记录表和秒表；
- 可选：缓冲瓶，用于稳定和过滤进入主机的基础空气；
- 可选：T2 环境热电偶和外置 LI-190R，用于记录叶片夹入前环境。

### 3.2 6800-01A 替代配置

若使用 6800-01A 荧光叶室：

- 叶面积按 6 cm² 或 2 cm² 孔径设置；
- 光源在 `Environment > Fluorometry` 中控制；
- 不测荧光时，`Flr Action at log = 0: Nothing`；
- 测荧光时需另行设置闪光、暗适应和 fluorescence logging，本教程不展开荧光参数。

---

## 4. 棉花实验设计

### 4.1 叶片规则

- 冠层比较：主茎上部最年轻的完全展开向阳叶；
- 铃叶关系：同一果枝和果节位置的铃对叶；
- 所有时间点、处理和重复必须使用同一规则；
- 避开主脉、粗侧脉、虫孔、病斑和卷曲区。

### 4.2 同一叶还是不同叶

**重复测量设计**：同一株同一片叶在多个时间点测量，统计效率高。应：

- 预先标记叶片；
- 尽量使用相同的平整叶肉区域；
- 若重复夹持留下明显压痕，预先规划相邻的非重叠叶肉位置；
- 把植株/叶片作为随机效应。

**独立取样设计**：每个时间点使用不同植株或叶片，可避免重复夹持影响，但需要更多生物学材料。不能把同株多片叶当作完全独立重复。

### 4.3 时间点与顺序

建议 07:00、09:00、11:00、13:00、15:00、17:00。不同处理使用轮换或随机顺序，避免固定先后。每个时间区组应在尽量短的时间内完成。

---

## 5. 测量前一天准备

1. 标记植株、目标叶片和可夹持区域。
2. 确定最终 setpoint，并写入预注册表；正式测量中禁止随意改变。
3. 电池充满，准备备用电池；标准化温控和光源耗电较高。
4. 准备足够 CO₂：8 g 小钢瓶刺破后即使不使用也会逐渐耗尽，官方资料给出的典型持续时间约 8 h。
5. 检查干燥剂、加湿柱和苏打石灰。
6. 把 U 盘格式化为 FAT/FAT32。
7. 建立文件命名和用户字段规则。
8. 准备光响应预试验和诱导时间记录表。

---

## 6. 物理连接：关机状态完成

### 6.1 主机气路材料

1. H₂O SCRUB 填装有效干燥剂，距顶部保留少量空间。
2. H₂O ADD：Nafion 柱加入过滤水或去离子水，盖紧；不得渗漏。
3. CO₂ SCRUB 填装有效苏打石灰，避免粉尘。
4. 检查 O 形圈和螺纹清洁、干燥。

### 6.2 安装 CO₂ 小钢瓶

1. 确认主机处于安全位置，远离太阳暴晒。
2. 将高质量无油 8 g CO₂ 小钢瓶大端先放入支架。
3. 拧紧至遇到阻力后，快速再转约半圈刺破。
4. 记录“新钢瓶”状态。
5. 不得在带压时快速拆除；必须按官方方法缓慢泄压。

若使用外接钢瓶，只使用官方适配器和合适减压装置，压力按设备要求设置，并运行 Soda Lime–CO₂ 系统测试。

### 6.3 连接头部电缆和供气管

1. LI-6800 关机。
2. 通信电缆接到主机 `HEAD 1` 或 `HEAD 2`，另一端接分析器头；红点朝上。
3. 供气管连接主机 `AIR OUT` 和分析器头。
4. 检查接头完全插入且没有折弯。
5. 通电后禁止插拔头部电缆。

### 6.4 安装 6800-12A 和孔径

1. 用原配固定螺钉安装叶室，均匀拧紧。
2. 安装 3 × 3 cm 上下孔径和匹配底板。
3. 上下孔径尺寸、方向必须一致。
4. 安装白色垫圈并检查密封。
5. 叶室关闭和 Parked 位置应正常。

### 6.5 安装叶温热电偶

1. T1 从下叶室插入，接到 `T1`。
2. 珠体通常高出垫圈约 2 mm。
3. 夹叶后应轻触叶片背面。
4. 不得压在主脉或接触金属。
5. 若 T1 不能可靠接触叶片，不应使用 Tleaf 控制；应先重新调整或改用能量平衡并重新设计方案。

### 6.6 安装 6800-02 光源

1. 把 6800-02 正确安装到 6800-12A 上方。
2. 光源电缆连接分析器头的 `LS` 接口。
3. 固定电缆，避免受力。
4. 开机后在 `Environment > Light > Head Light Source` 确认光源被识别。
5. 不得直视 LED 光源。

### 6.7 可选缓冲瓶

方案 B 的 CO₂ 和 H₂O由仪器控制，但缓冲瓶仍可减小进气扰动和灰尘。使用时按方案 A 方法连接，放在上风向。

---

## 7. 开机、自检和叶室识别

1. 检查全部物理连接。
2. 装入电池或接电源并开机。
3. 检查日期、时间和时区。
4. `Start Up > Chamber Setup` 中确认：
   - 6800-12A；
   - 6800-02 已识别；
   - 孔径尺寸和方向正确；
   - Complete Gas Exchange；
   - Oxygen = 21%。
5. 关闭空叶室。
6. `Start Up > Warmup/System Tests > Warmup Tests > Start`。
7. 等待约 10–15 min，处理所有关键失败项。
8. 运行 `Chamber Leak Test`。
9. 若新装 CO₂ 钢瓶，运行相关 CO₂/Soda Lime 测试，确认注入器可达到设定值。
10. 检查风扇、热交换器和湿度控制测试。

---

## 8. Constants 的完整设置

### 8.1 Gas Exchange

进入 `Constants > Gas Exchange`：

| 参数 | 设置 |
|---|---|
| ChType | 6800-12A |
| Geometry | Broadleaf |
| S | 9 cm²，或实际叶面积 |
| K | 0.5 暂用，最好实测 |
| O₂ | 21% |

棉花叶片如果没有完全填满孔径，记录后必须用真实面积重算 A、E 和导度相关参数。

### 8.2 Leaf Temperature

进入 `Constants > Leaf Temperature`：

- 选择 `Measured`；
- T1 作为叶温来源；
- 检查 `TleafCnd` 来源；
- 方案 B 的温度控制依赖该测量值，接触不可靠时不能继续正式测量。

### 8.3 Leaf Light

- 选择人工 LED 光源作为叶片光源；
- 保持默认吸收率，除非有实测值；
- 若使用 6800-02 单面照光，确保 Total Leaf Q 来源配置正确。

---

## 9. Environment：方案 B 的完整设置

### 9.1 Flow

`Environment > Flow`

- Flow: `On`
- Pump Speed: `Auto`
- Flow: `500 μmol s⁻¹`
- ΔP: `0.1 kPa`

若胁迫叶片 A 很低、ΔCO₂ 太小，可在预试验中降到 300 μmol s⁻¹。正式实验中不能因处理不同而使用不同流量。

### 9.2 Fan

`Environment > Fan`

- Mixing fan: `On`
- Fan speed: `10,000 rpm`

### 9.3 CO₂

`Environment > CO2`

- CO₂ injector: `On`
- Control target: 优先 `CO2_s`
- Setpoint: `400 μmol mol⁻¹`
- Soda Lime/Scrub: `Auto` 或按本机界面启用

为什么优先 CO2_s：叶片实际经历的是样品室 CO₂，可减少不同 A 导致的叶室 CO₂ 差异。控制 CO2_r 可更快，但仅适合不同样品 A 接近且经过预试验的快速测量。

若全实验采用 420 μmol mol⁻¹，也可以，但必须从预试验到正式测量全部一致，并在论文中报告。

### 9.4 H₂O

`Environment > H2O`

- H₂O: `On`
- Control: `VPDleaf`
- Setpoint: `1.5 kPa`

操作：

1. 先让 Tleaf 接近 30 ℃；
2. 再开启 VPDleaf 控制；
3. 检查 RH_s 是否处于仪器可实现且不结露范围；
4. 如果出现 H2O setpoint override、高湿警告或 AutoDry，不能记录；
5. 不要把 VPD 设为 0；
6. 极端高湿环境下，可改用 RH_air 60–70%，但所有时间点必须一致，并报告实际 VPDleaf。

### 9.5 Temperature

`Environment > Temperature`

- Temperature: `On`
- Control: `Tleaf`
- Setpoint: `30.0 ℃`

操作：

1. 确认 T1 接触叶片；
2. 输入 30.0 ℃；
3. 等待 Tleaf、Tair、Txchg 达到稳定；
4. 检查目标温度高于露点并且无结露风险；
5. 若仪器在正午无法把叶温降至 30 ℃，不要强行记录，应：
   - 遮挡分析器头但不能遮挡测量叶片；
   - 改善主机通风；
   - 把标准温度提高到全天均可达到的值，例如 32 ℃；
   - 重新开始并对全部时间点采用同一温度。

正式实验一旦开始，不能只在正午改变 Tleaf setpoint。

### 9.6 Light

使用 6800-02：

`Environment > Light > Head Light Source`

- Control Mode: `Setpoint/On`
- Setpoint: `1500 μmol m⁻² s⁻¹`
- Color Spec: `r90`

使用 6800-01A：

`Environment > Fluorometry/Light`

- Control Mode: `Setpoint`
- Setpoint: `1500 μmol m⁻² s⁻¹`
- Color Spec: `r90`

注意：

- 叶片夹入前先开启目标光强；
- 叶片由自然弱光转到 1500 时可能需要较长光诱导；
- 不要仅因为 Stability 达到 4/4 就认为生理稳定；
- 不直视光源。

### 9.7 Auto Controls

- 检查并关闭遗留 Auto Controls；
- 本方案使用固定 setpoint，不使用自动阶梯或 tracking；
- 确保没有背景程序改变 CO₂、H₂O、光照或温度。

---

## 10. 匹配与 Range Match

### 10.1 推荐流程

1. 预热测试后做一次 Manual Match。
2. 正式实验前获取并启用有效的 CO₂ 和 H₂O Range Match。
3. H₂O point match 设为 `Never match`。
4. CO₂ 使用 Range Match；分析器头温度变化大时做 point match。
5. 每个时间区组开始前检查匹配状态。

### 10.2 没有 Range Match 时

`Log Setup/Log Files > Match Options`

- CO₂：`Only match if` 或每个时间区组手动匹配；
- H₂O：`Never match`；
- 不建议在每片叶记录前都执行长时间 H₂O point match；
- 匹配期间不要记录。

---

## 11. Stability 和日志设置

### 11.1 Stability

建议起始值：

| 变量 | Slope Limit | Period |
|---|---:|---:|
| CO2R & CO2S | 1 | 20 s |
| H2OR & H2OS | 1 | 20 s |
| A.GasEx | 1 | 20 s |
| gsw.GasEx | 0.1 | 20 s |

CO₂ 和 H₂O控制较稳定，因此可使用比方案 A 更严格的气体稳定阈值。

### 11.2 Logging Options

- 勾选 `Also log data to Excel file`；
- 6800-02 不需要荧光动作；
- 6800-01A 且不测荧光：`Flr Action at log = 0: Nothing`；
- 开启 `Prompt on manual log`；
- User Constants：Treatment、Plant_ID、Leaf_ID、Time_Block、Leaf_Position、Induction_Time、Notes；
- 每个时间区组可单独建文件，也可全天一个文件。

---

## 12. 预试验：正式实验前必须完成

### 12.1 确定光强

在 3–5 片代表性棉花叶上测试 1000、1200、1500 和 1800 μmol m⁻² s⁻¹：

1. 固定 CO₂、Tleaf 和 VPDleaf；
2. 从较高光开始或进行完整光响应；
3. 每个光强等待 A 稳定；
4. 选择能消除光限制、但不会引起 A 下降或叶片过热的最低光强；
5. 把选择结果写入正式方案。

### 12.2 确定诱导时间

1. 选择早晨、正午、下午代表性叶片。
2. 从自然环境夹入标准叶室。
3. 记录 A 和 gsw 从夹叶到稳定所需时间。
4. 正式实验采用足以覆盖大多数样品的最短统一等待规则，例如：
   - 最少等待 3 min；
   - 且 A、gsw、Tleaf、VPDleaf 达到稳定；
   - 叶片从深度遮阴或清晨低光进入高光时，可能需要 10–20 min 甚至更久。
5. 不要让不同处理使用不同的主观等待标准。

### 12.3 确定温度可实现性

在最热时间检查仪器是否能稳定控制 Tleaf = 30 ℃。若不能，应在正式试验前把 setpoint 调整到全天可实现的值，而不是测量中途改变。

---

## 13. 每个时间区组开始前

1. 检查电池、CO₂ 余量、干燥剂、加湿柱和苏打石灰。
2. 检查叶室和 T1。
3. 运行或检查 Range Match/point match。
4. 空叶室下设置并确认：
   - Flow 500；
   - Fan 10,000；
   - CO2_s 400；
   - VPDleaf 1.5；
   - Tleaf 30；
   - Light 1500，r90。
5. 用试叶确认所有 setpoint 可达到。
6. 新建或切换日志文件。
7. 按轮换顺序开始处理测量。

---

## 14. 每片叶的标准化测量步骤

1. 核对处理、植株、叶片和时间区组。
2. 记录叶片夹入前自然环境：外界光强、环境温度、RH、叶片是否受光。
3. 确认人工光源已在目标 setpoint。
4. 打开叶室，将叶片平整放入，避开主脉。
5. Parked 调整位置，再完全关闭。
6. 检查 T1 接触叶片背面。
7. 立即观察：
   - Tleaf 是否向 30 ℃收敛；
   - CO2_s 是否向 400 收敛；
   - VPDleaf 是否向 1.5 收敛；
   - Qin 是否为 1500；
   - Flow 和 Fan 是否正常。
8. 开始计时并记录 Induction_Time。
9. 等待环境稳定后继续观察 A 和 gsw：
   - Stability 4/4；
   - A 不再持续上升或下降；
   - gsw 趋稳；
   - Tleaf 在预定容差内；
   - VPDleaf 在预定容差内；
   - CO2_s 在预定容差内。
10. 点击 Log。
11. 填写用户字段和异常备注。
12. 打开叶室，轻柔取出叶片。
13. 检查夹痕和损伤。
14. 下一片叶前确认 setpoint 已恢复。

### 14.1 推荐容差

正式实验前预先规定并写入方案，例如：

- Tleaf：setpoint ± 0.3 ℃；
- CO2_s：setpoint ± 5 μmol mol⁻¹；
- VPDleaf：setpoint ± 0.1 kPa；
- Qin：setpoint ± 1% 或按本机稳定显示；
- A、gsw：满足 Stability 且实时图无单向漂移。

这些是建议的项目内质控标准，不是 LI-COR 强制阈值。应根据本机性能和预试验调整。

---

## 15. 叶温控制专项要求

1. `TleafCnd` 必须来自 T1 测量，而不是意外切换到 Energy Balance。
2. 热电偶珠必须接触叶肉，不能压在粗叶脉上。
3. Tleaf 达标不代表叶片生理已稳定；仍需看 A 和 gsw。
4. 高温高湿环境下，控制到较低叶温可能造成结露；露点警告或 AutoDry 时停止测量。
5. 若温控达到极限：
   - 不得只对部分样品放宽温度；
   - 停止该时间区组；
   - 改用全天可实现的新 setpoint，并重新开始完整实验；
   - 或改用方案 A 测自然叶温。
6. 保存 Tleaf、TleafCnd、TleafEB、Tair 和 Txchg，便于审查控制质量。

---

## 16. 必须记录的数据

- A、gsw、E、Ci；
- CO2_r、CO2_s；
- H2O_r、H2O_s、RH_s；
- Tleaf、TleafCnd、TleafEB、Tair、Txchg；
- VPDleaf；
- Qin/Head light source output；
- Flow、ΔP、Fan、Leak；
- S、K、Geometry；
- 精确时间、Treatment、Plant_ID、Leaf_ID、Time_Block；
- Induction_Time；
- 夹叶前环境光、环境温度和 RH；
- 异常与重测标记。

后期可计算 WUE = A/E、iWUE = A/gsw、Ci/Ca。

---

## 17. 质量控制与剔除规则

建议在分析前锁定以下规则：

- Warmup 或 Chamber Leak 关键测试失败的数据不进入正式集；
- TleafCnd 来源错误或热电偶接触失败的数据剔除；
- 未达到温度、CO₂、VPD 或光照容差的数据重测；
- A 或 gsw 持续漂移时记录的数据重测；
- AutoDry、结露、高湿报警期间的数据剔除；
- 叶面积错误的数据必须重算；
- 光源或环境控制背景程序意外改变 setpoint 的数据剔除；
- 明显叶片损伤、压痕或漏气的数据标记；
- 处理之间采用不同等待标准的数据不得直接比较。

---

## 18. 常见问题

### 18.1 早晨叶片很久不稳定

早晨自然光较低，夹入 1500 光强后需要光诱导和气孔开放。延长等待时间，不能只看 4/4。也可提前用相同光源诱导，但所有处理必须使用相同规则。

### 18.2 正午无法降到 30 ℃

说明 setpoint 超出当时可实现范围。正式实验前应提高统一 setpoint，或使用遮阳保护分析器头但不能遮挡叶片和影响叶片夹入前状态。

### 18.3 CO2_s 不稳定

检查 CO₂ 钢瓶、苏打石灰、注入器、Flow、叶室漏气和控制对象。若 CO₂ 小钢瓶已刺破较久，可能接近耗尽。

### 18.4 VPDleaf 达不到

检查加湿柱水量、干燥剂、叶温、环境露点和 H₂O setpoint override。不要在高湿报警时记录。

### 18.5 A 达到稳定但 gsw 仍变化

说明气孔尚未完全适应。若研究需要稳态气孔参数，应继续等待；若仅研究快速光合能力，也必须在方法中预先规定统一的记录规则。

### 18.6 胁迫叶 ΔCO₂ 太小

预试验后可把流量从 500 降到 300 μmol s⁻¹，提高信噪比；随后所有处理、时间点都用同一流量，并重新做匹配和稳定性检查。

---

## 19. 数据导出与关机

1. `Close Log`。
2. 等待 Excel 文件完全写入。
3. U 盘插入主机。
4. `Tools > Manage Files > Copy files to USB`。
5. 复制日志、配置和必要的诊断文件。
6. 确认复制完成，点击 `Eject`。
7. 单击电源键，选择 `Shutdown`。
8. 完全关机后：
   - 取下并排空 Nafion 加湿柱；
   - 清除叶室残片；
   - 叶室置于 Parked；
   - 若长期存放，移除 CO₂ 钢瓶和电池；
   - 仪器存放在箱内，避免高温和高湿。

---

## 20. 推荐记录表

| 日期 | 精确时间 | 处理 | 植株号 | 叶号 | 夹叶前环境光 | 夹叶前环境温度 | 诱导时间 | A | gsw | E | Ci | CO2_s | TleafCnd | VPDleaf | Qin | 是否达标 | 备注 |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|

---

## 21. 数据分析建议

- 同一叶片多时间点测量：混合效应或重复测量模型；
- 固定效应：Treatment、Time、Treatment × Time；
- 随机效应：Plant_ID/Leaf_ID；
- 由于叶室条件固定，仍应把实际 TleafCnd、VPDleaf、CO2_s 和 Qin 作为质控变量；
- 可比较方案 A 与 B：
  - A 反映当时实际环境表现；
  - B 反映标准条件下潜在能力；
  - 两者差异有助于区分环境限制与叶片内在状态变化。

---

## 22. 一页式检查清单

### 开机前

- [ ] CO₂ 小钢瓶、干燥剂、加湿柱、苏打石灰准备好
- [ ] 头部电缆在关机状态连接
- [ ] 6800-12A、6800-02、孔径、垫圈和 T1 正确
- [ ] Warmup Tests 通过
- [ ] Chamber Leak Test 通过
- [ ] CO₂ 注入器正常

### 系统设置

- [ ] Complete Gas Exchange、O₂ 21%
- [ ] Broadleaf、S 正确、K 已定义
- [ ] Leaf temp source = Measured/T1
- [ ] Flow 500、ΔP 0.1
- [ ] Fan 10,000
- [ ] CO2_s 400
- [ ] VPDleaf 1.5
- [ ] Tleaf 30 ℃
- [ ] Light 1500、r90
- [ ] Auto Controls 无遗留程序
- [ ] Match/Range Match 正常
- [ ] Log file 已打开

### 每片叶

- [ ] 样品信息正确
- [ ] 避开叶脉、叶片填满孔径
- [ ] T1 接触叶肉
- [ ] Tleaf、CO2_s、VPDleaf、Qin 达标
- [ ] A、gsw 真正稳定
- [ ] 诱导时间已记录
- [ ] 无结露、AutoDry 或报警

### 结束

- [ ] Close Log 并等待 Excel 写完
- [ ] USB 复制和 Eject
- [ ] 正常 Shutdown
- [ ] 取下加湿柱
- [ ] 叶室 Parked

---

## 23. 参考资料

1. 用户上传资料：《LI-6800 快速上手实验指导手册》，实验二“植物光合特征和光合效率测量实验”、实验三“光响应曲线”和相关附录。
2. [LI-COR: Assembling the LI-6800](https://www.licor.com/support/LI-6800/topics/assembly.html)
3. [LI-COR: Installing the small leaf chamber](https://www.licor.com/support/LI-6800/topics/chamber-3x3.html)
4. [LI-COR: Preparing for measurements](https://www.licor.com/support/LI-6800/topics/making-leaf-level-measurements.html)
5. [LI-COR: Leaf chamber software controls](https://www.licor.com/support/LI-6800/topics/leaf-measurement-controls.html)
6. [LI-COR: Flow control](https://www.licor.com/support/LI-6800/topics/environment-flow-control.html)
7. [LI-COR: H₂O control](https://www.licor.com/support/LI-6800/topics/environment-h2o-control.html)
8. [LI-COR: Temperature control](https://www.licor.com/support/LI-6800/topics/environment-temperature-control.html)
9. [LI-COR: Light control](https://www.licor.com/support/LI-6800/topics/environment-light-control.html)
10. [LI-COR: Matching the IRGAs](https://www.licor.com/support/LI-6800/topics/matching-the-analyzers.html)
11. [LI-COR: Warmup tests](https://www.licor.com/support/LI-6800/topics/system-tests-warmup.html)
12. [LI-COR: Transferring files](https://www.licor.com/support/LI-6800/topics/file-transfer.html)
13. Echer FR et al. 2015. [Cotton leaf gas exchange responses to irradiance and leaf aging](https://link.springer.com/article/10.1007/s10535-015-0484-3).
14. [Cotton Physiology: Light and the Cotton Plant](https://www.cotton.org/foundation/upload/Stress-Physiology-in-Cotton_Chapter4.pdf).
15. Devi MJ et al. 2018. [Transpiration Response of Cotton to Vapor Pressure Deficit and Its Relationship With Stomatal Traits](https://pmc.ncbi.nlm.nih.gov/articles/PMC6218332/).
