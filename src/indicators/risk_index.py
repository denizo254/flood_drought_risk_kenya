import numpy as np
import pandas as pd
import geopandas as gpd


def _minmax_normalize(series: pd.Series) -> pd.Series:
    s_min, s_max = series.min(), series.max()
    if s_max == s_min:
        return pd.Series(np.zeros(len(series)), index=series.index, dtype=float)
    return (series - s_min) / (s_max - s_min)


def compute_composite_risk_index(gdf: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Composite Risk Index (0–1):

        Risk = w1 * norm(Rainfall_Z)
             + w2 * norm(-NDVI_Dev)   ← inverted: negative deviation = drought = high risk
             + w3 * PopDensity_norm
             + w4 * Slope_norm

    All components normalised to [0, 1] via min-max before weighting.
    Weights are read from config['risk_weights'] and must sum to 1.0.
    """
    cols = config["columns"]
    w = config["risk_weights"]
    thresholds = config["risk_categories"]
    gdf = gdf.copy()

    # Validate weights
    total_weight = sum(w.values())
    if abs(total_weight - 1.0) > 1e-6:
        raise ValueError(f"risk_weights must sum to 1.0, got {total_weight:.4f}")

    rain_norm = _minmax_normalize(gdf[cols["rainfall_zscore"]].fillna(0))
    ndvi_norm = _minmax_normalize(-gdf[cols["ndvi_deviation"]].fillna(0))
    pop_norm = gdf[cols["pop_density"]].fillna(0).clip(0, 1)
    slope_norm = gdf[cols["slope"]].fillna(0).clip(0, 1)

    gdf[cols["risk_index"]] = (
        w["rainfall_zscore"] * rain_norm
        + w["ndvi_deviation"] * ndvi_norm
        + w["pop_density"] * pop_norm
        + w["slope"] * slope_norm
    )

    risk = gdf[cols["risk_index"]]
    gdf[cols["risk_category"]] = pd.cut(
        risk,
        bins=[-0.001, thresholds["medium"], thresholds["high"], 1.001],
        labels=["Low", "Medium", "High"],
    )

    n_high = (gdf[cols["risk_category"]] == "High").sum()
    n_med = (gdf[cols["risk_category"]] == "Medium").sum()
    n_low = (gdf[cols["risk_category"]] == "Low").sum()

    print(f"  [OK] Composite Risk Index computed for {len(gdf)} counties.")
    print(f"    Score range : [{risk.min():.3f}, {risk.max():.3f}]  mean={risk.mean():.3f}")
    print(f"    Categories  : High={n_high}  Medium={n_med}  Low={n_low}")
    return gdf
