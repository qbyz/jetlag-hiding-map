"""Refresh TTC and GO GTFS, build the combined graph, and export MessagePack."""

from __future__ import annotations

import argparse

try:  # support both `python main.py` and `python -m processor.main`
    from .download import main as download_feeds
    from .export_graph import export_graph
    from .transit import build_graph, build_route_lookup, build_route_shapes, load_data
except ImportError:
    from download import main as download_feeds
    from export_graph import export_graph
    from transit import build_graph, build_route_lookup, build_route_shapes, load_data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="build from the already extracted feeds in processor/data/",
    )
    parser.add_argument("--output", help="optional output path for the MessagePack graph")
    args = parser.parse_args()

    if not args.skip_download:
        download_feeds()
    stop_times, trips, stops, routes = load_data()
    graph = build_graph(stop_times, trips, stops)
    route_names = build_route_lookup(routes)
    route_shapes = build_route_shapes(stop_times, trips, stops)
    export_graph(graph, stops, route_names, output_path=args.output, route_data=routes, route_shapes=route_shapes)


if __name__ == "__main__":
    main()
