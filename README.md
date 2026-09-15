# 永春县农业种植选址 MVP

这是一个以可交互地图为核心的本地 Demo。用户选择作物、输入所需面积并调整偏好权重后，系统对候选土地执行硬筛选和软排序。

## 本地启动

```bash
source .venv/bin/activate
streamlit run app.py
```

默认读取 `data/demo/candidates.geojson` 中的演示候选地。获取并处理真实遥感数据后，将结果保存为 `data/processed/yongchun_mvp.gpkg`，应用会优先读取真实数据。

完成道路、人口等空间指标计算后，结果保存为 `data/processed/yongchun_ranked.gpkg`，应用会优先读取它。

## 免费部署（Streamlit Community Cloud）

本仓库可直接部署到 Streamlit Community Cloud：

1. 将仓库推送到 GitHub。
2. 在 [share.streamlit.io](https://share.streamlit.io/) 创建应用并选择该仓库。
3. Branch 选择 `main`，Main file path 填写 `app.py`。
4. Advanced settings 中选择 Python 3.12，然后点击 Deploy。

部署环境会从根目录的 `uv.lock` 和 `pyproject.toml` 安装锁定依赖；应用所需的演示数据已包含在仓库中，不需要配置密钥或外部数据库。

## 测试

```bash
source .venv/bin/activate
pytest
```

## 遥感候选地生成

先从公开 STAC 目录下载并裁剪同一套年度10米土地覆盖数据：

```bash
python scripts/fetch_lulc.py \
  --boundary data/raw/yongchun_boundary.geojson \
  --years 2017 2022 2023
```

再将历史耕地栅格、两个近年土地覆盖栅格和保护区矢量转换为候选土地多边形：

```bash
python scripts/build_candidates.py \
  --historical data/interim/lulc/io_lulc_2017_yongchun.tif \
  --recent data/interim/lulc/io_lulc_2022_yongchun.tif data/interim/lulc/io_lulc_2023_yongchun.tif \
  --protected data/raw/protected_areas.geojson \
  --output data/processed/yongchun_mvp.gpkg
```

默认使用 Impact Observatory/Esri 年度土地覆盖 V2：耕地分类码为 `5`，低利用代理类别为裸地 `8` 和 rangeland `11`。默认规则是2017年为耕地，且2022、2023年连续变为代理类别。自然保护区文件暂时可选；未传入时结果会标记为尚未完成保护区筛查。

## 第一版空间指标

```bash
python scripts/extract_osm_features.py \
  --pbf data/raw/fujian-latest.osm.pbf \
  --boundary data/raw/yongchun_boundary.geojson \
  --output data/processed/osm_features.gpkg

python scripts/compute_spatial_metrics.py \
  --candidates data/processed/yongchun_mvp.gpkg \
  --features data/processed/osm_features.gpkg \
  --population data/interim/worldpop_2020_yongchun.tif \
  --output data/processed/yongchun_ranked.gpkg
```

当前成本分包含主干道、高速出入口、居民点、分级回填的土地流转租金、最低工资和水电成本；市场分使用周边人口与公开POI代理；风险分由河流距离和县级极端天气背景构成。政策保留0—3原始等级，再归一化到0—100参与加权。OSM中的市场、冷链和农业企业POI较稀疏，相关字段只作为低完整度代理，不应解释为完整名录。

## 土地流转与政策公开记录

```bash
python scripts/fetch_public_records.py
```

脚本从永春县政府公开网页抓取下洋镇、桃城镇、介福乡土地流转记录和县级种植补贴规则，生成：

- `data/processed/land_transfer_samples.csv`：24条土地租金样本；三镇有样本时用镇级中位数，其余位置用全部样本中位数进行县级回填。
- `data/processed/planting_subsidies.json`：可按作物、规模匹配的政策规则。
- `data/processed/public_data_sources.csv`：数据口径、时间、空间范围和当前用途清单。
- `data/processed/indicator_catalog.csv`：全部soft ranking指标的来源、分辨率、更新时间、接入状态和局限。

县级成本、极端天气代理和政策连续性由下列命令整理：

```bash
python scripts/fetch_climate_risk.py
python scripts/build_county_context.py
```

输出 `county_context.json` 和 `policy_continuity.json`。当前政策连续性由十四五、十五五规划原文人工结构化，未使用额外LLM接口。土地成本样本、补贴资格和最近乡镇中心归属均需要政府复核。
