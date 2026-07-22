# SunScan Data Analysis

## Overview

This page documents the data processing workflow for SunScan measurements, including PAR (64-channel) and LAI data.

## Data Files

### File 1: PAR 64-Channel Data
- **Format**: Tab-separated text
- **Content**: 64 sensor readings per measurement
- **Columns**: Time, Plot, Sample, PAR, Spread, Total, Diffuse, Ch1-Ch64
- **Rows**: 112 measurements (37 plots × 3 samples)

### File 2: LAI Data
- **Format**: Tab-separated text
- **Content**: LAI calculations with metadata
- **Columns**: Time, Plot, Sample, Transmitted, Spread, Incident, Beam_Frac, Zenith_Angle, LAI
- **Rows**: 457 measurements (38 plots)

## Python Processing Script

### Dependencies
```python
import csv
import re
from pathlib import Path
```

### Parsing Functions

#### PAR Data Parser
```python
def parse_par_file(path: str) -> list[dict]:
    """Parse PAR 64-channel data file."""
    rows = []
    current_title = ""
    current_group = ""
    current_location = ""

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Extract metadata
        if line.startswith("Title") and ":" in line:
            current_title = line.split(":", 1)[1].strip()
        if line.startswith("Location") and ":" in line:
            current_location = line.split(":", 1)[1].strip()
        if re.match(r"Group\s+(\d+)\s*:", line):
            current_group = re.match(r"Group\s+(\d+)\s*:", line).group(1)

        # Parse data lines
        if line.startswith("Time\tPlot\tSample\tPAR\tSpread\tTotal\tDiffuse"):
            i += 1
            while i < len(lines):
                data_line = lines[i].strip()
                if data_line.startswith("Title") or data_line.startswith("Created"):
                    break
                if not data_line:
                    i += 1
                    continue

                parts = data_line.split("\t")
                if len(parts) >= 9:
                    record = {
                        "File": "PAR",
                        "Title": current_title,
                        "Location": current_location,
                        "Group": current_group,
                        "Time": parts[0],
                        "Plot": parts[1],
                        "Sample": parts[2],
                        "PAR": parts[3],
                        "Spread": parts[4],
                        "Total": parts[5],
                        "Diffuse": parts[6],
                    }
                    # Add 64 channel values
                    for ch_idx, val in enumerate(parts[8:72]):
                        record[f"Ch{ch_idx+1}"] = val
                    rows.append(record)
                i += 1
            continue
        i += 1

    return rows
```

#### LAI Data Parser
```python
def parse_lai_file(path: str) -> list[dict]:
    """Parse LAI measurement data file."""
    rows = []
    current_title = ""
    current_group = ""
    current_location = ""

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Extract metadata
        if line.startswith("Title") and ":" in line:
            current_title = line.split(":", 1)[1].strip()
        if line.startswith("Location") and ":" in line:
            current_location = line.split(":", 1)[1].strip()
        if re.match(r"Group\s+(\d+)\s*:", line):
            current_group = re.match(r"Group\s+(\d+)\s*:", line).group(1)

        # Parse data lines
        if line.startswith("Time\tPlot\tSample\tTrans-"):
            i += 1  # Skip header continuation
            i += 1  # Move to first data line
            while i < len(lines):
                data_line = lines[i].strip()
                if not data_line or data_line.startswith("Title"):
                    i += 1
                    continue

                parts = data_line.split("\t")
                if len(parts) >= 8:
                    record = {
                        "File": "LAI",
                        "Title": current_title,
                        "Location": current_location,
                        "Group": current_group,
                        "Time": parts[0],
                        "Plot": parts[1],
                        "Sample": parts[2],
                        "Transmitted": parts[3],
                        "Spread": parts[4],
                        "Incident": parts[5],
                        "Beam_Frac": parts[6],
                        "Zenith_Angle": parts[7],
                        "LAI": parts[8] if len(parts) > 8 else "",
                    }
                    rows.append(record)
                i += 1
            continue
        i += 1

    return rows
```

### CSV Output
```python
def write_csv(rows: list[dict], out_path: str):
    """Write records to CSV file."""
    if not rows:
        print(f"Warning: No data to write to {out_path}")
        return
    fieldnames = list(rows[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[OK] {out_path} — {len(rows)} rows, {len(fieldnames)} columns")
```

## Output Files

### sunscan_par_64ch.csv
- **Rows**: 112
- **Columns**: 75 (File, Title, Location, Group, Time, Plot, Sample, PAR, Spread, Total, Diffuse, Ch1-Ch64)
- **Content**: Raw PAR readings from 64 sensors

### sunscan_lai.csv
- **Rows**: 457
- **Columns**: 18 (File, Title, Location, Latitude, Longitude, Leaf_Angle_Distn, Leaf_Absorption, Group, Time, Plot, Sample, Transmitted, Spread, Incident, Beam_Frac, Zenith_Angle, LAI, Notes)
- **Content**: LAI calculations with metadata

## Data Quality Notes

### Invalid Data Points
- **Negative LAI values**: -8.8, -8.6, -6.9, -8.6 (Incident = 0.2)
- **Action**: Filter out `LAI < 0` in analysis

### Anomalies
- **High spread values** (> 1.0): Sunfleck patterns
- **Low incident light** (< 100): Sensor malfunction
- **Beam fraction = 0.00**: Diffuse light only

## Related Topics
- [[PAR-Measurement]]
- [[LAI-Measurement]]
- [[Canopy-Structure]]
