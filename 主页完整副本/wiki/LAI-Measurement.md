# LAI Measurement

## What is LAI?

**Leaf Area Index (LAI)** is the total one-sided area of leaf tissue per unit ground surface area. It is a key parameter for understanding canopy structure and function.

## Measurement Methods

### 1. Indirect Methods (SunScan)
- **Principle**: Light extinction through canopy
- **Formula**: LAI = -ln(Transmitted/Incident) / (K × F)
  - K: extinction coefficient
  - F: beam fraction
- **Parameters**:
  - Leaf Angle Distribution Parameter: 1 (spherical)
  - Leaf Absorption: 0.85

### 2. SunScan Protocol
1. **Above canopy reference**
   - Record incident light (PAR)
   - Typical values: 1600-1900 µmol m⁻² s⁻¹

2. **Below canopy measurement**
   - Record transmitted light
   - Typical values: 100-800 µmol m⁻² s⁻¹

3. **Calculate LAI**
   - Use Beer-Lambert law
   - Account for beam fraction and zenith angle

### 3. Key Parameters
| Parameter | Description | Typical Range |
|-----------|-------------|---------------|
| Transmitted | Light below canopy | 100-800 µmol m⁻² s⁻¹ |
| Incident | Light above canopy | 1600-1900 µmol m⁻² s⁻¹ |
| Beam Fraction | Direct/diffuse ratio | 0.83-0.86 |
| Zenith Angle | Solar zenith angle | 21-37° |
| LAI | Calculated leaf area index | 0.5-6.0 |

## Data Quality Control

### Invalid Data
- **Negative LAI values** (e.g., -8.8, -8.6, -6.9)
  - Cause: Incident light = 0.2 (sensor malfunction)
  - Action: Remove from analysis

- **Very low LAI (< 0.3)**
  - May indicate gaps in canopy
  - Verify with field notes

### Outlier Detection
- Check for:
  - Unusual zenith angles
  - Extreme transmitted values
  - Inconsistent beam fractions

## Applications

### Canopy Structure
- LAI distribution across plots
- Seasonal changes
- Species differences

### Light Interception
- Relationship between LAI and light capture
- Canopy architecture effects

### Crop Production
- Yield prediction models
- Irrigation scheduling

## Related Topics
- [[PAR-Measurement]]
- [[SunScan-Data-Analysis]]
- [[Canopy-Structure]]
