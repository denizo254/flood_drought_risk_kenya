# Flood–Drought Risk Kenya

A production-ready spatial data science pipeline for computing a **Composite Flood–Drought Displacement Risk Index** at Kenya county level, scalable to the IGAD region.

---

## Architecture

```
flood_drought_risk_kenya/
├── src/
│   ├── ingestion/          # Data download & SHA-256 checksum verification
│   │   ├── checksum.py
│   │   ├── download_rainfall.py
│   │   └── download_boundaries.py
│   ├── preprocessing/      # Raster clipping & alignment
│   │   ├── clip_raster.py
│   │   └── align_layers.py
│   ├── indicators/         # Hazard & exposure computations
│   │   ├── rainfall_anomaly.py
│   │   ├── ndvi_deviation.py
│   │   ├── population_density.py
│   │   ├── slope.py
│   │   └── risk_index.py       ← Composite Risk Index
│   └── visualization/
│       └── risk_map.py
├── data/
│   ├── raw/                # Source data (git-ignored, populated by pipeline)
│   ├── processed/          # Clipped rasters (git-ignored)
│   └── checksums/          # SHA-256 manifests (versioned)
├── outputs/
│   ├── maps/               # PNG risk maps
│   └── reports/            # CSV county risk reports
├── config.yaml             # All paths, column names, weights — no hardcoding
├── pipeline.py             # Single-entry orchestrator
└── requirements.txt        # Pinned dependencies
```

---

## Quick Start

```bash
# 1. Clone and create virtual environment
git clone <repo-url>
cd flood_drought_risk_kenya
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 2. Install pinned dependencies
pip install -r requirements.txt

# 3. Place data files in data/raw/
#    Required:
#      kenya_counties.geojson      (auto-downloaded if absent)
#      rainfall_dec_2025.tif.gz    (auto-downloaded from CHIRPS if absent)
#
#    Optional — add for full index (pipeline degrades gracefully without them):
#      ndvi_current.tif            (MODIS MOD13A3 current month)
#      ndvi_baseline.tif           (MODIS long-term mean)
#      population_density.tif      (WorldPop 100 m)
#      srtm_dem.tif                (SRTM 30 m elevation)

# 4. Run the full pipeline
python pipeline.py

# Optional: use a custom config
python pipeline.py --config config.yaml
```

**Outputs written to:**
- `outputs/reports/county_risk_report.csv` — tabular risk scores per county
- `outputs/maps/kenya_risk_map.png` — dual-panel hazard + risk map
- `outputs/maps/county_risk_ranking.png` — top-15 county bar chart

---

## Execution Order

The pipeline runs six sequential stages:

| Stage | Module | Description |
|-------|--------|-------------|
| 1 | `src/ingestion/` | Download & verify source data (with checksum guard) |
| 2 | `src/preprocessing/clip_raster.py` | Clip Africa-wide CHIRPS raster to Kenya extent |
| 3 | *(internal)* | Load county GeoDataFrame, enforce CRS |
| 4 | `src/indicators/` | Compute all four indicator layers |
| 5 | `src/indicators/risk_index.py` | Assemble and categorise Composite Risk Index |
| 6 | `src/visualization/` | Export CSV report + PNG maps |

---

## Risk Index Methodology

The Composite Risk Index is a weighted sum of four normalised indicators:

$$\text{Risk} = w_1 \cdot \hat{Z}_{rain} + w_2 \cdot \hat{D}_{NDVI} + w_3 \cdot \hat{P}_{pop} + w_4 \cdot \hat{S}_{slope}$$

| Component | Symbol | Source | Default Weight | Interpretation |
|-----------|--------|--------|:--------------:|----------------|
| Rainfall Z-Score | $\hat{Z}_{rain}$ | CHIRPS v2.0 (0.05°) | **0.40** | High positive Z → flood signal |
| NDVI Deviation | $\hat{D}_{NDVI}$ | MODIS MOD13A3 (1 km) | **0.30** | Negative deviation → drought/vegetation stress |
| Population Density | $\hat{P}_{pop}$ | WorldPop (100 m) | **0.20** | Higher density → greater human exposure |
| Terrain Variability | $\hat{S}_{slope}$ | SRTM (30 m) | **0.10** | High relief std → runoff susceptibility |

### Normalisation procedure

1. **Rainfall Z-score** — computed cross-sectionally across all 47 counties for the analysis period; measures deviation from the national mean.
2. **NDVI deviation** — **inverted** before normalisation (`-NDVI_dev`), so that negative NDVI anomalies (drought stress) produce high risk scores.
3. **Population density** and **slope** — min-max normalised within-pipeline via `rasterstats` zonal means.
4. All four components are independently scaled to **[0, 1]** via min-max before weighting.
5. Counties are classified into risk tiers: **Low** (< 0.4) · **Medium** (0.4–0.7) · **High** (> 0.7).

Weights and thresholds are fully configurable in `config.yaml` under `risk_weights` and `risk_categories`.

---

## Data Sources

| Dataset | Resolution | Provider |
|---------|-----------|----------|
| CHIRPS Rainfall | 0.05° (~5 km) | Climate Hazards Group, UCSB |
| MODIS NDVI | 1 km monthly | NASA LPDAAC (MOD13A3) |
| Population Density | 100 m | WorldPop |
| SRTM DEM | 30 m | USGS EarthExplorer |
| County Boundaries | Vector (ADM1) | geoBoundaries / KNBS |

---

## Security & Reproducibility

- **SHA-256 checksums** — every downloaded file is verified against a stored manifest in `data/checksums/`. Re-runs skip already-verified files.
- **No hardcoded paths** — all file names and column names live in `config.yaml`.
- **pathlib throughout** — all file I/O uses `pathlib.Path` for cross-OS compatibility.
- **Graceful degradation** — if optional rasters (NDVI, population, DEM) are absent, the pipeline substitutes zeros with a warning and continues.

---

## Policy Relevance

Supports climate risk monitoring, anticipatory humanitarian action, and evidence-based prioritisation of vulnerable regions within Kenya and the IGAD region. The framework aligns with the IGAD Climate Prediction and Applications Centre (ICPAC) Early Warning standards.

---

## Author

**Laono Denis** — Spatial Data Scientist  
Email: marklelaono933@gmail.com
