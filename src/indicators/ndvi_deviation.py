import numpy as np
import geopandas as gpd
import rasterstats
from pathlib import Path


def compute_ndvi_deviation(
    gdf: gpd.GeoDataFrame,
    ndvi_path: Path,
    baseline_path: Path,
    config: dict,
) -> gpd.GeoDataFrame:
    """
    NDVI deviation = current NDVI − long-term baseline NDVI.
    Negative values indicate vegetation stress (drought signal).
    Falls back to placeholder zeros when rasters are absent.
    """
    zs_cfg = config["zonal_stats"]
    col = config["columns"]["ndvi_deviation"]

    if not ndvi_path.exists() or not baseline_path.exists():
        missing = [p for p in (ndvi_path, baseline_path) if not p.exists()]
        print(f"  [warn] NDVI rasters not found ({[p.name for p in missing]}) — using zeros.")
        gdf = gdf.copy()
        gdf[col] = 0.0
        return gdf

    current_stats = rasterstats.zonal_stats(
        gdf, str(ndvi_path), stats=["mean"], nodata=zs_cfg["nodata"], all_touched=True
    )
    baseline_stats = rasterstats.zonal_stats(
        gdf, str(baseline_path), stats=["mean"], nodata=zs_cfg["nodata"], all_touched=True
    )

    gdf = gdf.copy()
    current = np.array([s["mean"] if s["mean"] is not None else 0.0 for s in current_stats])
    baseline = np.array([s["mean"] if s["mean"] is not None else 0.0 for s in baseline_stats])
    gdf[col] = current - baseline

    print(f"  [OK] NDVI deviation computed for {len(gdf)} counties.")
    return gdf
