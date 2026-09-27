#!/usr/bin/env python3
"""
Compute all stations reachable from Bloor–Yonge at 09:30 for 45 minutes.
Run from repository root with:

    python processor/reachable_bloor_yonge.py

This uses the same loader and router utilities in the processor package.
"""
from transit import load_data, build_graph, build_route_lookup
from router import reachable_stops, format_reachable
try:
    import pandas as pd
except Exception:
    print("Missing dependency: pandas is required to run this script.")
    print()
    print("Install dependencies with:")
    print("  python3 -m pip install -r processor/requirements.txt")
    print()
    raise

# 9:30 AM -> seconds since midnight
DEPARTURE_SECONDS = 9 * 3600 + 45 * 60  # 34200
BUDGET_SECONDS = 45 * 60  # 2700


def find_start_stop_id(stops_df, name_substrings=("bloor", "yonge")):
    # stops_df here is the stops DataFrame returned by load_data(), which
    # already has agency prefixes on stop_id (e.g. "ttc_16067").
    mask = pd.Series(True, index=stops_df.index)
    for s in name_substrings:
        mask &= stops_df["stop_name"].str.lower().str.contains(s)
    matches = stops_df[mask]
    if matches.empty:
        # fallback: any stop containing both words separate (in case names vary)
        mask2 = stops_df["stop_name"].str.lower().str.contains("bloor") & stops_df["stop_name"].str.lower().str.contains("yonge")
        matches = stops_df[mask2]
    if matches.empty:
        raise RuntimeError("Could not find a stop whose name contains both 'Bloor' and 'Yonge'. Inspect stops.csv manually.")
    # return the first match's stop_id (prefer station-level rows if available)
    # If parent_station exists, prefer a row where parent_station is NaN (a station-level row)
    if "parent_station" in matches.columns:
        station_rows = matches[matches["parent_station"].isna()]
        if not station_rows.empty:
            return station_rows.iloc[0]["stop_id"]
    return matches.iloc[0]["stop_id"]


def main():
    stop_times, trips, stops, routes = load_data()
    graph = build_graph(stop_times, trips, stops)
    route_names = build_route_lookup(routes)

    # locate Bloor–Yonge stop_id (will be prefixed, e.g. "ttc_16067")
    start = find_start_stop_id(stops)
    print(f"Using start stop_id: {start}")

    reachable, _ = reachable_stops(
        graph,
        start,
        DEPARTURE_SECONDS,
        budget_seconds=BUDGET_SECONDS
    )

    results = format_reachable(reachable, stops, DEPARTURE_SECONDS, exclude_start=True)
    # Only include results whose display name contains the word "station"
    station_results = [r for r in results if "station" in r[0].lower()]

    # Normalize display names to canonical station names and deduplicate.
    # Strategy: find the first occurrence of the word 'station' and take the
    # substring up to and including that word (e.g. "Yonge Station - Westbound"
    # -> "Yonge Station"). This collapses platform variants to the station
    # level.
    import re

    def canonical(name: str) -> str:
        m = re.search(r"\bstation\b", name, flags=re.IGNORECASE)
        if m:
            return name[: m.end()].strip()
        return name.strip()

    best = {}
    for name, minutes in station_results:
        cname = canonical(name)
        key = cname.lower()
        if key not in best or minutes < best[key][1]:
            best[key] = (cname, minutes)

    deduped = list(best.values())
    deduped.sort(key=lambda r: r[1])

    print(f"Stations reachable from {start} at 09:30 within 45 minutes ({len(deduped)} results):")
    for name, minutes in deduped:
        print(f"  {name} ({minutes:.1f} min)")


if __name__ == "__main__":
    main()





