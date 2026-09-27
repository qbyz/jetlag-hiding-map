from pathlib import Path
import pandas as pd


GTFS_DIR = Path("data/ttc")


def load_stops():
    stops_file = GTFS_DIR / "stops.txt"

    print("Loading stops...")

    stops = pd.read_csv(stops_file)

    print(f"Loaded {len(stops)} stops")

    return stops


if __name__ == "__main__":
    stops = load_stops()

    print()
    print(stops.head())
    print()

    print(stops.columns)