"""Refresh TTC and GO GTFS, build the combined graph, and export MessagePack."""

from __future__ import annotations

import argparse
import json

try:  # support both `python main.py` and `python -m processor.main`
    from .download import download_city
    from .city_config import BASE_DIR, frontend_cities, get_city, load_cities
    from .export_graph import export_graph
    from .transit import build_graph, build_route_lookup, build_route_shapes, load_data
except ImportError:
    from download import download_city
    from city_config import BASE_DIR, frontend_cities, get_city, load_cities
    from export_graph import export_graph
    from transit import build_graph, build_route_lookup, build_route_shapes, load_data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="build from the already extracted feeds configured for the city",
    )
    parser.add_argument("--output", help="optional output path for the MessagePack graph")
    parser.add_argument("--city", default="toronto", help="city id from processor/cities.json")
    parser.add_argument("--list-cities", action="store_true", help="list configured city ids and exit")
    args = parser.parse_args()

    cities = load_cities()
    if args.list_cities:
        for city_id in cities:
            print(city_id)
        return
    city = get_city(args.city)
    agencies = {feed_id: BASE_DIR.parent / feed.get("directory", f"data/{args.city}/{feed_id}") for feed_id, feed in city["feeds"].items()}
    if not args.skip_download:
        download_city(args.city)
    stop_times, trips, stops, routes = load_data(agencies, city["route_rules"])
    graph = build_graph(stop_times, trips, stops, agencies)
    route_names = build_route_lookup(routes)
    cities[args.city]["line_count"] = len(route_names)
    route_shapes = build_route_shapes(stop_times, trips, stops, agencies)
    export_graph(graph, stops, route_names, output_path=args.output, route_data=routes, route_shapes=route_shapes, city_id=args.city, city_config=city)
    manifest_path = BASE_DIR.parent / "frontend" / "jet-lag-frontend" / "public" / "cities.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(frontend_cities(cities), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote city manifest {manifest_path}")


if __name__ == "__main__":
    main()
