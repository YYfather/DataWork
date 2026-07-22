---
title: Python 科学计算
description: NumPy、Pandas、Matplotlib 与科学数据分析的常用工作流。
category: 学习文档
order: 50
lang: zh
---
# Python 科学计算

## 概述

Python 是一种广泛应用于科学计算、数据分析和可视化的通用编程语言。本页涵盖科学工作所需的基本工具和库。

## 核心库

### 1. NumPy
- **用途**：基于数组的数值计算
- **主要特性**：快速数组运算、线性代数、随机数
- **安装**：`pip install numpy`

```python
import numpy as np

# 创建数组
arr = np.array([1, 2, 3, 4, 5])
matrix = np.array([[1, 2], [3, 4]])

# 基本运算
mean = np.mean(arr)
std = np.std(arr)
```

### 2. Pandas
- **用途**：数据处理与分析
- **主要特性**：DataFrame、数据清洗、文件 I/O
- **安装**：`pip install pandas`

```python
import pandas as pd

# 读取 CSV
df = pd.read_csv('data.csv')

# 基本操作
df.head()
df.describe()
df['column'].mean()
```

### 3. Matplotlib
- **用途**：数据可视化
- **主要特性**：图表、图形、自定义样式
- **安装**：`pip install matplotlib`

```python
import matplotlib.pyplot as plt

# 基本绘图
plt.plot(x, y)
plt.xlabel('X')
plt.ylabel('Y')
plt.title('我的图表')
plt.show()
```

### 4. SciPy
- **用途**：科学计算
- **主要特性**：优化、插值、统计分析
- **安装**：`pip install scipy`

```python
from scipy import stats

# 统计检验
t_stat, p_value = stats.ttest_ind(group1, group2)
```

## 数据分析工作流

### 1. 数据加载
```python
import pandas as pd

# 读取不同文件格式
df_csv = pd.read_csv('data.csv')
df_excel = pd.read_excel('data.xlsx')
df_json = pd.read_json('data.json')
```

### 2. 数据清洗
```python
# 处理缺失值
df.dropna()  # 删除含 NaN 的行
df.fillna(0)  # 用 0 填充 NaN

# 删除重复值
df.drop_duplicates()

# 数据类型转换
df['column'] = pd.to_numeric(df['column'])
```

### 3. 数据转换
```python
# 筛选数据
filtered = df[df['column'] > 100]

# 分组聚合
grouped = df.groupby('category').mean()

# 应用函数
df['new_col'] = df['col'].apply(lambda x: x * 2)
```

### 4. 数据可视化
```python
import matplotlib.pyplot as plt

# 折线图
plt.plot(df['x'], df['y'])
plt.show()

# 直方图
plt.hist(df['values'], bins=20)
plt.show()

# 散点图
plt.scatter(df['x'], df['y'])
plt.show()
```

## 科学应用

### 1. SunScan 数据分析
```python
import pandas as pd

# 加载 PAR 数据
par_df = pd.read_csv('sunscan_par_64ch.csv')

# 计算统计量
par_df['mean_par'] = par_df[['Ch1', 'Ch2', ...]].mean(axis=1)
par_df['std_par'] = par_df[['Ch1', 'Ch2', ...]].std(axis=1)
```

### 2. LAI 计算
```python
import numpy as np

# Beer-Lambert 定律
def calculate_lai(transmitted, incident, k=0.5):
    return -np.log(transmitted / incident) / k

# 应用于数据框
df['LAI'] = df.apply(lambda row: calculate_lai(
    row['Transmitted'], row['Incident']
), axis=1)
```

### 3. 统计分析
```python
from scipy import stats

# T 检验
t_stat, p_value = stats.ttest_ind(group1, group2)

# 相关性分析
corr, p_value = stats.pearsonr(x, y)

# 线性回归
slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
```

## 最佳实践

### 代码组织
- 使用函数实现可复用代码
- 为函数添加文档字符串
- 对复杂逻辑添加注释

### 错误处理
```python
try:
    result = risky_operation()
except Exception as e:
    print(f"错误：{e}")
    # 适当处理错误
```

### 性能优化
- 使用向量化运算（NumPy/Pandas）
- 尽可能避免循环
- 对性能瓶颈进行性能分析

## 相关主题
- [[SunScan-Data-Analysis]]
- [[Git-Basics]]
