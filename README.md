# 🔭 skyview-cli

从命令行或 Jupyter notebook 快速查看天文巡天图像。不用打开浏览器，不用手动输坐标。

## 安装

```bash
cd ~/Documents/code/skyview
pip install -e .
```

## 使用场景

### 场景1：Jupyter notebook 里查看图像

在 ipynb 里处理数据，发现异常源，直接看图：

```python
import skyview

# 单个天体
skyview.show("NGC 788")
skyview.show(ra=30.28, dec=-23.50, survey="sdss", fov=2.0)

# 批量查看 — 传入列表
skyview.batch(["NGC 788", "M31", "NGC 1275", "Coma Cluster"])

# 从你的数据直接来
import pandas as pd
df = pd.read_csv("my_sources.csv")
anomalies = df[df["flag"] == "bad"]
skyview.batch(list(zip(anomalies["ra"], anomalies["dec"])), fov=0.5, cols=4)

# 从文件批量加载
skyview.batch_from_file("catalog.fits", ra_col="RA", dec_col="DEC", name_col="NAME")
```

### 场景2：命令行快速查看

```bash
# 按名称
skyview show NGC 788
skyview show M31 -s sdss -f 3.0

# 按坐标
skyview show 30.28 -23.50

# 保存图像
skyview show NGC 788 -o ngc788.jpg

# 批量
skyview batch "NGC 788" "M31" "NGC 1275"
skyview batch -f catalog.csv --ra-col RA --dec-col DEC -o gallery.png

# 解析天体名
skyview resolve "NGC 788"
```

### 场景3：批量保存不显示

```python
# 保存网格图到文件
skyview.batch(targets, save="anomalies_gallery.png", cols=6)

# 单独下载图像
img = skyview.fetch("NGC 788", fov=2.0)
img.save("ngc788.jpg")
```

## 支持的巡天

| 巡天 | 说明 |
|------|------|
| `ls-dr10` | Legacy Survey DR10 (默认) |
| `ls-dr9` | Legacy Survey DR9 |
| `sdss` | SDSS |
| `des-dr1` | DES DR1 |
| `unwise-neo7` | unWISE (WISE红外) |
| `galex` | GALEX (紫外) |
| `panstarrs` | PanSTARRS |

```bash
skyview surveys  # 列出所有可用巡天
```

## 参数说明

- `fov` — 视场大小，单位角分（默认 1'）
- `survey` — 巡天名称
- `size` — 图像像素大小（一般用 fov 就够了）
- `cols` — 批量网格的列数

## 开发

```bash
pip install -e ".[jupyter]"
```
