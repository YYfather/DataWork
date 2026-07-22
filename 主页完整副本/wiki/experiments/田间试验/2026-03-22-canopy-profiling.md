---
title: Canopy Structure Profile Measurement
titleEn: Canopy Structure Profile Measurement
summary: Vertical profile PAR measurements in maize canopy, analyzing light distribution across height layers
summaryEn: Vertical profile PAR measurements in maize canopy, analyzing light distribution across height layers
tags: [Canopy, Profile, PAR]
status: completed
pinned: true
---

# Canopy Structure Profile Measurement

**Date**: 2026-03-22  
**Project**: Field Trial  
**Personnel**:  

---

## Objective

Measure vertical PAR profile in a maize canopy to analyze light distribution across height layers and provide parameters for crop growth models.

## Design

- **Crop**: Maize (Zhengdan 958)
- **Growth Stage**: Tasseling
- **Plots**: 3 replicates
- **Measurement Heights**: 0cm, 50cm, 100cm, 150cm, 200cm (canopy top)

## Results

### PAR Vertical Distribution

| Height (cm) | PAR (µmol m⁻² s⁻¹) | Relative Light (%) |
|------------|-------------------|-------------------|
| 200 (top) | 1650 | 100 |
| 150 | 820 | 49.7 |
| 100 | 350 | 21.2 |
| 50 | 120 | 7.3 |
| 0 (ground) | 45 | 2.7 |

### Light Extinction Curve
```
Relative Light = 100 × exp(-0.45 × cumulative LAI)
```
R² = 0.97

## Analysis
- Upper 50cm of canopy intercepts ~50% of PAR
- PAR reaching ground is <3%, consistent with dense maize canopy
- Extinction coefficient K ≈ 0.45, close to literature values

## Photos

*(Insert canopy photos here)*

## Related
- [[Canopy-Structure]]
- [[PAR-Measurement]]
- [[Light-Interception]]
