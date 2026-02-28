# 🔭 skyview-cli

**[中文](#中文) | [English](#english)**

---

<a id="中文"></a>

## 中文

从命令行或 Jupyter Notebook 快速查看天文巡天图像。
不用打开浏览器，不用手动输坐标，支持批量查看和系统图像查看器浏览。

### 安装

```bash
pip install git+https://github.com/tdccccc/skyview-cli.git
```

本地开发：

```bash
cd ~/Documents/code/skyview
pip install -e .
```

### 快速上手

#### Jupyter Notebook（推荐场景）

在 notebook 里处理数据时，发现异常源想看图：

```python
import skyview

# ---- 单个天体 ----
skyview.show("NGC 788")
skyview.show(ra=30.28, dec=-23.50, survey="sdss", fov=2.0)

# ---- 批量查看 ----

# 方式1: 天体名列表
skyview.batch(["NGC 788", "M31", "NGC 1275", "Coma Cluster"])

# 方式2: 两个数组/Series（最常用！）
skyview.batch(df["ra"], df["dec"], fov=5)

# 方式3: tuple 包裹两个数组
skyview.batch((df["ra"], df["dec"]), survey="ls-dr9", fov=5)

# 方式4: 2D numpy 数组 / DataFrame .values
skyview.batch(df[["ra", "dec"]].values, fov=3)

# 方式5: (ra, dec) 元组列表
skyview.batch(list(zip(df["ra"], df["dec"])), fov=5, cols=4)

# 方式6: 从 CSV/FITS 文件加载
skyview.batch_from_file("catalog.fits", ra_col="RA", dec_col="DEC", name_col="NAME")

# 方式7: pandas Series / numpy array
skyview.batch(pd.Series(["NGC 788", "M31"]))
```

#### 保存图像

```python
# 保存网格到文件（不弹窗）
skyview.batch(targets, save="gallery.png", cols=6)

# 下载单张原始图像
img = skyview.fetch("NGC 788", fov=2.0)
img.save("ngc788.jpg")
```

#### 名称解析

```python
ra, dec = skyview.resolve("NGC 788")
print(f"RA={ra:.4f}, Dec={dec:.4f}")
```

#### 命令行

```bash
# 查看单个天体（自动调用系统图像查看器）
skyview show NGC 788
skyview show 30.28 -23.50
skyview show "10:00:00 +02:12:00"   # 时角格式
skyview show NGC 788 -s sdss -f 3.0
skyview show NGC 788 -o ngc788.jpg  # 保存到文件
skyview show NGC 788 --viewer feh   # 指定查看器

# 批量查看（系统查看器打开，左右键切换）
skyview batch "NGC 788" "M31" "NGC 1275"
skyview batch "NGC 788" "M31" -f 5
skyview batch "NGC 788" "M31" --grid         # 强制 matplotlib 网格视图
skyview batch -F catalog.csv --ra-col RA --dec-col DEC

# 浏览模式（下载图像 + 系统查看器）
skyview browse "NGC 788" "M31" "NGC 1275" -f 5

# 名称解析
skyview resolve "NGC 788"

# 列出可用巡天
skyview surveys

# 缓存管理
skyview cache-info
skyview cache-clear
```

### 支持的巡天

| 名称 | 波段 | 覆盖 | 优先级 | 说明 |
|------|------|------|--------|------|
| `ls-dr10` | grz | Dec > -70° | 100 | **默认**，Legacy Survey DR10 |
| `ls-dr9` | grz | Dec > -70° | 90 | Legacy Survey DR9 |
| `panstarrs` | grizy | Dec > -30° | 80 | Pan-STARRS1 |
| `sdss` | ugriz | 部分天区 | 70 | SDSS |
| `des-dr1` | grizY | -65° < Dec < 5° | 60 | DES DR1（南天） |
| `unwise-neo7` | W1W2 | 全天 | 20 | unWISE 红外 |
| `galex` | FUV/NUV | 全天 | 10 | GALEX 紫外 |

**自动 fallback**：如果指定巡天返回空白图（坐标超出覆盖范围），会自动按优先级尝试下一个巡天。

### 关键参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `fov` | 视场大小（角分） | `1.0` |
| `survey` | 巡天名称 | `ls-dr10` |
| `size` | 图像像素大小 | 自动（由 fov 计算） |
| `cols` | 批量网格列数 | `5` |
| `workers` | 并发下载线程数 | `8` |
| `save` | 保存路径（不设则显示） | — |

### 坐标输入格式

`show()` 和 CLI 的 `target` 参数支持：

- **十进制度数**：`"150.0 2.2"` 或 `150.0, 2.2`
- **时角/度分秒**：`"10:00:00 +02:12:00"`
- **天体名称**：`"NGC 788"`, `"M31"`, `"Coma Cluster"`

### 依赖

- Python >= 3.9
- click, requests, matplotlib, astropy, Pillow, numpy

---

<a id="english"></a>

## English

Quickly browse astronomical survey images from the command line or Jupyter Notebook.
No browser needed, no manual coordinate entry — supports batch viewing and system image viewer browsing.

### Installation

```bash
pip install git+https://github.com/tdccccc/skyview-cli.git
```

Local development:

```bash
cd ~/Documents/code/skyview
pip install -e .
```

### Quick Start

#### Jupyter Notebook (Recommended)

Spot an interesting source while analyzing data? View it instantly:

```python
import skyview

# ---- Single target ----
skyview.show("NGC 788")
skyview.show(ra=30.28, dec=-23.50, survey="sdss", fov=2.0)

# ---- Batch viewing ----

# Method 1: list of object names
skyview.batch(["NGC 788", "M31", "NGC 1275", "Coma Cluster"])

# Method 2: two arrays/Series (most common!)
skyview.batch(df["ra"], df["dec"], fov=5)

# Method 3: tuple of two arrays
skyview.batch((df["ra"], df["dec"]), survey="ls-dr9", fov=5)

# Method 4: 2D numpy array / DataFrame .values
skyview.batch(df[["ra", "dec"]].values, fov=3)

# Method 5: list of (ra, dec) tuples
skyview.batch(list(zip(df["ra"], df["dec"])), fov=5, cols=4)

# Method 6: load from CSV/FITS file
skyview.batch_from_file("catalog.fits", ra_col="RA", dec_col="DEC", name_col="NAME")

# Method 7: pandas Series / numpy array
skyview.batch(pd.Series(["NGC 788", "M31"]))
```

#### Saving Images

```python
# Save grid to file (no popup)
skyview.batch(targets, save="gallery.png", cols=6)

# Download a single raw image
img = skyview.fetch("NGC 788", fov=2.0)
img.save("ngc788.jpg")
```

#### Name Resolution

```python
ra, dec = skyview.resolve("NGC 788")
print(f"RA={ra:.4f}, Dec={dec:.4f}")
```

#### Command Line

```bash
# View a single target (opens system image viewer)
skyview show NGC 788
skyview show 30.28 -23.50
skyview show "10:00:00 +02:12:00"   # sexagesimal format
skyview show NGC 788 -s sdss -f 3.0
skyview show NGC 788 -o ngc788.jpg  # save to file
skyview show NGC 788 --viewer feh   # specify viewer

# Batch view (system viewer, arrow keys to navigate)
skyview batch "NGC 788" "M31" "NGC 1275"
skyview batch "NGC 788" "M31" -f 5
skyview batch "NGC 788" "M31" --grid         # force matplotlib grid
skyview batch -F catalog.csv --ra-col RA --dec-col DEC

# Browse mode (download images + system viewer)
skyview browse "NGC 788" "M31" "NGC 1275" -f 5

# Name resolution
skyview resolve "NGC 788"

# List available surveys
skyview surveys

# Cache management
skyview cache-info
skyview cache-clear
```

### Supported Surveys

| Name | Bands | Coverage | Priority | Notes |
|------|-------|----------|----------|-------|
| `ls-dr10` | grz | Dec > -70° | 100 | **Default**, Legacy Survey DR10 |
| `ls-dr9` | grz | Dec > -70° | 90 | Legacy Survey DR9 |
| `panstarrs` | grizy | Dec > -30° | 80 | Pan-STARRS1 |
| `sdss` | ugriz | Partial | 70 | SDSS |
| `des-dr1` | grizY | -65° < Dec < 5° | 60 | DES DR1 (southern sky) |
| `unwise-neo7` | W1W2 | All-sky | 20 | unWISE infrared |
| `galex` | FUV/NUV | All-sky | 10 | GALEX ultraviolet |

**Auto fallback**: If a survey returns a blank image (coordinates outside coverage), it automatically tries the next survey by priority.

### Key Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `fov` | Field of view (arcmin) | `1.0` |
| `survey` | Survey name | `ls-dr10` |
| `size` | Image pixel size | Auto (from fov) |
| `cols` | Batch grid columns | `5` |
| `workers` | Concurrent download threads | `8` |
| `save` | Save path (display if not set) | — |

### Coordinate Formats

The `show()` function and CLI `target` argument accept:

- **Decimal degrees**: `"150.0 2.2"` or `150.0, 2.2`
- **Sexagesimal**: `"10:00:00 +02:12:00"`
- **Object names**: `"NGC 788"`, `"M31"`, `"Coma Cluster"`

### Dependencies

- Python >= 3.9
- click, requests, matplotlib, astropy, Pillow, numpy

## License

MIT
