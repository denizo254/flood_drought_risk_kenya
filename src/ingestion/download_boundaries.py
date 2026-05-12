import geopandas as gpd
from pathlib import Path

from src.ingestion.checksum import save_checksum, verify_checksum

_GEOBOUNDARIES_URL = (
    "https://github.com/wmgeolab/geoBoundaries/raw/main/"
    "releaseData/gbOpen/KEN/ADM1/geoBoundaries-KEN-ADM1.geojson"
)


def ingest_boundaries(config: dict) -> Path:
    raw_dir = Path(config["paths"]["raw_data"])
    checksum_dir = Path(config["paths"]["checksums"])
    dest = raw_dir / config["data"]["counties_file"]

    if dest.exists() and verify_checksum(dest, checksum_dir):
        print(f"  [skip] {dest.name} already verified.")
        return dest

    if dest.exists():
        save_checksum(dest, checksum_dir)
        print(f"  [OK] County boundaries registered: {dest.name}")
        return dest

    print(f"  Downloading Kenya county boundaries from geoBoundaries...")
    raw_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.read_file(_GEOBOUNDARIES_URL)
    gdf.to_file(dest, driver="GeoJSON")
    save_checksum(dest, checksum_dir)
    print(f"  [OK] County boundaries saved: {dest.name}")
    return dest
