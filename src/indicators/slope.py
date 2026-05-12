import numpy as np
import geopandas as gpd
import rasterstats
from pathlib import Path


def compute_slope_susceptibility(
    gdf: gpd.GeoDataFrame,
    dem_path: Path,
    config: dict,
) -> gpd.GeoDataFrame:
    """
    Proxy slope susceptibility from within-county DEM standard deviation.
    High terrain variability → high runoff susceptibility → higher flood risk.
    Normalized to [0, 1]. Falls back to zeros when DEM is absent.
    """
    zs_cfg = config["zonal_stats"]
    col = config["columns"]["slope"]

    if not dem_path.exists():
        print(f"  [warn] DEM not found ({dem_path.name}) — using zeros.")
        gdf = gdf.copy()
        gdf[col] = 0.0
        return gdf

    stats = rasterstats.zonal_stats(
        gdf, str(dem_path), stats=["std"], nodata=zs_cfg["nodata"], all_touched=True
    )

    gdf = gdf.copy()
    raw = np.array([s["std"] if s["std"] is not None else 0.0 for s in stats])
    r_min, r_max = raw.min(), raw.max()
    if r_max > r_min:
        gdf[col] = (raw - r_min) / (r_max - r_min)
    else:
        gdf[col] = 0.0

    print(f"  [OK] Slope susceptibility computed for {len(gdf)} counties.")
    return gdf
