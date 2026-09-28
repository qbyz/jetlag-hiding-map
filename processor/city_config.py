"""Read and validate city/feed definitions used by the GTFS pipeline."""

from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CITIES_PATH = BASE_DIR / "cities.json"


def load_cities(path: Path = CITIES_PATH) -> dict:
    with Path(path).open(encoding="utf-8") as source:
        cities = json.load(source)
    if not isinstance(cities, dict) or not cities:
        raise ValueError(f"No cities configured in {path}")
    return cities


def get_city(city_id: str, path: Path = CITIES_PATH) -> dict:
    cities = load_cities(path)
    if city_id not in cities:
        raise ValueError(f"Unknown city {city_id!r}; configured cities: {', '.join(cities)}")
    city = cities[city_id]
    if not city.get("feeds"):
        raise ValueError(f"City {city_id!r} has no GTFS feeds")
    if not city.get("route_rules"):
        raise ValueError(f"City {city_id!r} has no route_rules")
    return city


def frontend_cities(cities: dict, graph_dir: Path | None = None) -> list[dict]:
    """Return the compact city-picker manifest; graphs are exported separately."""
    if graph_dir is None:
        graph_dir = BASE_DIR.parent / "frontend" / "jet-lag-frontend" / "public" / "cities"
    try:
        import msgpack
    except ImportError:  # pragma: no cover - msgpack is a required pipeline dependency
        msgpack = None
    result = []
    for city_id, config in cities.items():
        line_count = config.get("line_count", 0)
        graph_file = Path(graph_dir) / f"{city_id}.msgpack"
        if not graph_file.exists():
            continue
        if msgpack is not None and graph_file.exists():
            try:
                with graph_file.open("rb") as graph:
                    line_count = len(msgpack.unpackb(graph.read(), raw=False).get("routes", []))
            except (ValueError, msgpack.UnpackException):
                pass
        result.append({
            "id": city_id,
            "name": config["name"],
            "region": config.get("region", ""),
            "operators": config.get("operators", ", ".join(config["feeds"])),
            "networkType": config.get("networkType", "bus" if config.get("route_rules") and all(rule.get("mode") == "bus" for rule in config["route_rules"]) else "rail"),
            "timeZone": config.get("timeZone", "UTC"),
            "graphPath": f"/cities/{city_id}.msgpack",
            "lines": line_count,
        })
    return result
