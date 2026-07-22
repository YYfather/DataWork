---
title: LAI 测量校准实验
titleEn: LAI Measurement Calibration
summary: 使用标准光板对 SunScan 探针进行 LAI 测量校准，比较不同叶倾角参数下的计算结果
summaryEn: Calibrating SunScan probe LAI measurements using standard light panels, comparing results across leaf angle parameters
tags: [LAI, 校准, SunScan]
status: 已完成
pinned: true
---

# LAI 测量校准实验

**日期**：2026-05-10  
**项目**：SunScan 校验  
**实验人员**：  

---

## 实验目的

使用标准光板对 SunScan 探针进行 LAI 测量校准，验证不同叶倾角分布参数对 LAI 计算结果的影响，确定最佳参数配置。

## 实验方法

### 设备
- SunScan 探针 v1.03R
- BFS 光束比例传感器
- 标准光板（已知透射率）

### 步骤
1. 在均匀光照条件下，将 SunScan 探针置于标准光板下方
2. 调整光板角度模拟不同叶倾角分布
3. 记录 PAR 透射数据
4. 使用不同 Leaf Angle Distribution Parameter (0.5-2.0) 计算 LAI
5. 与标准光板的理论 LAI 值对比

## 实验结果

| 参数设置 | 计算 LAI | 理论 LAI | 误差 (%) |
|---------|---------|---------|---------|
| LAD=1.0 (球形) | 2.85 | 3.00 | 5.0 |
| LAD=0.8 | 3.12 | 3.00 | 4.0 |
| LAD=1.2 | 2.63 | 3.00 | 12.3 |

### 结论
- LAD=0.8 在该条件下误差最小
- 球形分布（LAD=1.0）结果可接受，误差在 5%
- 叶倾角参数对 LAI 计算结果影响显著

## 待办事项
- [ ] 在不同天顶角条件下重复实验
- [ ] 检验 Leaf Absorption 参数的敏感性

## 相关条目
- [[LAI-Measurement]]
- [[SunScan-Data-Analysis]]
