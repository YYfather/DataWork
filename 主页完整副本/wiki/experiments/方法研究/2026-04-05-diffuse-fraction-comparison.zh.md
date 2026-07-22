---
title: 散射光比例对比实验
titleEn: Diffuse Fraction Comparison
summary: 对比不同天气条件下 SunScan BFS 传感器测量的散射光比例与理论模型
summaryEn: Comparing diffuse light fraction measured by SunScan BFS sensor under different weather conditions against theoretical models
tags: [散射光, BFS, 模型]
status: 已完成
pinned: false
---

# 散射光比例对比实验

**日期**：2026-04-05  
**项目**：方法研究  
**实验人员**：  

---

## 实验目的

对比不同天气条件（晴天、多云、阴天）下 SunScan BFS 传感器测量的散射光比例（Beam Fraction），验证传感器在不同光照条件下的可靠性。

## 实验方法

### 设备
- SunScan 探针 + BFS 传感器
- 手持式气象站

### 步骤
1. 在开阔无遮挡场地架设 BFS 传感器
2. 分别在晴天、多云、阴天三种条件下连续测量 30 分钟
3. 每 30 秒记录一次 Beam Fraction 数据
4. 同步记录天气状况和太阳高度角

## 实验结果

### Beam Fraction 对比

| 天气条件 | 平均 BF | 标准差 | 样本数 |
|---------|--------|-------|-------|
| 晴天 | 0.85 | 0.03 | 60 |
| 多云 | 0.52 | 0.18 | 60 |
| 阴天 | 0.12 | 0.05 | 60 |

### 分析
- 晴天条件下 BF 稳定在 0.82-0.88，与理论值一致
- 多云天气 BF 波动最大（CV=35%），云层移动导致直射/散射比例快速变化
- 阴天 BF 稳定在低值，散射光占主导

## 结论
- BFS 传感器在稳定天气条件下表现可靠
- 多云天气测量需增加采样次数以获取代表性均值
- 建议在野外测量时同步记录天气状况

## 相关条目
- [[PAR-Measurement]]
- [[Light-Interception]]
