import hashlib
import json
from pathlib import Path


def compute_sha256(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def save_checksum(file_path: Path, checksum_dir: Path) -> str:
    checksum_dir.mkdir(parents=True, exist_ok=True)
    checksum = compute_sha256(file_path)
    record = {"file": file_path.name, "sha256": checksum}
    record_path = checksum_dir / f"{file_path.stem}.json"
    record_path.write_text(json.dumps(record, indent=2))
    return checksum


def verify_checksum(file_path: Path, checksum_dir: Path) -> bool:
    record_path = checksum_dir / f"{file_path.stem}.json"
    if not record_path.exists():
        return False
    stored = json.loads(record_path.read_text())["sha256"]
    return stored == compute_sha256(file_path)
