"""Download SRTM 90 m DEM for Kenya via the OpenTopography REST API.

Free API key required — register at https://portal.opentopography.org/login
Set via env var OPENTOPO_API_KEY or 'opentopo_api_key' in config.yaml.
"""
import os
import requests
from pathlib import Path
from tqdm import tqdm

from src.ingestion.checksum import save_checksum, verify_checksum

_OPENTOPO_ENDPOINT = "https://portal.opentopography.org/API/globaldem"


def ingest_dem(config: dict) -> Path:
    raw_dir = Path(config["paths"]["raw_data"])
    checksum_dir = Path(config["paths"]["checksums"])
    dest = raw_dir / config["data"]["dem_file"]

    if dest.exists() and verify_checksum(dest, checksum_dir):
        print(f"  [skip] {dest.name} already verified.")
        return dest

    bbox = config["ingestion"]["kenya_bbox"]  # [west, south, east, north]
    api_key = (
        os.environ.get("OPENTOPO_API_KEY")
        or config["ingestion"].get("opentopo_api_key", "")
    )

    if not api_key:
        raise EnvironmentError(
            "OpenTopography API key required for DEM download.\n"
            "  1. Register free at https://portal.opentopography.org/login\n"
            "  2. Export OPENTOPO_API_KEY=<your_key>  (or set in config.yaml)"
        )

    params = {
        "demtype": "SRTMGL3",
        "south": bbox[1],
        "north": bbox[3],
        "west": bbox[0],
        "east": bbox[2],
        "outputFormat": "GTiff",
        "API_Key": api_key,
    }

    print("  Downloading SRTM 90 m DEM from OpenTopography...")
    raw_dir.mkdir(parents=True, exist_ok=True)

    with requests.get(_OPENTOPO_ENDPOINT, params=params, stream=True, timeout=300) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        with open(dest, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc=dest.name
        ) as bar:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                bar.update(len(chunk))

    save_checksum(dest, checksum_dir)
    print(f"  [OK] DEM saved: {dest.name}")
    return dest
