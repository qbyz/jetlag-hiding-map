from pathlib import Path
import pandas as pd


GTFS_DIR = Path("data/ttc")


stop_times = pd.read_csv(
    GTFS_DIR / "stop_times.txt",
    nrows=5
)

print(stop_times)
print()
print(stop_times.columns)