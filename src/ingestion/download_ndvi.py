"""Download MODIS MOD13A3 monthly NDVI for Kenya via NASA earthaccess.

Requires a free NASA Earthdata account: https://urs.earthdata.nasa.gov/users/new
Set credentials via env vars EARTHDATA_USERNAME and EARTHDATA_PASSWORD,
or run interactively and the library will prompt you.
"""
import os
import tempfile
import numpy as np
import rasterio
from rasterio.merge import merge as rio_merge
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.transform import array_bounds
from pathlib import Path
import earthaccess

from src.ingestion.checksum import save_checksum, verify_checksum

_SCALE_FACTOR = 0.0001
_FILL_VALUE = -28672
_NODATA = -9999.0
_NDVI_LAYER = "1 km monthly NDVI"


# ── Auth ───────────────────────────────────────────────────────────────────────

def _auth() -> None:
    if os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD"):
        earthaccess.login(strategy="environment")
    else:
        raise EnvironmentError(
            "NASA Earthdata credentials not found.\n"
            "  Free account: https://urs.earthdata.nasa.gov/users/new\n"
            "  Then: set EARTHDATA_USERNAME=<user> and EARTHDATA_PASSWORD=<pass>"
        )


# ── HDF4 helpers ───────────────────────────────────────────────────────────────

def _ndvi_subdataset(hdf_path: Path) -> str:
    """Return the rasterio-compatible GDAL subdataset path for the NDVI layer."""
    try:
        with rasterio.open(str(hdf_path)) as ds:
            for sub in ds.subdatasets:
                if _NDVI_LAYER in sub:
                    return sub
    except Exception as exc:
        raise RuntimeError(
            f"Cannot open {hdf_path.name} as HDF4. "
            "Ensure your GDAL build includes the HDF4 driver "
            "(rasterio PyPI wheels on Windows include it by default)."
        ) from exc
    raise ValueError(f"No '{_NDVI_LAYER}' subdataset found in {hdf_path.name}")


def _hdf_tiles_to_geotiff(hdf_paths: list, output_path: Path) -> None:
    """Mosaic MODIS HDF4 tiles → reproject to EPSG:4326 → save GeoTIFF."""
    open_srcs = [rasterio.open(_ndvi_subdataset(p)) for p in hdf_paths]

    try:
        if len(open_srcs) > 1:
            mosaic, transform = rio_merge(open_srcs)
            raw = mosaic[0]
            src_crs = open_srcs[0].crs
            h, w = raw.shape
        else:
            raw = open_srcs[0].read(1)
            transform = open_srcs[0].transform
            src_crs = open_srcs[0].crs
            h, w = raw.shape
    finally:
        for src in open_srcs:
            src.close()

    # Apply MODIS scale factor; replace fill with nodata sentinel
    ndvi = np.where(
        raw == _FILL_VALUE,
        _NODATA,
        raw.astype(np.float32) * _SCALE_FACTOR,
    )

    # Reproject sinusoidal → EPSG:4326
    dst_crs = "EPSG:4326"
    bounds = array_bounds(h, w, transform)  # (west, south, east, north)
    dst_transform, dst_w, dst_h = calculate_default_transform(
        src_crs, dst_crs, w, h, *bounds
    )

    reprojected = np.full((dst_h, dst_w), _NODATA, dtype=np.float32)
    reproject(
        source=ndvi,
        destination=reprojected,
        src_transform=transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=Resampling.bilinear,
        src_nodata=_NODATA,
        dst_nodata=_NODATA,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **{
        "driver": "GTiff", "dtype": "float32",
        "crs": dst_crs, "transform": dst_transform,
        "width": dst_w, "height": dst_h,
        "count": 1, "nodata": _NODATA, "compress": "lzw",
    }) as dst:
        dst.write(reprojected, 1)


# ── Download helpers ───────────────────────────────────────────────────────────

def _download_month(year: int, month: int, save_dir: Path, bbox: list) -> list:
    """Download MOD13A3 granules (HDF4) for one year/month over the bbox."""
    results = earthaccess.search_data(
        short_name="MOD13A3",
        version="061",
        temporal=(f"{year}-{month:02d}-01", f"{year}-{month:02d}-28"),
        bounding_box=(bbox[0], bbox[1], bbox[2], bbox[3]),  # W, S, E, N
    )
    if not results:
        raise FileNotFoundError(f"No MOD13A3 granules for {year}-{month:02d}.")
    out_dir = save_dir / f"{year}_{month:02d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    files = earthaccess.download(results, str(out_dir))
    return [Path(f) for f in files]


# ── Public entry point ─────────────────────────────────────────────────────────

def ingest_ndvi(config: dict) -> tuple:
    """
    Download and process MODIS MOD13A3 NDVI.
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

    _auth()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # Current month
        if not (current_path.exists() and verify_checksum(current_path, checksum_dir)):
            print(f"  Downloading current NDVI ({year}-{month:02d})...")
            hdfs = _download_month(year, month, tmp_dir, bbox)
            _hdf_tiles_to_geotiff(hdfs, current_path)
            save_checksum(current_path, checksum_dir)
            print(f"  [OK] Current NDVI saved: {current_path.name}")

        # Baseline — mean over baseline_years for the same calendar month
        if not (baseline_path.exists() and verify_checksum(baseline_path, checksum_dir)):
            print(f"  Computing baseline NDVI ({baseline_years}, month={month:02d})...")
            year_arrays = []
            ref_profile = None

            for by in baseline_years:
                try:
                    hdfs = _download_month(by, month, tmp_dir, bbox)
                    tiff = tmp_dir / f"ndvi_{by}.tif"
                    _hdf_tiles_to_geotiff(hdfs, tiff)
                    with rasterio.open(tiff) as src:
                        arr = src.read(1).astype(np.float32)
                        arr = np.where(arr == _NODATA, np.nan, arr)
                        year_arrays.append(arr)
                        if ref_profile is None:
                            ref_profile = src.profile.copy()
                except Exception as exc:
                    print(f"  [warn] NDVI {by} skipped: {exc}")

            if not year_arrays:
                raise RuntimeError("Could not download any baseline NDVI years.")

            baseline_mean = np.nanmean(np.stack(year_arrays), axis=0)
            baseline_mean = np.where(
                np.isnan(baseline_mean), _NODATA, baseline_mean
            ).astype(np.float32)

            ref_profile.update({"nodata": _NODATA, "compress": "lzw"})
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(baseline_path, "w", **ref_profile) as dst:
                dst.write(baseline_mean, 1)
            save_checksum(baseline_path, checksum_dir)
            print(
                f"  [OK] Baseline NDVI saved: {baseline_path.name} "
                f"(n={len(year_arrays)} years)"
            )

    return current_path, baseline_path
