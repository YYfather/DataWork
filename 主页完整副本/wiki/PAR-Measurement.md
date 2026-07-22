# PAR Measurement

## What is PAR?

**Photosynthetically Active Radiation (PAR)** refers to the portion of the solar spectrum (400-700 nm) that plants can use for photosynthesis.

## Measurement Methods

### 1. SunScan Probe
- **Device**: SunScan probe v1.03R (C) JGW 2020/05/22
- **Sensors**: 64 channels (1-64, including tip sensor 64)
- **External sensor**: BFS (Beam Fraction Sensor)
- **Output**: PAR values in µmol m⁻² s⁻¹

### 2. Measurement Protocol
1. **Above canopy reference** (Sample 1)
   - Place probe above canopy
   - Record incident PAR
   - Typical values: 1000-1500 µmol m⁻² s⁻¹

2. **Below canopy dark reference** (Sample 2)
   - Place probe below canopy with shade cap
   - Record diffuse light
   - Typical values: 50-80 µmol m⁻² s⁻¹

3. **Below canopy measurement** (Sample 3)
   - Place probe below canopy without shade cap
   - Record transmitted PAR (direct + diffuse)
   - Typical values: 100-500 µmol m⁻² s⁻¹ (highly variable)

### 3. Key Parameters
| Parameter | Description | Typical Range |
|-----------|-------------|---------------|
| PAR | Average PAR across 64 sensors | 100-1500 µmol m⁻² s⁻¹ |
| Spread | Standard deviation / mean | 0.02-1.5 |
| Total | Total incident light | 1200-1500 µmol m⁻² s⁻¹ |
| Diffuse | Diffuse light component | 230-250 µmol m⁻² s⁻¹ |

## Data Interpretation

### Spread Values
- **Low spread (< 0.1)**: Uniform light environment (above canopy)
- **Medium spread (0.1-0.5)**: Moderate heterogeneity
- **High spread (> 0.5)**: Highly heterogeneous (sunfleck patterns)

### Sunfleck Analysis
- High spread values indicate sunfleck patterns
- Sunflecks are patches of direct sunlight penetrating the canopy
- Important for understory plant photosynthesis

## Related Topics
- [[LAI-Measurement]]
- [[SunScan-Data-Analysis]]
- [[Canopy-Structure]]
