"""Download WorldPop Kenya population density (2020, 1 km resolution)."""
import requests
from pathlib import Path
from tqdm import tqdm

from src.ingestion.checksum import save_checksum, verify_checksum

_WORLDPOP_URL = (
    "https://data.worldpop.org/GIS/Population/"
    "Global_2000_2020/2020/KEN/ken_ppp_2020.tif"
)


def ingest_population(config: dict) -> Path:
    raw_dir = Path(config["paths"]["raw_data"])
    checksum_dir = Path(config["paths"]["checksums"])
    dest = raw_dir / config["data"]["population_file"]

    if dest.exists() and verify_checksum(dest, checksum_dir):
        print(f"  [skip] {dest.name} already verified.")
        return dest

    url = config["ingestion"].get("worldpop_url", _WORLDPOP_URL)
    print(f"  Downloading Kenya population raster (WorldPop 2020, 1 km)...")
    raw_dir.mkdir(parents=True, exist_ok=True)

    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        with open(dest, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc=dest.name
        ) as bar:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                bar.update(len(chunk))

    save_checksum(dest, checksum_dir)
    print(f"  [OK] Population raster saved: {dest.name}")
    return dest
