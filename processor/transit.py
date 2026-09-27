"""Load TTC and GO GTFS feeds and build a time-dependent transit graph."""

from __future__ import annotations

from collections import defaultdict
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
AGENCIES = {"ttc": BASE_DIR / "data" / "ttc", "go": BASE_DIR / "data" / "go"}
WALKING_TRANSFER_RADIUS_METERS = 200
WALKING_SPEED_METERS_PER_SECOND = 1.4


def _read_csv(path: Path, required: list[str], optional: list[str] | None = None) -> pd.DataFrame:
    optional = optional or []
    header = pd.read_csv(path, nrows=0).columns
    missing = set(required) - set(header)
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(sorted(missing))}")
    columns = required + [column for column in optional if column in header]
    return pd.read_csv(path, usecols=columns, dtype=str, keep_default_na=False)


def _load_agency(agency: str, directory: Path):
    stop_times = _read_csv(
        directory / "stop_times.txt",
        ["trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time"],
    )
    trips = _read_csv(directory / "trips.txt", ["trip_id", "route_id"], ["shape_id"])
    stops = _read_csv(
        directory / "stops.txt",
        ["stop_id", "stop_name", "stop_lat", "stop_lon"],
        ["parent_station", "location_type", "wheelchair_boarding"],
    )
    routes = _read_csv(
        directory / "routes.txt",
        ["route_id", "route_type"],
        ["route_short_name", "route_long_name", "route_color", "route_text_color"],
    )

    prefix = f"{agency}_"
    for frame, columns in (
        (stop_times, ["trip_id", "stop_id"]),
        (trips, ["trip_id", "route_id"]),
        (stops, ["stop_id", "parent_station"]),
        (routes, ["route_id"]),
    ):
        for column in columns:
            if column in frame:
                frame[column] = frame[column].map(lambda value: prefix + value if value else "")

    stops["agency"] = agency
    for column in ("stop_lat", "stop_lon"):
        stops[column] = pd.to_numeric(stops[column], errors="coerce")
    stops = stops.dropna(subset=["stop_lat", "stop_lon"])
    return stop_times, trips, stops, routes


def _station_mode(route, route_rules):
    """Apply city route rules; only explicitly included routes enter the graph."""
    route_type = str(route.get("route_type", "")).strip()
    agency = str(route.get("agency", ""))
    long_name = str(route.get("route_long_name", "")).strip().lower()
    short_name = str(route.get("route_short_name", "")).strip().lower()
    name = " ".join(part for part in (short_name, long_name) if part)
    for rule in route_rules:
        if rule.get("feed") != agency or route_type not in {str(value) for value in rule.get("route_types", [])}:
            continue
        prefixes = [str(prefix).lower() for prefix in rule.get("route_name_prefixes", [])]
        if prefixes and not any(long_name.startswith(prefix) or short_name.startswith(prefix) or name.startswith(prefix) for prefix in prefixes):
            continue
        return rule.get("mode", "rail")
    return None


