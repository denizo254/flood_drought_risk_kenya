import gzip
import shutil
import requests
from pathlib import Path
from tqdm import tqdm

from src.ingestion.checksum import save_checksum, verify_checksum


def _download_file(url: str, dest: Path, timeout: int, chunk_size: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        with open(dest, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc=dest.name
        ) as bar:
            for chunk in r.iter_content(chunk_size=chunk_size):
                f.write(chunk)
                bar.update(len(chunk))


def _decompress_gz(src: Path, dest: Path) -> None:
    with gzip.open(src, "rb") as f_in, open(dest, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)


def ingest_rainfall(config: dict) -> Path:
    raw_dir = Path(config["paths"]["raw_data"])
    checksum_dir = Path(config["paths"]["checksums"])
    compressed_path = raw_dir / config["data"]["rainfall_compressed"]
    extracted_path = raw_dir / config["data"]["rainfall_raw"]
    ingestion_cfg = config["ingestion"]

    if extracted_path.exists() and verify_checksum(extracted_path, checksum_dir):
        print(f"  [skip] {extracted_path.name} already verified.")
        return extracted_path

    if not compressed_path.exists():
        year = ingestion_cfg["year"]
        month = str(ingestion_cfg["month"]).zfill(2)
        url = f"{ingestion_cfg['chirps_base_url']}/chirps-v2.0.{year}.{month}.tif.gz"
        print(f"  Downloading: {url}")
        _download_file(
            url, compressed_path,
            timeout=ingestion_cfg["timeout_seconds"],
            chunk_size=ingestion_cfg["chunk_size"]
        )

    if not extracted_path.exists():
        print(f"  Decompressing {compressed_path.name}...")
        _decompress_gz(compressed_path, extracted_path)

    save_checksum(extracted_path, checksum_dir)
    print(f"  [OK] Rainfall raster ready: {extracted_path.name}")
    return extracted_path
