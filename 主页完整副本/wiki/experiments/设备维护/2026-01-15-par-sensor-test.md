---
title: PAR Sensor Consistency Test
titleEn: PAR Sensor Consistency Test
summary: Testing 64-channel PAR sensor consistency under uniform light, detecting anomalous channels
summaryEn: Testing 64-channel PAR sensor consistency under uniform light, detecting anomalous channels
tags: [PAR, Sensor, QC]
status: completed
pinned: false
---

# PAR Sensor Consistency Test

**Date**: 2026-01-15  
**Project**: Equipment Maintenance  
**Personnel**:  

---

## Objective

Test the consistency of the SunScan probe's 64-channel PAR sensor under uniform light conditions, identify and record anomalous channels.

## Conditions

- **Light**: Overcast diffuse light (best uniformity)
- **Location**: Open area with no obstructions
- **Probe Orientation**: Horizontal
- **Replicates**: 3

## Results

### Channel Statistics

| Statistic | Value |
|-----------|-------|
| Channel Mean | 328 µmol m⁻² s⁻¹ |
| Std Dev | 12.4 |
| CV | 3.8% |
| Min (channel) | 289 (Ch43) |
| Max (channel) | 352 (Ch12) |

### Anomalous Channels
- **Ch43**: ~12% low, may need cleaning or calibration
- **Ch12**: ~7% high, recommend re-check

## Conclusion
- Overall consistency is good (CV < 5%)
- Ch43 and Ch12 require further inspection
- Recommend quarterly consistency tests

## Related
- [[PAR-Measurement]]
- [[SunScan-Data-Analysis]]
