---
title: SunScan 数据分析
description: SunScan 测量数据处理流程，覆盖 PAR 64 通道数据与 LAI 数据。
category: 学习文档
order: 60
lang: zh
---
# SunScan 数据分析

## 概述

本页记录了 SunScan 测量的数据处理流程，包括 PAR（64 通道）和 LAI 数据。

## 数据文件

### 文件 1：PAR 64 通道数据
- **格式**：制表符分隔文本
- **内容**：每次测量 64 个传感器读数
- **列**：时间、样地、样品、PAR、Spread、Total、Diffuse、Ch1-Ch64
- **行**：112 次测量（37 个样地 × 3 个样品）

### 文件 2：LAI 数据
- **格式**：制表符分隔文本
- **内容**：带元数据的 LAI 计算
- **列**：时间、样地、样品、Transmitted、Spread、Incident、Beam_Frac、Zenith_Angle、LAI
- **行**：457 次测量（38 个样地）

## Python 处理脚本

### 依赖
```python
import csv
import re
from pathlib import Path
```

### 解析函数

#### PAR 数据解析器
```python
def parse_par_file(path: str) -> list[dict]:
    """解析 PAR 64 通道数据文件。"""
    rows = []
    current_title = ""
    current_group = ""
    current_location = ""

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 提取元数据
        if line.startswith("Title") and ":" in line:
            current_title = line.split(":", 1)[1].strip()
        if line.startswith("Location") and ":" in line:
            current_location = line.split(":", 1)[1].strip()
        if re.match(r"Group\s+(\d+)\s*:", line):
            current_group = re.match(r"Group\s+(\d+)\s*:", line).group(1)

        # 解析数据行
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
                    # 添加 64 个通道值
                    for ch_idx, val in enumerate(parts[8:72]):
                        record[f"Ch{ch_idx+1}"] = val
                    rows.append(record)
                i += 1
            continue
        i += 1

    return rows
```

#### LAI 数据解析器
```python
def parse_lai_file(path: str) -> list[dict]:
    """解析 LAI 测量数据文件。"""
    rows = []
    current_title = ""
    current_group = ""
    current_location = ""

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 提取元数据
        if line.startswith("Title") and ":" in line:
            current_title = line.split(":", 1)[1].strip()
        if line.startswith("Location") and ":" in line:
            current_location = line.split(":", 1)[1].strip()
        if re.match(r"Group\s+(\d+)\s*:", line):
            current_group = re.match(r"Group\s+(\d+)\s*:", line).group(1)

        # 解析数据行
        if line.startswith("Time\tPlot\tSample\tTrans-"):
            i += 1  # 跳过表头延续行
            i += 1  # 移动到第一条数据行
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

### CSV 输出
```python
def write_csv(rows: list[dict], out_path: str):
    """将记录写入 CSV 文件。"""
    if not rows:
        print(f"警告：没有数据可写入 {out_path}")
        return
    fieldnames = list(rows[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[OK] {out_path} — {len(rows)} 行，{len(fieldnames)} 列")
```

## 输出文件

### sunscan_par_64ch.csv
- **行数**：112
- **列数**：75（File、Title、Location、Group、Time、Plot、Sample、PAR、Spread、Total、Diffuse、Ch1-Ch64）
- **内容**：64 个传感器的原始 PAR 读数

### sunscan_lai.csv
- **行数**：457
- **列数**：18（File、Title、Location、Latitude、Longitude、Leaf_Angle_Distn、Leaf_Absorption、Group、Time、Plot、Sample、Transmitted、Spread、Incident、Beam_Frac、Zenith_Angle、LAI、Notes）
- **内容**：带元数据的 LAI 计算结果

## 数据质量说明

### 无效数据点
- **负 LAI 值**：-8.8、-8.6、-6.9、-8.6（Incident = 0.2）
- **处理**：在分析中过滤掉 `LAI < 0` 的数据

### 异常情况
- **高 spread 值**（> 1.0）：光斑模式（Sunfleck patterns）
- **低入射光**（< 100）：传感器故障
- **光束比例 = 0.00**：仅存在散射光

## 相关主题
- [[PAR-Measurement]]
- [[LAI-Measurement]]
- [[Canopy-Structure]]
