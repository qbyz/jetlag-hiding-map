"""Compatibility entry point for rebuilding the graph from local GTFS files."""

try:
    from .export_graph import export_graph
    from .transit import build_graph, build_route_lookup, load_data
except ImportError:
    from export_graph import export_graph
    from transit import build_graph, build_route_lookup, load_data


def main():
    stop_times, trips, stops, routes = load_data()
    graph = build_graph(stop_times, trips, stops)
    export_graph(graph, stops, build_route_lookup(routes))


if __name__ == "__main__":
    main()
