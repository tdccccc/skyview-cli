# 🔭 skyview-cli

从命令行或 Jupyter notebook 快速查看天文巡天图像。  
不用打开浏览器，不用手动输坐标，支持批量查看。

## 安装

```bash
pip install git+https://github.com/tdccccc/skyview-cli.git
```

本地开发：

```bash
cd ~/Documents/code/skyview
pip install -e .
```

## 快速上手

### Jupyter Notebook（推荐场景）

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

# 方式7: pandas Series / numpy array of names
skyview.batch(pd.Series(["NGC 788", "M31"]))
```

### 保存图像

```python
# 保存网格到文件（不弹窗）
skyview.batch(targets, save="gallery.png", cols=6)

# 下载单张原始图像
img = skyview.fetch("NGC 788", fov=2.0)
img.save("ngc788.jpg")
```

### 名称解析

```python
ra, dec = skyview.resolve("NGC 788")
print(f"RA={ra:.4f}, Dec={dec:.4f}")
```

### 命令行

```bash
# 查看单个天体
skyview show NGC 788
skyview show 30.28 -23.50
skyview show "10:00:00 +02:12:00"   # 时角格式
skyview show NGC 788 -s sdss -f 3.0
skyview show NGC 788 -o ngc788.jpg  # 保存

# 批量查看
skyview batch "NGC 788" "M31" "NGC 1275"
skyview batch -f catalog.csv --ra-col RA --dec-col DEC
skyview batch -f sources.fits -o gallery.png

# 名称解析
skyview resolve "NGC 788"

# 列出可用巡天
skyview surveys
```

## 支持的巡天

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

## 关键参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `fov` | 视场大小（角分） | `1.0` |
| `survey` | 巡天名称 | `ls-dr10` |
| `size` | 图像像素大小 | 自动（由 fov 计算） |
| `cols` | 批量网格列数 | `5` |
| `workers` | 并发下载线程数 | `8` |
| `save` | 保存路径（不设则显示） | — |

## 坐标输入格式

`show()` 和 CLI 的 `target` 参数支持：

- **十进制度数**：`"150.0 2.2"` 或 `150.0, 2.2`
- **时角/度分秒**：`"10:00:00 +02:12:00"`
- **天体名称**：`"NGC 788"`, `"M31"`, `"Coma Cluster"`

## 性能说明

- `show()` 使用全分辨率图像，适合单个天体细看
- `batch()` 自动将缩略图限制在 512px，保证下载速度
- `batch()` 使用 8 线程并发下载，批量查看更快
- 天体名称解析结果会缓存（最多 256 条），避免重复查询

## 依赖

- Python ≥ 3.9
- click, requests, matplotlib, astropy, astroquery, Pillow, numpy

## License

MIT
