"""Download and extract the latest TTC and GO static GTFS feeds."""

from __future__ import annotations

import os
import ssl
from pathlib import Path
import shutil
import tempfile
from urllib.parse import urlparse
import zipfile

import requests
from requests.adapters import HTTPAdapter

try:
    from .city_config import get_city
except ImportError:
    from city_config import get_city


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROJECT_DIR = BASE_DIR.parent


class LegacyTLSAdapter(HTTPAdapter):
    """Keep certificate checks while permitting an explicitly configured TLS level."""

    def __init__(self, security_level: int):
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.set_ciphers(f"DEFAULT@SECLEVEL={security_level}")
        super().__init__()

    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        kwargs["ssl_context"] = self.ssl_context
        return super().init_poolmanager(connections, maxsize, block=block, **kwargs)


def _latest_feed_url(session: requests.Session, metadata_url: str, dataset_id: str) -> str:
    response = session.get(
        metadata_url,
        params={"id": dataset_id},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(f"Dataset metadata was not returned for {dataset_id}")

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
        raise RuntimeError(f"No ZIP resource was found for dataset {dataset_id}")

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


def download_feed(city_id: str, feed_id: str, feed: dict, *, session: requests.Session | None = None) -> Path:
    session = session or requests.Session()
    city_data_dir = DATA_DIR / city_id
    city_data_dir.mkdir(parents=True, exist_ok=True)

    if feed.get("metadata_url"):
        url = _latest_feed_url(session, feed["metadata_url"], feed["dataset_id"])
    else:
        url = feed.get("url")
    if not url:
        raise ValueError(f"Feed {feed_id!r} for {city_id!r} needs url or metadata_url/dataset_id")
    if feed.get("tls_security_level") is not None:
        level = int(feed["tls_security_level"])
        if not 1 <= level <= 5:
            raise ValueError("tls_security_level must be between 1 and 5")
        parsed_url = urlparse(url)
        session.mount(f"{parsed_url.scheme}://{parsed_url.netloc}/", LegacyTLSAdapter(level))
    request_params = {}
    for key, value in feed.get("url_params", {}).items():
        if isinstance(value, dict) and "env" in value:
            env_var = value["env"]
            value = os.environ.get(env_var)
            if not value:
                raise RuntimeError(f"Set {env_var} to download the {feed_id.upper()} feed")
        request_params[key] = value
    destination = city_data_dir / f"{feed_id}.zip"
    print(f"Downloading {city_id} / {feed_id} GTFS...")
    try:
        with session.get(url, params=request_params, stream=True, timeout=(30, 180)) as response:
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(dir=city_data_dir, delete=False) as tmp:
                temp_path = Path(tmp.name)
                try:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            tmp.write(chunk)
                except Exception:
                    temp_path.unlink(missing_ok=True)
                    raise
    except requests.RequestException as exc:
        response = getattr(exc, "response", None)
        status = f" (HTTP {response.status_code})" if response is not None else ""
        kind = type(exc).__name__
        raise RuntimeError(f"Could not download the {feed_id.upper()} feed for {city_id}{status} [{kind}]; check network access and feed authorization.") from None
    temp_path.replace(destination)

    # Validate before replacing the current extracted feed.
    with zipfile.ZipFile(destination) as archive:
        names = {Path(name).name for name in archive.namelist()}
        if not {"stops.txt", "routes.txt", "trips.txt", "stop_times.txt"}.issubset(names):
            destination.unlink(missing_ok=True)
            raise RuntimeError(f"Downloaded {feed_id.upper()} archive is missing required GTFS files")

    extract_to = PROJECT_DIR / feed.get("directory", f"data/{city_id}/{feed_id}")
    extract_to.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{feed_id}-", dir=extract_to.parent))
    try:
        _safe_extract(destination, staging)
        if not (staging / "stops.txt").exists():
            # Some feeds wrap the GTFS files in a single containing directory.
            nested = next((p for p in staging.iterdir() if p.is_dir() and (p / "stops.txt").exists()), None)
            if nested is None:
                raise RuntimeError(f"Could not find stops.txt in {feed_id.upper()} archive")
            for child in nested.iterdir():
                target = staging / child.name
                if child.is_dir():
                    shutil.move(str(child), target)
                else:
                    os.replace(child, target)
            nested.rmdir()

        backup = city_data_dir / f".{feed_id}-previous"
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

    print(f"Extracted {feed_id.upper()} GTFS to {extract_to}")
    return extract_to


def download_city(city_id: str, *, session: requests.Session | None = None) -> None:
    city = get_city(city_id)
    session = session or requests.Session()
    session.headers["User-Agent"] = "transit-isochrone-generator/0.1 (GTFS graph builder)"
    for feed_id, feed in city["feeds"].items():
        download_feed(city_id, feed_id, feed, session=session)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", default="toronto", help="city id from cities.json")
    args = parser.parse_args()
    with requests.Session() as session:
        download_city(args.city, session=session)


if __name__ == "__main__":
    main()