def load_data(agencies=None, route_rules=None):
    agencies = agencies or AGENCIES
    if route_rules is None:
        try:
            from .city_config import get_city
        except ImportError:
            from city_config import get_city
        route_rules = get_city("toronto")["route_rules"]
    loaded = []
    for agency, directory in agencies.items():
        directory = Path(directory)
        if not directory.exists():
            raise FileNotFoundError(f"Missing {agency.upper()} GTFS feed at {directory}; run download.py first")
        print(f"Loading {agency.upper()} GTFS from {directory}")
        loaded.append(_load_agency(agency, directory))
    if not loaded:
        raise FileNotFoundError("No GTFS feeds configured")

    combined = [pd.concat([feed[i] for feed in loaded], ignore_index=True) for i in range(4)]
    stop_times, trips, stops, routes = combined
    # Feed ids may contain underscores (e.g. bc_transit); match the full,
    # longest configured prefix instead of splitting at the first underscore.
    feed_prefixes = sorted(agencies, key=len, reverse=True)
    routes["agency"] = routes["route_id"].map(
        lambda route_id: next((feed for feed in feed_prefixes if str(route_id).startswith(f"{feed}_")), "")
    )
    routes["station_mode"] = routes.apply(lambda route: _station_mode(route, route_rules), axis=1)
    routes = routes[routes["station_mode"].notna()].reset_index(drop=True)
    rail_route_ids = set(routes["route_id"])
    trips = trips[trips["route_id"].isin(rail_route_ids)].reset_index(drop=True)
    rail_trip_ids = set(trips["trip_id"])
    stop_times = stop_times[stop_times["trip_id"].isin(rail_trip_ids)].copy()
    if stop_times.empty:
        raise ValueError("No trips matched the configured route_rules in the selected GTFS feeds")

    trip_modes = trips.set_index("trip_id")["route_id"].map(routes.set_index("route_id")["station_mode"])
    stop_times["station_mode"] = stop_times["trip_id"].map(trip_modes)
    served_stops = set(stop_times["stop_id"])
    stops = stops[stops["stop_id"].isin(served_stops)].copy()
    modes_by_stop = stop_times.groupby("stop_id")["station_mode"].agg(lambda values: sorted(set(values)))
    stops["modes"] = stops["stop_id"].map(modes_by_stop).apply(
        lambda value: value if isinstance(value, list) else []
    )
    # Invalid GTFS times/sequence rows cannot contribute an edge.
    stop_times["stop_sequence"] = pd.to_numeric(stop_times["stop_sequence"], errors="coerce")
    stop_times = stop_times.dropna(subset=["stop_sequence", "arrival_time", "departure_time"])
    stops = stops.drop_duplicates("stop_id", keep="first").reset_index(drop=True)
    routes = routes.drop_duplicates("route_id", keep="first").reset_index(drop=True)
    return stop_times, trips, stops, routes


