"""
export_graph.py

Serializes the graph built by transit.build_graph() into a single compact
MessagePack file the React frontend can fetch once and then run its own
Dijkstra against, for arbitrary (start stop, start time, budget) queries
with no server round-trip per query.

Design choices, and why:

  - stop_id / route_id strings are replaced with integer array indices
    everywhere in the graph. Repeating "ttc_14276" as a key thousands of
    times is enormously wasteful next to a plain int.

  - graph is an array indexed by stop index (not an object keyed by
    stop_id string) -- same reasoning, and it's a direct fit for how the
    JS side will use it (data.graph[stopIdx]).

  - each stop's edges are split into "transit" and "transfer" lists
    instead of a flat list with a repeated "type" field on every edge.

  - the "departures" convenience array (parallel to "trips", used for
    bisect) is NOT included in the export -- it's cheap for the browser
    to derive once at load time (`edge.trips.map(t => t[0])`), and
    dropping it roughly halves the size of every transit edge's payload.

  - route_id inside each trip tuple becomes a route *index* into the
    routes array, not a repeated string.

  - serialized with MessagePack instead of JSON: every integer is
    encoded in binary (1-9 bytes depending on magnitude) instead of as
    ASCII digit characters, and arrays/maps don't carry comma/brace/
    bracket punctuation. For a payload that's almost entirely large
    arrays of numbers, this is a meaningful size win on top of gzip,
    not instead of it -- still worth serving compressed.

Run directly:
    python export_graph.py
writes to:
    data/graph.msgpack
"""

from pathlib import Path
import shutil

import msgpack

try:
    from .transit import BASE_DIR, load_data, build_graph, build_route_lookup, build_route_shapes
except ImportError:
    from transit import BASE_DIR, load_data, build_graph, build_route_lookup, build_route_shapes


def export_graph(graph, stops, route_names, output_path=None, route_data=None, route_shapes=None):
    """Write the compact browser-facing schema, indexed by stop and route."""
    frontend_output = BASE_DIR.parent / "frontend" / "jet-lag-frontend" / "public" / "graph.msgpack"
    output_path = Path(output_path) if output_path else frontend_output

    # --- assign a stable integer index to every stop -------------------
    stop_ids = list(stops["stop_id"])
    stop_index = {stop_id: i for i, stop_id in enumerate(stop_ids)}

    # --- assign a stable integer index to every route -------------------
    route_ids = list(route_names.keys())
    route_index = {route_id: i for i, route_id in enumerate(route_ids)}
    route_rows = {}
    if route_data is not None:
        route_rows = {str(row["route_id"]): row for row in route_data.to_dict("records")}

    def route_color(route_id, column, fallback):
        raw = str(route_rows.get(route_id, {}).get(column, "")).strip().lstrip("#")
        if len(raw) == 6 and all(char in "0123456789abcdefABCDEF" for char in raw):
            return f"#{raw}"
        return fallback

    # --- build the stops array (parent_station resolved to an index) ---
    stops_out = []
    for row in stops.to_dict("records"):
        parent = row.get("parent_station")
        parent_idx = None
        if parent is not None and str(parent).strip() and parent in stop_index:
            parent_idx = stop_index[parent]

        stops_out.append({
            "id": row["stop_id"],
            "name": row["stop_name"],
            "lat": float(row["stop_lat"]),
            "lon": float(row["stop_lon"]),
            "parent": parent_idx,
            "agency": row.get("agency", ""),
            "locationType": int(row["location_type"]) if str(row.get("location_type", "")).isdigit() else 0,
            "modes": row.get("modes", []),
        })

    # --- build the routes array -----------------------------------------
    routes_out = [
        {
            "id": route_id,
            "name": route_names[route_id],
            "color": route_color(route_id, "route_color", "#27847b"),
            "textColor": route_color(route_id, "route_text_color", "#ffffff"),
        }
        for route_id in route_ids
    ]
    route_shapes = route_shapes or {}

    # --- build the graph array (index-aligned with stops_out) ----------
    graph_out = [
        {"transit": [], "transfer": []}
        for _ in stop_ids
    ]

    skipped = 0

    for stop_id, edges in graph.items():

        from_idx = stop_index.get(stop_id)
        if from_idx is None:
            # a graph node with no matching stops.txt row -- shouldn't
            # normally happen, but don't let one bad row crash the export
            skipped += len(edges)
            continue

        for edge in edges:

            to_idx = stop_index.get(edge["to"])
            if to_idx is None:
                skipped += 1
                continue

            if edge["type"] == "transit":
                trips_out = [
                    [dep, arr, route_index.get(route_id, -1)]
                    for dep, arr, route_id in edge["trips"]
                ]
                graph_out[from_idx]["transit"].append({
                    "to": to_idx,
                    "trips": trips_out,
                })

            elif edge["type"] == "transfer":
                graph_out[from_idx]["transfer"].append({
                    "to": to_idx,
                    "duration": edge["duration"],
                })

    if skipped:
        print(f"  warning: skipped {skipped} edge(s) with no matching stop row")

    # Prefer GTFS track shapes, split at station-to-station boundaries so the
    # map can keep the route geometry smooth while dimming unreachable links.
    stop_coords = [(float(row["stop_lat"]), float(row["stop_lon"])) for row in stops.to_dict("records")]
    for route_idx, route_id in enumerate(route_ids):
        shaped_segments = []
        for segment in route_shapes.get(route_id, []):
            from_idx, to_idx = stop_index.get(segment["from"]), stop_index.get(segment["to"])
            if from_idx is None or to_idx is None:
                continue
            shaped_segments.append({
                "from": from_idx,
                "to": to_idx,
                "positions": segment["points"],
            })
        if not shaped_segments:
            for from_idx, node in enumerate(graph_out):
                for edge in node["transit"]:
                    if any(trip[2] == route_idx for trip in edge["trips"]):
                        shaped_segments.append({
                            "from": from_idx,
                            "to": edge["to"],
                            "positions": [stop_coords[from_idx], stop_coords[edge["to"]]],
                        })
        routes_out[route_idx]["segments"] = shaped_segments

    payload = {
        "version": 2,
        "city": "Toronto",
        "timeZone": "America/Toronto",
        "timeUnit": "seconds-after-midnight",
        "stationFilter": ["TTC subway", "TTC Line 5/6 LRT", "GO rail"],
        "scheduleNote": "Trips from all service days are included; filter by service calendar when adding date-aware queries.",
        "stops": stops_out,
        "routes": routes_out,
        "graph": graph_out,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "wb") as f:
        # use_bin_type=True keeps str/bytes distinct per the msgpack spec,
        # which is what every JS msgpack decoder (e.g. @msgpack/msgpack)
        # expects for strings to come back as strings, not byte arrays
        f.write(msgpack.packb(payload, use_bin_type=True))

    # Keep the processor copy in sync when writing to the default frontend path.
    processor_output = BASE_DIR / "data" / "graph.msgpack"
    if output_path == frontend_output:
        processor_output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(output_path, processor_output)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"Wrote {output_path} ({size_mb:.1f} MB, {len(stops_out)} stops, {len(routes_out)} routes)")
    if output_path == frontend_output:
        print(f"Synced processor graph to {processor_output}")


if __name__ == "__main__":
    stop_times, trips, stops, routes = load_data()
    graph = build_graph(stop_times, trips, stops)
    route_names = build_route_lookup(routes)
    route_shapes = build_route_shapes(stop_times, trips, stops)
    print("Graph ready")

    export_graph(graph, stops, route_names, route_data=routes, route_shapes=route_shapes)
