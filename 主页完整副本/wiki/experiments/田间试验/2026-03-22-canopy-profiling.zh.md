---
title: 冠层结构剖面测量
titleEn: Canopy Structure Profile Measurement
summary: 对玉米冠层进行垂直剖面 PAR 测量，分析不同高度层的光分布特征
summaryEn: Vertical profile PAR measurements in maize canopy, analyzing light distribution across height layers
tags: [冠层, 剖面, PAR分布]
status: 已完成
pinned: true
---

# 冠层结构剖面测量

**日期**：2026-03-22  
**项目**：田间试验  
**实验人员**：  

---

## 实验目的

对玉米冠层进行垂直剖面 PAR 测量，分析不同高度层的光分布特征，为作物生长模型提供参数。

## 实验设计

- **作物**：玉米（品种：郑单958）
- **生育期**：抽雄期
- **样地**：3 个重复小区
- **测量高度**：距地面 0cm、50cm、100cm、150cm、200cm（冠层顶部）

## 测量结果

### PAR 垂直分布

| 高度 (cm) | PAR (µmol m⁻² s⁻¹) | 相对光强 (%) |
|----------|-------------------|------------|
| 200 (冠层顶) | 1650 | 100 |
| 150 | 820 | 49.7 |
| 100 | 350 | 21.2 |
| 50 | 120 | 7.3 |
| 0 (地面) | 45 | 2.7 |

### 光衰减曲线
```
相对光强 = 100 × exp(-0.45 × 累计LAI)
```
拟合 R² = 0.97

## 初步分析
- 冠层上部 50cm 截获了约 50% 的 PAR
- 到达地面的 PAR 不足 3%，符合密植玉米冠层特征
- 消光系数 K ≈ 0.45，接近文献值

## 照片记录

*（此处插入冠层照片）*

## 相关条目
- [[Canopy-Structure]]
- [[PAR-Measurement]]
- [[Light-Interception]]