def time_to_seconds(value: str) -> int:
    """Convert a GTFS time to seconds; hours may exceed 24 per the spec."""
    try:
        hours, minutes, seconds = map(int, str(value).split(":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid GTFS time: {value!r}") from exc
    if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ValueError(f"Invalid GTFS time: {value!r}")
    return hours * 3600 + minutes * 60 + seconds


def distance_meters(lat1, lon1, lat2, lon2) -> float:
    radius = 6_371_000
    p1, p2 = radians(float(lat1)), radians(float(lat2))
    dp = p2 - p1
    dl = radians(float(lon2) - float(lon1))
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * radius * atan2(sqrt(a), sqrt(1 - a))


def build_route_lookup(routes):
    lookup = {}
    for row in routes.to_dict("records"):
        route_id = str(row["route_id"])
        short = str(row.get("route_short_name", "")).strip()
        long = str(row.get("route_long_name", "")).strip()
        if long and long.lower().startswith("line"):
            name = long
        elif long and short and short.isdigit():
            name = f"Line {short} {long}"
        else:
            name = long or short or route_id
        lookup[route_id] = name
    return lookup


def build_route_shapes(stop_times, trips, stops, agencies=None):
    """Return route polylines split at stops, using each GTFS shape pattern."""
    agencies = agencies or AGENCIES
    stop_index = {str(stop_id): index for index, stop_id in enumerate(stops["stop_id"])}
    stop_coords = {
        str(row["stop_id"]): (float(row["stop_lat"]), float(row["stop_lon"]))
        for row in stops.to_dict("records")
    }
    route_segments = defaultdict(list)
    seen = defaultdict(set)

    if "shape_id" not in trips.columns:
        return route_segments

    for agency, directory in agencies.items():
        agency_trips = trips[
            trips["route_id"].astype(str).str.startswith(f"{agency}_")
            & trips["shape_id"].astype(str).ne("")
        ].drop_duplicates(["route_id", "shape_id"])
        if agency_trips.empty:
            continue
        shapes_path = Path(directory) / "shapes.txt"
        if not shapes_path.exists():
            continue
        shape_ids = set(agency_trips["shape_id"].astype(str))
        shapes = _read_csv(
            shapes_path,
            ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"],
        )
        shapes = shapes[shapes["shape_id"].isin(shape_ids)].copy()
        shapes["shape_pt_sequence"] = pd.to_numeric(shapes["shape_pt_sequence"], errors="coerce")
        shapes["shape_pt_lat"] = pd.to_numeric(shapes["shape_pt_lat"], errors="coerce")
        shapes["shape_pt_lon"] = pd.to_numeric(shapes["shape_pt_lon"], errors="coerce")
        shapes = shapes.dropna(subset=["shape_pt_sequence", "shape_pt_lat", "shape_pt_lon"])
        shape_points = {
            str(shape_id): list(zip(group["shape_pt_lat"].astype(float), group["shape_pt_lon"].astype(float)))
            for shape_id, group in shapes.sort_values("shape_pt_sequence").groupby("shape_id", sort=False)
        }

        for row in agency_trips.to_dict("records"):
            shape_id = str(row["shape_id"])
            points = shape_points.get(shape_id, [])
            if len(points) < 2:
                continue
            trip_id = str(row["trip_id"])
            trip_stops = stop_times[stop_times["trip_id"] == trip_id].sort_values("stop_sequence")
            matched = []
            cursor = 0
            for stop_id in trip_stops["stop_id"].astype(str):
                coordinates = stop_coords.get(stop_id)
                if coordinates is None:
                    continue
                lat, lon = coordinates
                nearest = min(
                    range(cursor, len(points)),
                    key=lambda index: (points[index][0] - lat) ** 2 + (points[index][1] - lon) ** 2 * 0.5,
                )
                matched.append((stop_id, nearest))
                cursor = nearest

            route_id = str(row["route_id"])
            for (from_id, from_point), (to_id, to_point) in zip(matched, matched[1:]):
                from_index, to_index = stop_index.get(from_id), stop_index.get(to_id)
                if from_index is None or to_index is None or from_index == to_index:
                    continue
                section = points[min(from_point, to_point):max(from_point, to_point) + 1]
                if from_point > to_point:
                    section = list(reversed(section))
                if len(section) < 2:
                    section = [stop_coords[from_id], stop_coords[to_id]]
                path = tuple(section)
                reverse_path = tuple(reversed(section))
                canonical_path = min(path, reverse_path)
                key = (min(from_index, to_index), max(from_index, to_index), canonical_path)
                if key in seen[route_id]:
                    continue
                seen[route_id].add(key)
                route_segments[route_id].append({
                    "from": from_id,
                    "to": to_id,
                    "points": [[float(lat), float(lon)] for lat, lon in section],
                })

    return route_segments


def _add_transfer(graph, from_stop: str, to_stop: str, duration: int) -> None:
    if from_stop == to_stop or duration < 0:
        return
    graph[from_stop].append({"to": to_stop, "type": "transfer", "duration": int(duration)})


def _add_gtfs_transfers(graph, agencies, valid_stops=None) -> int:
    count = 0
    for agency, directory in agencies.items():
        path = Path(directory) / "transfers.txt"
        if not path.exists():
            continue
        transfers = _read_csv(path, ["from_stop_id", "to_stop_id"], ["transfer_type", "min_transfer_time"])
        for row in transfers.to_dict("records"):
            # Type 3 means transfers are not possible. In-seat transfer types
            # 4 and 5 are not walking edges and are omitted from this graph.
            transfer_type = row.get("transfer_type", "0") or "0"
            if transfer_type in {"3", "4", "5"}:
                continue
            try:
                duration = int(float(row.get("min_transfer_time") or 0))
            except ValueError:
                duration = 0
            prefix = f"{agency}_"
            from_stop = prefix + row["from_stop_id"]
            to_stop = prefix + row["to_stop_id"]
            if valid_stops is not None and (from_stop not in valid_stops or to_stop not in valid_stops):
                continue
            _add_transfer(graph, from_stop, to_stop, duration)
            count += 1
    return count


def _add_nearby_transfers(graph, stops, radius=WALKING_TRANSFER_RADIUS_METERS) -> int:
    """Add walk links among close stops using a spatial grid (not all-pairs)."""
    # A degree-based grid cell is approximately the transfer radius in size.
    lat_cell = radius / 111_000
    lon_cell = radius / 80_000  # conservative for Toronto's latitude
    buckets = defaultdict(list)
    records = stops.to_dict("records")
    count = 0
    for row in records:
        lat, lon = float(row["stop_lat"]), float(row["stop_lon"])
        cell = (int(lat / lat_cell), int(lon / lon_cell))
        stop_id = str(row["stop_id"])
        for y in range(cell[0] - 1, cell[0] + 2):
            for x in range(cell[1] - 1, cell[1] + 2):
                for other in buckets[(y, x)]:
                    other_id, other_lat, other_lon = other
                    distance = distance_meters(lat, lon, other_lat, other_lon)
                    if distance <= radius:
                        duration = int(distance / WALKING_SPEED_METERS_PER_SECOND)
                        _add_transfer(graph, stop_id, other_id, duration)
                        _add_transfer(graph, other_id, stop_id, duration)
                        count += 2
        buckets[cell].append((stop_id, lat, lon))
    return count


def build_graph(stop_times, trips, stops, agencies=None):
    print("Building scheduled transit edges...")
    joined = stop_times.merge(trips[["trip_id", "route_id"]], on="trip_id", how="inner", validate="many_to_one")
    joined = joined.sort_values(["trip_id", "stop_sequence"], kind="stable")
    edges = defaultdict(lambda: defaultdict(list))

    for _, group in joined.groupby("trip_id", sort=False):
        rows = group[["stop_id", "departure_time", "arrival_time", "route_id"]].to_dict("records")
        for current, following in zip(rows, rows[1:]):
            source, target = str(current["stop_id"]), str(following["stop_id"])
            if not source or not target or source == target:
                continue
            try:
                departure = time_to_seconds(current["departure_time"])
                arrival = time_to_seconds(following["arrival_time"])
            except ValueError:
                continue
            # Keep only chronologically valid hops. GTFS after-midnight times
            # (e.g. 25:10:00) naturally remain later than midnight.
            if arrival < departure:
                continue
            edges[source][target].append((departure, arrival, str(current["route_id"])))

    graph = defaultdict(list)
    for source, targets in edges.items():
        for target, trips_for_edge in targets.items():
            trips_for_edge.sort(key=lambda trip: (trip[0], trip[1], trip[2]))
            graph[source].append({
                "to": target,
                "type": "transit",
                "trips": trips_for_edge,
                "departures": [trip[0] for trip in trips_for_edge],
            })

    print("Adding GTFS and nearby-stop transfers...")
    valid_stops = set(stops["stop_id"].astype(str))
    transfer_count = _add_gtfs_transfers(graph, agencies or AGENCIES, valid_stops)
    transfer_count += _add_nearby_transfers(graph, stops)
    # GTFS transfer rules and proximity can describe the same connection.
    # Keep one edge per destination, using the faster specified walk.
    for source, source_edges in graph.items():
        transit_edges = [edge for edge in source_edges if edge["type"] == "transit"]
        transfer_edges = {}
        for edge in source_edges:
            if edge["type"] != "transfer":
                continue
            target = edge["to"]
            if target not in transfer_edges or edge["duration"] < transfer_edges[target]["duration"]:
                transfer_edges[target] = edge
        graph[source] = transit_edges + sorted(transfer_edges.values(), key=lambda edge: edge["to"])
    transfer_count = sum(1 for source_edges in graph.values() for edge in source_edges if edge["type"] == "transfer")
    edge_count = sum(map(len, graph.values()))
    print(f"Created {edge_count:,} edges ({edge_count - transfer_count:,} transit, {transfer_count:,} transfers)")
    return graph
