import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject
from pathlib import Path


def align_to_reference(
    source_path: Path,
    reference_path: Path,
    output_path: Path,
) -> Path:
    """Reproject and resample source raster to match the reference raster's grid."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(reference_path) as ref:
        ref_crs = ref.crs
        ref_transform = ref.transform
        ref_width = ref.width
        ref_height = ref.height

    with rasterio.open(source_path) as src:
        meta = src.meta.copy()
        meta.update({
            "crs": ref_crs,
            "transform": ref_transform,
            "width": ref_width,
            "height": ref_height,
            "compress": "lzw",
        })

        with rasterio.open(output_path, "w", **meta) as dst:
            for band in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, band),
                    destination=rasterio.band(dst, band),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=ref_transform,
                    dst_crs=ref_crs,
                    resampling=Resampling.bilinear,
                )

    print(f"  [OK] Aligned raster saved: {output_path.name}")
    return output_path
