from pathlib import Path
import pandas as pd


GTFS_DIR = Path("data/ttc")


trips = pd.read_csv(
    GTFS_DIR / "trips.txt",
    nrows=5
)

print(trips)
print()
print(trips.columns)