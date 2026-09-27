import heapq
import itertools
import bisect
import pandas as pd
from transit import load_data, build_graph, build_route_lookup


def reachable_stops(graph, start, departure_time, budget_seconds):
    """
    One-to-many version of the same Dijkstra: instead of stopping at a
    single target, explore everything reachable within `budget_seconds`
    of `departure_time`.

    Returns:
        arrival: dict[stop_id] -> earliest arrival_time (seconds),
                 filtered to stops within budget
        previous: dict[stop_id] -> (prev_stop, edge, route_id), same
                  shape as route()'s internal bookkeeping, so paths back
                  to `start` can still be reconstructed if needed
    """
    counter = itertools.count()
    deadline = departure_time + budget_seconds

    heap = [
        (
            departure_time,
            next(counter),
            start
        )
    ]
    arrival = {
        start: departure_time
    }
    previous = {}

    while heap:
        current_time, _, current = heapq.heappop(heap)

        # Dijkstra pops in non-decreasing time order, so once we're past
        # the deadline nothing left in the heap can be closer either --
        # safe to stop here instead of draining the whole graph.
        if current_time > deadline:
            break

        if current_time > arrival.get(
            current,
            float("inf")
        ):
            continue

        for edge in graph.get(current, []):
            neighbor = edge["to"]
            route_id = None

            if edge["type"] == "transit":
                idx = bisect.bisect_left(
                    edge["departures"],
                    current_time
                )
                if idx == len(edge["trips"]):
                    continue
                depart, arrive, route_id = edge["trips"][idx]
                next_time = arrive
            elif edge["type"] == "transfer":
                next_time = (
                    current_time
                    + edge["duration"]
                )
            else:
                continue

            if next_time > deadline:
                continue

            if next_time < arrival.get(
                neighbor,
                float("inf")
            ):
                arrival[neighbor] = next_time
                previous[neighbor] = (
                    current,
                    edge,
                    route_id
                )
                heapq.heappush(
                    heap,
                    (
                        next_time,
                        next(counter),
                        neighbor
                    )
                )

    return arrival, previous


def format_reachable(arrival, stops, departure_time, exclude_start=True):
    """
    arrival -> list of (display_name, minutes_away), sorted by minutes_away.

    A single GTFS station is usually split across several platform-level
    stop_ids (e.g. "Mount Dennis Station LRT Platform", eastbound vs
    westbound bus platforms, etc). Left ungrouped, reachable_stops() would
    report the same station many times over. This groups by parent_station
    where available (falling back to stop_name for stops with no parent,
    e.g. plain bus stops) and keeps only the earliest arrival per group.
    """
    stop_lookup = stops.set_index("stop_id")

    best = {}  # group_key -> (display_name, minutes)

    for stop_id, arrival_time in arrival.items():
        minutes = (arrival_time - departure_time) / 60
        if exclude_start and minutes == 0:
            continue

        if stop_id in stop_lookup.index:
            row = stop_lookup.loc[stop_id]
            parent = row.get("parent_station")
            # group by parent station id when there is one, otherwise by
            # the stop's own id -- NEVER by name, or a station's own row
            # (no parent) and its child platforms (parent = station id)
            # end up keyed differently and fail to merge
            group_key = parent if pd.notna(parent) and str(parent).strip() else stop_id
        else:
            group_key = stop_id

        # prefer the station-level name for display, if we have one
        if group_key in stop_lookup.index:
            name = stop_lookup.loc[group_key]["stop_name"]
        elif stop_id in stop_lookup.index:
            name = stop_lookup.loc[stop_id]["stop_name"]
        else:
            name = stop_id

        if group_key not in best or minutes < best[group_key][1]:
            best[group_key] = (name, minutes)

    results = list(best.values())
    results.sort(key=lambda r: r[1])
    return results


def route(graph, start, target, departure_time):
    counter = itertools.count()
    heap = [
        (
            departure_time,
            next(counter),
            start
        )
    ]
    arrival = {
        start: departure_time
    }
    previous = {}
    while heap:
        current_time, _, current = heapq.heappop(heap)
        if current == target:
            break
        if current_time > arrival.get(
            current,
            float("inf")
        ):
            continue
        for edge in graph.get(current, []):
            neighbor = edge["to"]
            route_id = None
            if edge["type"] == "transit":
                # NEW: bisect instead of scanning every departure
                idx = bisect.bisect_left(
                    edge["departures"],
                    current_time
                )
                if idx == len(edge["trips"]):
                    continue
                depart, arrive, route_id = edge["trips"][idx]
                next_time = arrive
            elif edge["type"] == "transfer":
                next_time = (
                    current_time
                    + edge["duration"]
                )
            else:
                continue
            if next_time < arrival.get(
                neighbor,
                float("inf")
            ):
                arrival[neighbor] = next_time
                previous[neighbor] = (
                    current,
                    edge,
                    route_id
                )
                heapq.heappush(
                    heap,
                    (
                        next_time,
                        next(counter),
                        neighbor
                    )
                )
    if target not in arrival:
        return None
    path = []
    node = target
    while node != start:
        prev, edge, route_id = previous[node]
        path.append(
            (
                prev,
                node,
                edge,
                route_id
            )
        )
        node = prev
    return (
        list(reversed(path)),
        arrival[target]
    )


def format_path(path, stops, route_names):
    """
    Prints:
        Stop Name
        Line X Name
        Stop Name
        TRANSFER
        Stop Name
        Line Y Name
        ...

    A TRANSFER line is emitted either for an explicit "transfer" edge
    (walking between platforms/stations) or when two consecutive
    transit hops use a different route_id with no transfer edge
    between them (e.g. same-platform line change).
    """

    lines = []
    current_route = None

    def stop_name(stop_id):
        return stops.loc[
            stops["stop_id"] == str(stop_id),
            "stop_name"
        ].iloc[0]

    first_stop = path[0][0]
    lines.append(stop_name(first_stop))

    for a, b, edge, route_id in path:

        if edge["type"] == "transfer":
            lines.append("TRANSFER")
            current_route = None
            lines.append(stop_name(b))
            continue

        # transit hop
        if route_id != current_route:
            if current_route is not None:
                lines.append("TRANSFER")
            current_route = route_id

        lines.append(stop_name(b))
        lines.append(
            route_names.get(route_id, route_id)
        )

    return "\n".join(lines)


if __name__ == "__main__":
    stop_times, trips, stops, routes = load_data()
    graph = build_graph(
        stop_times,
        trips,
        stops
    )
    route_names = build_route_lookup(routes)
    print(
        "Graph ready"
    )

    # NEW: stop_id is now agency-prefixed ("ttc_16067") since load_data()
    # can merge multiple GTFS feeds into one graph.
    start = "ttc_16067"
    target = "ttc_16204"
    departure = 20700

    result = route(
        graph,
        start,
        target,
        departure
    )
    if result:
        path, arrival = result
        print()
        print(
            "Arrival:",
            arrival
        )
        print(
            "Duration:",
            arrival - departure,
            "seconds"
        )
        print()
        print(
            format_path(path, stops, route_names)
        )
    else:
        print(
            "No route found"
        )

    # NEW: one-to-many reachability from the same start point --
    # everything you can reach within 20 minutes.
    print()
    print("Reachable within 20 minutes:")
    reachable, _ = reachable_stops(
        graph,
        start,
        departure,
        budget_seconds=20 * 60
    )
    for name, minutes in format_reachable(reachable, stops, departure):
        print(f"  {name} ({minutes:.1f} min)")e