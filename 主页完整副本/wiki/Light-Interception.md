# Light Interception

## Overview

Light interception is the process by which plant canopies absorb, reflect, and transmit solar radiation. It is a key driver of photosynthesis and productivity.

## Beer-Lambert Law

### Basic Formula
```
I = I₀ × e^(-K × LAI)
```

Where:
- **I**: Light intensity below canopy
- **I₀**: Incident light above canopy
- **K**: Extinction coefficient
- **LAI**: Leaf area index

### Extinction Coefficient (K)
- **Definition**: Fraction of light intercepted per unit LAI
- **Range**: 0.3-0.8 (depending on canopy structure)
- **Factors**:
  - Leaf angle distribution
  - Solar zenith angle
  - Leaf optical properties

## Light Components

### 1. Direct Light (Beam)
- **Definition**: Direct sunlight from the sun
- **Characteristics**: High intensity, directional
- **Measurement**: Beam fraction sensor (BFS)

### 2. Diffuse Light (Scattered)
- **Definition**: Light scattered by atmosphere
- **Characteristics**: Lower intensity, omnidirectional
- **Sources**: Clouds, aerosols, sky

### 3. Sunflecks
- **Definition**: Patches of direct light penetrating canopy gaps
- **Duration**: Seconds to minutes
- **Importance**: Major contributor to understory photosynthesis
- **Measurement**: High spread values in SunScan data

## Measurement with SunScan

### Protocol
1. **Above canopy reference** (Sample 1)
   - Measure incident PAR
   - Record beam fraction
   - Calculate diffuse component

2. **Below canopy measurement** (Sample 3)
   - Measure transmitted PAR
   - Record spatial heterogeneity
   - Identify sunfleck patterns

3. **Calculate light interception**
   ```
   Interception = (Incident - Transmitted) / Incident × 100%
   ```

### Data Interpretation
| Parameter | Low Value | High Value |
|-----------|-----------|------------|
| PAR | Low light environment | High light environment |
| Spread | Uniform light | Heterogeneous (sunflecks) |
| Beam Fraction | Diffuse dominated | Direct dominated |

## Applications

### Crop Production
- Optimize planting density
- Predict yield potential
- Guide canopy management

### Forest Ecology
- Understand understory dynamics
- Species coexistence
- Carbon cycling

### Climate Science
- Energy balance
- Evapotranspiration
- Albedo effects

## Related Topics
- [[PAR-Measurement]]
- [[LAI-Measurement]]
- [[Canopy-Structure]]
