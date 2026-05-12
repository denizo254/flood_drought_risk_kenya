"""
Single-entry pipeline orchestrator.
Usage: python pipeline.py [--config config.yaml]
"""
import sys
import argparse
import yaml
import geopandas as gpd
from pathlib import Path

from src.ingestion.download_rainfall import ingest_rainfall
from src.ingestion.download_boundaries import ingest_boundaries
from src.ingestion.download_population import ingest_population
from src.ingestion.download_dem import ingest_dem
from src.ingestion.download_ndvi import ingest_ndvi
from src.preprocessing.clip_raster import clip_raster_to_aoi
from src.indicators.rainfall_anomaly import compute_rainfall_anomaly
from src.indicators.ndvi_deviation import compute_ndvi_deviation
from src.indicators.population_density import compute_population_exposure
from src.indicators.slope import compute_slope_susceptibility
from src.indicators.risk_index import compute_composite_risk_index
from src.visualization.risk_map import plot_risk_map, plot_county_ranking


def _try_ingest(fn, config: dict, label: str) -> None:
    """Run an optional ingestion step; warn and continue on auth/missing-key errors."""
    try:
        fn(config)
    except (OSError, EnvironmentError, FileNotFoundError) as exc:
        print(f"  [warn] Skipping {label}: {exc}")


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def run_pipeline(config: dict) -> gpd.GeoDataFrame:
    raw_dir = Path(config["paths"]["raw_data"])
    processed_dir = Path(config["paths"]["processed_data"])
    reports_dir = Path(config["paths"]["reports"])
    reports_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Ingestion ───────────────────────────────────────────────────────────
    print("\n[1/6] Ingesting data...")
    counties_path = ingest_boundaries(config)
    rainfall_raw_path = ingest_rainfall(config)
    ingest_population(config)
    _try_ingest(ingest_dem, config, "DEM (set OPENTOPO_API_KEY to enable)")
    _try_ingest(ingest_ndvi, config, "NDVI (set EARTHDATA_USERNAME/PASSWORD to enable)")

    # ── 2. Preprocessing ───────────────────────────────────────────────────────
    print("\n[2/6] Clipping raster to Kenya boundary...")
    clipped_path = processed_dir / config["data"]["rainfall_clipped"]
    if clipped_path.exists():
        print(f"  [skip] Clipped raster already exists.")
    else:
        clip_raster_to_aoi(
            raster_path=rainfall_raw_path,
            aoi_path=counties_path,
            output_path=clipped_path,
            nodata=config["zonal_stats"]["nodata"],
        )

    # ── 3. Load boundaries ─────────────────────────────────────────────────────
    print("\n[3/6] Loading county boundaries...")
    gdf = gpd.read_file(counties_path)
    if gdf.crs is None:
        gdf = gdf.set_crs(config["project"]["crs"])
    print(f"  [OK] {len(gdf)} counties loaded (CRS: {gdf.crs}).")

    # ── 4. Compute indicators ──────────────────────────────────────────────────
    print("\n[4/6] Computing indicators...")
    gdf = compute_rainfall_anomaly(gdf, clipped_path, config)
    gdf = compute_ndvi_deviation(
        gdf,
        raw_dir / config["data"]["ndvi_file"],
        raw_dir / config["data"]["ndvi_baseline_file"],
        config,
    )
    gdf = compute_population_exposure(gdf, raw_dir / config["data"]["population_file"], config)
    gdf = compute_slope_susceptibility(gdf, raw_dir / config["data"]["dem_file"], config)

    # ── 5. Composite Risk Index ────────────────────────────────────────────────
    print("\n[5/6] Computing Composite Risk Index...")
    gdf = compute_composite_risk_index(gdf, config)

    # ── 6. Export ──────────────────────────────────────────────────────────────
    print("\n[6/6] Exporting results & generating maps...")
    cols = config["columns"]
    report_cols = [
        cols["county_name"],
        cols["avg_rainfall"],
        cols["rainfall_zscore"],
        cols["ndvi_deviation"],
        cols["pop_density"],
        cols["slope"],
        cols["risk_index"],
        cols["risk_category"],
    ]
    report_path = reports_dir / config["data"]["risk_report"]
    gdf[report_cols].to_csv(report_path, index=False)
    print(f"  [OK] Report saved: {report_path}")

    plot_risk_map(gdf, config)
    plot_county_ranking(gdf, config)

    return gdf


def _print_summary(gdf: gpd.GeoDataFrame, config: dict) -> None:
    cols = config["columns"]
    print("\n" + "=" * 55)
    print("  PIPELINE COMPLETE")
    print("=" * 55)
    print(f"\nTop 5 highest-risk counties:\n")
    top5 = gdf.nlargest(5, cols["risk_index"])[
        [cols["county_name"], cols["risk_index"], cols["risk_category"]]
    ]
    print(top5.to_string(index=False))
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flood-Drought Risk Kenya pipeline")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    result = run_pipeline(cfg)
    _print_summary(result, cfg)
