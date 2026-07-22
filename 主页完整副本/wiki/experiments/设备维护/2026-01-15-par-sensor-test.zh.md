---
title: PAR 传感器一致性测试
titleEn: PAR Sensor Consistency Test
summary: 在均匀光照条件下测试 64 通道 PAR 传感器的一致性，检测异常通道
summaryEn: Testing 64-channel PAR sensor consistency under uniform light, detecting anomalous channels
tags: [PAR, 传感器, 质控]
status: 已完成
pinned: false
---

# PAR 传感器一致性测试

**日期**：2026-01-15  
**项目**：设备维护  
**实验人员**：  

---

## 实验目的

在均匀光照条件下测试 SunScan 探针 64 通道 PAR 传感器的一致性，识别并记录异常通道。

## 测试条件

- **光照**：阴天散射光（均匀度最佳）
- **位置**：开阔无遮挡场地
- **探针朝向**：水平放置
- **测量次数**：3 次重复

## 结果

### 通道统计

| 统计量 | 数值 |
|-------|------|
| 通道均值 | 328 µmol m⁻² s⁻¹ |
| 标准差 | 12.4 |
| 变异系数 (CV) | 3.8% |
| 最小值 (通道) | 289 (Ch43) |
| 最大值 (通道) | 352 (Ch12) |

### 异常通道
- **Ch43**：偏低约 12%，可能需要清洁或校准
- **Ch12**：偏高约 7%，建议复查

## 结论
- 整体一致性良好（CV < 5%）
- Ch43 和 Ch12 需进一步检查
- 建议每季度进行一次一致性测试

## 相关条目
- [[PAR-Measurement]]
- [[SunScan-Data-Analysis]]
