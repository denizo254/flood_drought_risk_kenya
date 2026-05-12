"""Download MODIS MOD13A1 NDVI for Kenya via Microsoft Planetary Computer.

Uses Cloud-Optimized GeoTIFFs — no HDF4, no NASA auth required.
MOD13A1 = 500 m, 16-day composite. Monthly NDVI is computed as the
mean of all 16-day composites that fall within the target month.
"""
import numpy as np
import rasterio
from rasterio.merge import merge as rio_merge
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.transform import array_bounds
from collections import defaultdict
from pathlib import Path
import pystac_client
import planetary_computer

from src.ingestion.checksum import save_checksum, verify_checksum

_PC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
_COLLECTION = "modis-13A1-061"
_NDVI_ASSET = "500m_16_days_NDVI"
_SCALE = 0.0001
_FILL = -28672
_NODATA = -9999.0


def _catalog() -> pystac_client.Client:
    return pystac_client.Client.open(_PC_URL, modifier=planetary_computer.sign_inplace)


def _month_ndvi_array(year: int, month: int, bbox: list, cat) -> tuple:
    """
    Search MOD13A1 items for a month, mosaic tiles per composite date,
    then return the pixel-wise mean NDVI across all composites.
    Returns (ndvi_array, src_crs, src_transform, h, w).
    """
    items = cat.search(
        collections=[_COLLECTION],
        bbox=bbox,
        datetime=f"{year}-{month:02d}-01/{year}-{month:02d}-31",
    ).item_collection()

    if not items:
        raise FileNotFoundError(f"No MOD13A1 items found for {year}-{month:02d}.")

    # Group tiles by composite date (some items carry a range; fall back to start)
    by_date = defaultdict(list)
    for item in items:
        dt = item.datetime or item.common_metadata.start_datetime
        by_date[dt.strftime("%Y-%m-%d")].append(item)

    composite_arrays, ref_crs, ref_transform, ref_h, ref_w = [], None, None, None, None

    for date, date_items in by_date.items():
        signed = [planetary_computer.sign(it) for it in date_items]
        srcs = [rasterio.open(it.assets[_NDVI_ASSET].href) for it in signed]
        try:
            if len(srcs) > 1:
                mosaic, transform = rio_merge(srcs)
                raw = mosaic[0]
                crs = srcs[0].crs
            else:
                raw = srcs[0].read(1)
                transform = srcs[0].transform
                crs = srcs[0].crs
        finally:
            for s in srcs:
                s.close()

        if ref_crs is None:
            ref_crs, ref_transform = crs, transform
            ref_h, ref_w = raw.shape

        ndvi = np.where(raw == _FILL, np.nan, raw.astype(np.float32) * _SCALE)
        composite_arrays.append(ndvi)

    mean = np.nanmean(np.stack(composite_arrays), axis=0)
    mean = np.where(np.isnan(mean), _NODATA, mean).astype(np.float32)
    return mean, ref_crs, ref_transform, ref_h, ref_w


def _save_geotiff(array: np.ndarray, src_crs, src_transform, h: int, w: int, output_path: Path) -> None:
    """Reproject to EPSG:4326 and write GeoTIFF atomically."""
    dst_crs = "EPSG:4326"
    bounds = array_bounds(h, w, src_transform)
    dst_transform, dst_w, dst_h = calculate_default_transform(src_crs, dst_crs, w, h, *bounds)

    reprojected = np.full((dst_h, dst_w), _NODATA, dtype=np.float32)
    reproject(
        source=array, destination=reprojected,
        src_transform=src_transform, src_crs=src_crs,
        dst_transform=dst_transform, dst_crs=dst_crs,
        resampling=Resampling.bilinear,
        src_nodata=_NODATA, dst_nodata=_NODATA,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(".tmp.tif")
    try:
        with rasterio.open(tmp_path, "w", **{
            "driver": "GTiff", "dtype": "float32",
            "crs": dst_crs, "transform": dst_transform,
            "width": dst_w, "height": dst_h,
            "count": 1, "nodata": _NODATA, "compress": "lzw",
        }) as dst:
            dst.write(reprojected, 1)
        tmp_path.replace(output_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def ingest_ndvi(config: dict) -> tuple:
    """
    Download current + baseline NDVI from Planetary Computer (no auth needed).
    Returns (current_ndvi_path, baseline_ndvi_path).
    """
    raw_dir = Path(config["paths"]["raw_data"])
    checksum_dir = Path(config["paths"]["checksums"])
    current_path = raw_dir / config["data"]["ndvi_file"]
    baseline_path = raw_dir / config["data"]["ndvi_baseline_file"]
    bbox = config["ingestion"]["kenya_bbox"]
    year = config["ingestion"]["year"]
    month = config["ingestion"]["month"]
    baseline_years = config["ingestion"]["ndvi_baseline_years"]

    if (
        current_path.exists() and verify_checksum(current_path, checksum_dir)
        and baseline_path.exists() and verify_checksum(baseline_path, checksum_dir)
    ):
        print("  [skip] NDVI files already verified.")
        return current_path, baseline_path

    # Remove any corrupt remnants from a previous failed write.
    for p in (current_path, baseline_path):
        if p.exists() and not verify_checksum(p, checksum_dir):
            print(f"  [warn] Removing corrupt/unverified file: {p.name}")
            p.unlink()

    cat = _catalog()

    # Current month — fall back to previous year if PC hasn't ingested it yet.
    if not (current_path.exists() and verify_checksum(current_path, checksum_dir)):
        actual_year = year
        try:
            print(f"  Downloading current NDVI ({year}-{month:02d}) from Planetary Computer...")
            arr, crs, transform, h, w = _month_ndvi_array(year, month, bbox, cat)
        except FileNotFoundError:
            actual_year = year - 1
            print(f"  [warn] {year}-{month:02d} not yet on Planetary Computer; using {actual_year}-{month:02d} as proxy.")
            arr, crs, transform, h, w = _month_ndvi_array(actual_year, month, bbox, cat)
        _save_geotiff(arr, crs, transform, h, w, current_path)
        save_checksum(current_path, checksum_dir)
        print(f"  [OK] Current NDVI saved: {current_path.name} (source year: {actual_year})")

    # Baseline: mean of same calendar month across baseline_years
    if not (baseline_path.exists() and verify_checksum(baseline_path, checksum_dir)):
        print(f"  Computing baseline NDVI ({baseline_years}, month={month:02d})...")
        year_arrays, ref_crs, ref_transform, ref_h, ref_w = [], None, None, None, None

        for by in baseline_years:
            try:
                arr, crs, transform, h, w = _month_ndvi_array(by, month, bbox, cat)
                masked = np.where(arr == _NODATA, np.nan, arr)
                year_arrays.append(masked)
                if ref_crs is None:
                    ref_crs, ref_transform, ref_h, ref_w = crs, transform, h, w
                print(f"    {by} done.")
            except Exception as exc:
                print(f"  [warn] NDVI {by} skipped: {exc}")

        if not year_arrays:
            raise RuntimeError("No baseline NDVI years could be downloaded.")

        baseline = np.nanmean(np.stack(year_arrays), axis=0)
        baseline = np.where(np.isnan(baseline), _NODATA, baseline).astype(np.float32)
        _save_geotiff(baseline, ref_crs, ref_transform, ref_h, ref_w, baseline_path)
        save_checksum(baseline_path, checksum_dir)
        print(f"  [OK] Baseline NDVI saved: {baseline_path.name} (n={len(year_arrays)} years)")

    return current_path, baseline_path
