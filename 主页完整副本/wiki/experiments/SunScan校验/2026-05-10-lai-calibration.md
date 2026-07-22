---
title: LAI Measurement Calibration
titleEn: LAI Measurement Calibration
summary: Calibrating SunScan probe LAI measurements using standard light panels, comparing results across leaf angle parameters
summaryEn: Calibrating SunScan probe LAI measurements using standard light panels, comparing results across leaf angle parameters
tags: [LAI, Calibration, SunScan]
status: completed
pinned: true
---

# LAI Measurement Calibration

**Date**: 2026-05-10  
**Project**: SunScan Verification  
**Personnel**:  

---

## Objective

Calibrate the SunScan probe using standard light panels to verify the impact of leaf angle distribution parameters on LAI calculation and determine optimal parameter settings.

## Method

### Equipment
- SunScan probe v1.03R
- BFS Beam Fraction Sensor
- Standard light panels (known transmittance)

### Procedure
1. Place SunScan probe below standard light panel under uniform light
2. Adjust panel angle to simulate different leaf angle distributions
3. Record PAR transmission data
4. Calculate LAI using different Leaf Angle Distribution Parameters (0.5-2.0)
5. Compare against theoretical LAI of the standard panel

## Results

| LAD Setting | Calculated LAI | Theoretical LAI | Error (%) |
|------------|---------------|-----------------|-----------|
| LAD=1.0 (spherical) | 2.85 | 3.00 | 5.0 |
| LAD=0.8 | 3.12 | 3.00 | 4.0 |
| LAD=1.2 | 2.63 | 3.00 | 12.3 |

### Conclusion
- LAD=0.8 gives the smallest error under these conditions
- Spherical distribution (LAD=1.0) is acceptable with ~5% error
- Leaf angle parameters significantly affect LAI results

## Todos
- [ ] Repeat experiment at different zenith angles
- [ ] Test sensitivity of Leaf Absorption parameter

## Related
- [[LAI-Measurement]]
- [[SunScan-Data-Analysis]]
