import csv
import tempfile
import unittest
from pathlib import Path

import msgpack

from processor.export_graph import export_graph
from processor.transit import build_graph, build_route_lookup, load_data


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def make_feed(directory: Path, agency: str) -> None:
    directory.mkdir(parents=True)
    write_csv(directory / "stops.txt", ["stop_id", "stop_name", "stop_lat", "stop_lon", "parent_station", "location_type"], [
        {"stop_id": f"{agency}_sub_a", "stop_name": "Subway A", "stop_lat": 43.60, "stop_lon": -79.60, "parent_station": "", "location_type": ""},
        {"stop_id": f"{agency}_sub_b", "stop_name": "Subway B", "stop_lat": 43.61, "stop_lon": -79.60, "parent_station": "", "location_type": ""},
        {"stop_id": f"{agency}_bus_a", "stop_name": "Bus only A", "stop_lat": 43.70, "stop_lon": -79.60, "parent_station": "", "location_type": ""},
        {"stop_id": f"{agency}_bus_b", "stop_name": "Bus only B", "stop_lat": 43.71, "stop_lon": -79.60, "parent_station": "", "location_type": ""},
        {"stop_id": f"{agency}_street_a", "stop_name": "Streetcar only A", "stop_lat": 43.80, "stop_lon": -79.60, "parent_station": "", "location_type": ""},
        {"stop_id": f"{agency}_street_b", "stop_name": "Streetcar only B", "stop_lat": 43.81, "stop_lon": -79.60, "parent_station": "", "location_type": ""},
        {"stop_id": f"{agency}_lrt_a", "stop_name": "LRT A", "stop_lat": 43.90, "stop_lon": -79.60, "parent_station": "", "location_type": ""},
        {"stop_id": f"{agency}_lrt_b", "stop_name": "LRT B", "stop_lat": 43.91, "stop_lon": -79.60, "parent_station": "", "location_type": ""},
    ])
    routes = [
        {"route_id": "subway", "route_type": "1", "route_short_name": "1", "route_long_name": "Line 1"},
        {"route_id": "bus", "route_type": "3", "route_short_name": "10", "route_long_name": "Bus"},
        {"route_id": "streetcar", "route_type": "0", "route_short_name": "501", "route_long_name": "Queen"},
        {"route_id": "lrt", "route_type": "0", "route_short_name": "5", "route_long_name": "Line 5 Eglinton"},
    ]
    if agency == "go":
        routes = [{"route_id": "rail", "route_type": "2", "route_short_name": "LE", "route_long_name": "Lakeshore East"}]
    write_csv(directory / "routes.txt", ["route_id", "route_type", "route_short_name", "route_long_name"], routes)
    trips = [
        {"trip_id": "trip_subway", "route_id": "subway"},
        {"trip_id": "trip_bus", "route_id": "bus"},
        {"trip_id": "trip_streetcar", "route_id": "streetcar"},
        {"trip_id": "trip_lrt", "route_id": "lrt"},
    ]
    if agency == "go":
        trips = [{"trip_id": "trip_subway", "route_id": "rail"}]
    write_csv(directory / "trips.txt", ["trip_id", "route_id"], trips)
    stop_time_rows = []
    for trip_id, start, end in [
        ("trip_subway", f"{agency}_sub_a", f"{agency}_sub_b"),
        ("trip_bus", f"{agency}_bus_a", f"{agency}_bus_b"),
        ("trip_streetcar", f"{agency}_street_a", f"{agency}_street_b"),
        ("trip_lrt", f"{agency}_lrt_a", f"{agency}_lrt_b"),
    ]:
        stop_time_rows.extend([
            {"trip_id": trip_id, "stop_id": start, "stop_sequence": 1, "arrival_time": "08:00:00", "departure_time": "08:00:00"},
            {"trip_id": trip_id, "stop_id": end, "stop_sequence": 2, "arrival_time": "08:10:00", "departure_time": "08:10:00"},
        ])
    write_csv(directory / "stop_times.txt", ["trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time"], stop_time_rows)


class StationGraphTests(unittest.TestCase):
    def test_load_data_excludes_bus_and_streetcar_only_stops(self):
        with tempfile.TemporaryDirectory() as temp:
            feed = Path(temp) / "ttc"
            make_feed(feed, "ttc")
            stop_times, trips, stops, routes = load_data({"ttc": feed})

            self.assertEqual(set(routes["route_short_name"]), {"1", "5"})
            self.assertEqual(
                set(stops["stop_id"]),
                {"ttc_ttc_sub_a", "ttc_ttc_sub_b", "ttc_ttc_lrt_a", "ttc_ttc_lrt_b"},
            )
            self.assertEqual(set(stop_times["trip_id"]), {"ttc_trip_subway", "ttc_trip_lrt"})
            self.assertEqual(set(stops["agency"]), {"ttc"})

    def test_load_data_keeps_go_rail_stations(self):
        with tempfile.TemporaryDirectory() as temp:
            feed = Path(temp) / "go"
            make_feed(feed, "go")
            _, _, stops, routes = load_data({"go": feed})

            self.assertEqual(set(routes["station_mode"]), {"rail"})
            self.assertEqual(set(stops["stop_id"]), {"go_go_sub_a", "go_go_sub_b"})
            self.assertTrue(all(stop_modes == ["rail"] for stop_modes in stops["modes"]))

    def test_export_contains_only_station_graph_nodes(self):
        with tempfile.TemporaryDirectory() as temp:
            feed = Path(temp) / "ttc"
            make_feed(feed, "ttc")
            stop_times, trips, stops, routes = load_data({"ttc": feed})
            graph = build_graph(stop_times, trips, stops, agencies={"ttc": feed})
            output = Path(temp) / "graph.msgpack"
            export_graph(graph, stops, build_route_lookup(routes), output)

            with output.open("rb") as stream:
                payload = msgpack.unpack(stream, raw=False)
            names = {stop["name"] for stop in payload["stops"]}
            self.assertFalse(any("Bus only" in name or "Streetcar only" in name for name in names))
            self.assertEqual(len(payload["graph"]), len(payload["stops"]))
            self.assertTrue(any(stop["modes"] == ["subway"] for stop in payload["stops"]))
            self.assertTrue(any(stop["modes"] == ["light_rail"] for stop in payload["stops"]))


if __name__ == "__main__":
    unittest.main()
