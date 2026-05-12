import rasterio
from rasterio.mask import mask as rio_mask
import geopandas as gpd
from pathlib import Path


def clip_raster_to_aoi(
    raster_path: Path,
    aoi_path: Path,
    output_path: Path,
    nodata: float = -9999,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    aoi = gpd.read_file(aoi_path)
    if aoi.crs is None:
        aoi = aoi.set_crs("EPSG:4326")

    with rasterio.open(raster_path) as src:
        if aoi.crs != src.crs:
            aoi = aoi.to_crs(src.crs)

        shapes = [geom.__geo_interface__ for geom in aoi.geometry if geom is not None]
        clipped, transform = rio_mask(src, shapes, crop=True, nodata=nodata)

        meta = src.meta.copy()
        meta.update({
            "driver": "GTiff",
            "height": clipped.shape[1],
            "width": clipped.shape[2],
            "transform": transform,
            "nodata": nodata,
            "compress": "lzw",
        })

        with rasterio.open(output_path, "w", **meta) as dst:
            dst.write(clipped)

    print(f"  [OK] Clipped raster saved: {output_path.name}")
    return output_path
