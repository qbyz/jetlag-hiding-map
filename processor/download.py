"""Download and extract the latest TTC and GO static GTFS feeds."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import zipfile

import requests

try:
    from .config import GO_GTFS_URL, TORONTO_CKAN_PACKAGE_SHOW_URL, TTC_DATASET_ID
except ImportError:
    from config import GO_GTFS_URL, TORONTO_CKAN_PACKAGE_SHOW_URL, TTC_DATASET_ID


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
AGENCIES = {
    "ttc": {"dataset": TTC_DATASET_ID, "api": TORONTO_CKAN_PACKAGE_SHOW_URL},
    "go": {"url": GO_GTFS_URL},
}


def _latest_ttc_url(session: requests.Session) -> str:
    response = session.get(
        AGENCIES["ttc"]["api"],
        params={"id": AGENCIES["ttc"]["dataset"]},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError("Toronto Open Data did not return the TTC dataset metadata")

    resources = payload["result"].get("resources", [])
    candidates = [
        resource for resource in resources
        if resource.get("url")
        and (
            "zip" in str(resource.get("format", "")).lower()
            or str(resource.get("name", "")).lower().endswith(".zip")
            or ".zip" in str(resource.get("url", "")).lower()
        )
    ]
    if not candidates:
        raise RuntimeError("No ZIP resource was found in the TTC dataset metadata")

    # Prefer the most recently modified resource when the dataset retains old
    # snapshots. Resource order is a fallback for feeds without timestamps.
    def publication_key(resource):
        return resource.get("last_modified") or resource.get("created") or ""

    return max(candidates, key=publication_key)["url"]


def _safe_extract(zip_path: Path, target_dir: Path) -> None:
    """Extract an archive while rejecting paths that escape the target folder."""
    target_root = target_dir.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            destination = (target_dir / member.filename).resolve()
            if destination != target_root and target_root not in destination.parents:
                raise RuntimeError(f"Unsafe path in GTFS archive: {member.filename}")
        archive.extractall(target_dir)


def download_agency(agency: str, *, session: requests.Session | None = None) -> Path:
    if agency not in AGENCIES:
        raise ValueError(f"Unknown GTFS agency: {agency}")
    session = session or requests.Session()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    url = _latest_ttc_url(session) if agency == "ttc" else AGENCIES[agency]["url"]
    destination = DATA_DIR / f"{agency}.zip"
    print(f"Downloading {agency.upper()} GTFS...")
    with session.get(url, stream=True, timeout=(30, 180)) as response:
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(dir=DATA_DIR, delete=False) as tmp:
            temp_path = Path(tmp.name)
            try:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        tmp.write(chunk)
            except Exception:
                temp_path.unlink(missing_ok=True)
                raise
    temp_path.replace(destination)

    # Validate before replacing the current extracted feed.
    with zipfile.ZipFile(destination) as archive:
        names = {Path(name).name for name in archive.namelist()}
        if not {"stops.txt", "routes.txt", "trips.txt", "stop_times.txt"}.issubset(names):
            destination.unlink(missing_ok=True)
            raise RuntimeError(f"Downloaded {agency.upper()} archive is missing required GTFS files")

    extract_to = DATA_DIR / agency
    staging = Path(tempfile.mkdtemp(prefix=f".{agency}-", dir=DATA_DIR))
    try:
        _safe_extract(destination, staging)
        if not (staging / "stops.txt").exists():
            # Some feeds wrap the GTFS files in a single containing directory.
            nested = next((p for p in staging.iterdir() if p.is_dir() and (p / "stops.txt").exists()), None)
            if nested is None:
                raise RuntimeError(f"Could not find stops.txt in {agency.upper()} archive")
            for child in nested.iterdir():
                target = staging / child.name
                if child.is_dir():
                    shutil.move(str(child), target)
                else:
                    os.replace(child, target)
            nested.rmdir()

        backup = DATA_DIR / f".{agency}-previous"
        if backup.exists():
            shutil.rmtree(backup)
        if extract_to.exists():
            extract_to.replace(backup)
        staging.replace(extract_to)
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    print(f"Extracted {agency.upper()} GTFS to {extract_to}")
    return extract_to


def main() -> None:
    with requests.Session() as session:
        session.headers["User-Agent"] = "jetlag-hiding-map/0.1 (GTFS graph builder)"
        for agency in AGENCIES:
            download_agency(agency, session=session)


if __name__ == "__main__":
    main()
