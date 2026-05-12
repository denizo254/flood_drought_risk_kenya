import numpy as np
import geopandas as gpd
import rasterstats
from pathlib import Path


def compute_population_exposure(
    gdf: gpd.GeoDataFrame,
    pop_path: Path,
    config: dict,
) -> gpd.GeoDataFrame:
    """
    Compute mean population density per county, normalized to [0, 1].
    Falls back to placeholder zeros when the raster is absent.
    """
    zs_cfg = config["zonal_stats"]
    col = config["columns"]["pop_density"]

    if not pop_path.exists():
        print(f"  [warn] Population raster not found ({pop_path.name}) — using zeros.")
        gdf = gdf.copy()
        gdf[col] = 0.0
        return gdf

    stats = rasterstats.zonal_stats(
        gdf, str(pop_path), stats=["mean"], nodata=zs_cfg["nodata"], all_touched=True
    )

    gdf = gdf.copy()
    raw = np.array([s["mean"] if s["mean"] is not None else 0.0 for s in stats])
    r_min, r_max = raw.min(), raw.max()
    if r_max > r_min:
        gdf[col] = (raw - r_min) / (r_max - r_min)
    else:
        gdf[col] = 0.0

    print(f"  [OK] Population exposure computed for {len(gdf)} counties.")
    return gdf
