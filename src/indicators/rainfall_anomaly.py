import numpy as np
import pandas as pd
import geopandas as gpd
import rasterstats
from pathlib import Path


def _zonal_stats_df(gdf: gpd.GeoDataFrame, raster_path: Path, stats: list, nodata: float) -> pd.DataFrame:
    results = rasterstats.zonal_stats(
        gdf,
        str(raster_path),
        stats=stats,
        nodata=nodata,
        all_touched=True,
    )
    return pd.DataFrame(results)


def compute_rainfall_anomaly(
    gdf: gpd.GeoDataFrame,
    raster_path: Path,
    config: dict,
) -> gpd.GeoDataFrame:
    cols = config["columns"]
    zs_cfg = config["zonal_stats"]

    print("  Computing zonal statistics for rainfall...")
    stats_df = _zonal_stats_df(gdf, raster_path, zs_cfg["stats"], zs_cfg["nodata"])

    gdf = gdf.copy()
    gdf[cols["avg_rainfall"]] = stats_df["mean"]
    gdf["rainfall_max_mm"] = stats_df["max"]
    gdf["rainfall_std_mm"] = stats_df["std"]

    county_mean = gdf[cols["avg_rainfall"]].mean()
    county_std = gdf[cols["avg_rainfall"]].std()

    if county_std == 0 or pd.isna(county_std):
        gdf[cols["rainfall_zscore"]] = 0.0
    else:
        gdf[cols["rainfall_zscore"]] = (
            (gdf[cols["avg_rainfall"]] - county_mean) / county_std
        )

    print(
        f"  [OK] Rainfall anomaly computed for {len(gdf)} counties "
        f"(mean={county_mean:.1f} mm, std={county_std:.1f} mm)."
    )
    return gdf
