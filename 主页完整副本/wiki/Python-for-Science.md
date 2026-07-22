# Python for Science

## Overview

Python is a versatile programming language widely used in scientific computing, data analysis, and visualization. This page covers essential tools and libraries for scientific work.

## Core Libraries

### 1. NumPy
- **Purpose**: Numerical computing with arrays
- **Key features**: Fast array operations, linear algebra, random numbers
- **Installation**: `pip install numpy`

```python
import numpy as np

# Create arrays
arr = np.array([1, 2, 3, 4, 5])
matrix = np.array([[1, 2], [3, 4]])

# Basic operations
mean = np.mean(arr)
std = np.std(arr)
```

### 2. Pandas
- **Purpose**: Data manipulation and analysis
- **Key features**: DataFrames, data cleaning, file I/O
- **Installation**: `pip install pandas`

```python
import pandas as pd

# Read CSV
df = pd.read_csv('data.csv')

# Basic operations
df.head()
df.describe()
df['column'].mean()
```

### 3. Matplotlib
- **Purpose**: Data visualization
- **Key features**: Plots, charts, customization
- **Installation**: `pip install matplotlib`

```python
import matplotlib.pyplot as plt

# Basic plot
plt.plot(x, y)
plt.xlabel('X')
plt.ylabel('Y')
plt.title('My Plot')
plt.show()
```

### 4. SciPy
- **Purpose**: Scientific computing
- **Key features**: Optimization, interpolation, statistics
- **Installation**: `pip install scipy`

```python
from scipy import stats

# Statistical tests
t_stat, p_value = stats.ttest_ind(group1, group2)
```

## Data Analysis Workflow

### 1. Data Loading
```python
import pandas as pd

# Read different file formats
df_csv = pd.read_csv('data.csv')
df_excel = pd.read_excel('data.xlsx')
df_json = pd.read_json('data.json')
```

### 2. Data Cleaning
```python
# Handle missing values
df.dropna()  # Remove rows with NaN
df.fillna(0)  # Fill NaN with 0

# Remove duplicates
df.drop_duplicates()

# Data type conversion
df['column'] = pd.to_numeric(df['column'])
```

### 3. Data Transformation
```python
# Filter data
filtered = df[df['column'] > 100]

# Group by
grouped = df.groupby('category').mean()

# Apply functions
df['new_col'] = df['col'].apply(lambda x: x * 2)
```

### 4. Data Visualization
```python
import matplotlib.pyplot as plt

# Line plot
plt.plot(df['x'], df['y'])
plt.show()

# Histogram
plt.hist(df['values'], bins=20)
plt.show()

# Scatter plot
plt.scatter(df['x'], df['y'])
plt.show()
```

## Scientific Applications

### 1. SunScan Data Analysis
```python
import pandas as pd

# Load PAR data
par_df = pd.read_csv('sunscan_par_64ch.csv')

# Calculate statistics
par_df['mean_par'] = par_df[['Ch1', 'Ch2', ...]].mean(axis=1)
par_df['std_par'] = par_df[['Ch1', 'Ch2', ...]].std(axis=1)
```

### 2. LAI Calculations
```python
import numpy as np

# Beer-Lambert law
def calculate_lai(transmitted, incident, k=0.5):
    return -np.log(transmitted / incident) / k

# Apply to dataframe
df['LAI'] = df.apply(lambda row: calculate_lai(
    row['Transmitted'], row['Incident']
), axis=1)
```

### 3. Statistical Analysis
```python
from scipy import stats

# T-test
t_stat, p_value = stats.ttest_ind(group1, group2)

# Correlation
corr, p_value = stats.pearsonr(x, y)

# Linear regression
slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
```

## Best Practices

### Code Organization
- Use functions for reusable code
- Add docstrings to functions
- Comment complex logic

### Error Handling
```python
try:
    result = risky_operation()
except Exception as e:
    print(f"Error: {e}")
    # Handle error appropriately
```

### Performance
- Use vectorized operations (NumPy/Pandas)
- Avoid loops when possible
- Profile code for bottlenecks

## Related Topics
- [[SunScan-Data-Analysis]]
- [[Git-Basics]]
