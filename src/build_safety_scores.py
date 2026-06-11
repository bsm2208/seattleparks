"""
build_safety_scores.py
======================
Generates parks_with_safety.csv by spatially joining SPD crime data
to each park within a 0.5-mile radius, then computing a safety score.

Only "crimes against a person" are counted (NIBRS category = PERSON),
which maps to: homicide, rape, robbery, aggravated assault, simple
assault, kidnapping, sex offenses, human trafficking, etc.

Safety score methodology
------------------------
Uses a logistic curve anchored to the *median* annual incident count
across all Seattle parks, so score 5.0 always means "exactly average
for this dataset" regardless of radius. The scale spreads naturally
around that midpoint:

  Score 10  → well below median  (e.g. Carkeek, Discovery Park)
  Score  5  → median park        (e.g. Thornton Creek, Coe Play Park)
  Score  1  → far above median   (e.g. Westlake, Freeway Park)

0.5 miles was chosen as the radius because Seattle is ~84 sq miles
total; 1 mile circles overlap too many neighborhoods and inflate counts
for parks near-but-not-in high-crime areas.

Usage
-----
    python build_safety_scores.py \
        --parks  data/parks_with_neighborhoods.csv \
        --crime  data/SPD_Crime_Data__2008-Present_20260604.csv \
        --output data/parks_with_safety.csv \
        --radius 0.5 \
        --years  2020 2025

Dependencies: pandas, numpy, scikit-learn
"""

import argparse
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.neighbors import BallTree

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EARTH_RADIUS_MILES = 3958.8
LOGISTIC_STEEPNESS = 0.04  # steepness tuned for 0.5-mile radius incident counts


def logistic_safety(annual_incidents: np.ndarray) -> np.ndarray:
    """
    Maps annual incident count → safety score 1–10 using a logistic curve.
    Midpoint is set dynamically to the median of the dataset so that
    score 5.0 always means "exactly average for Seattle parks."

    Formula: score = 1 + 9 / (1 + exp(k * (x - median)))
    """
    midpoint = float(np.median(annual_incidents))
    raw = 1 + 9 / (1 + np.exp(LOGISTIC_STEEPNESS * (annual_incidents - midpoint)))
    return np.clip(np.round(raw, 1), 1.0, 10.0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def build_safety_scores(parks_path: str, crime_path: str, output_path: str,
                         radius_miles: float, year_start: int, year_end: int):

    parks = pd.read_csv(parks_path)
    parks = parks[parks["Name"].apply(lambda x: isinstance(x, str))].copy()
    parks = parks[parks["X Coord"].notna() & parks["Y Coord"].notna()].copy()
    parks = parks.reset_index(drop=True)
    print(f"  {len(parks)} parks with valid coordinates")

    crime = pd.read_csv(crime_path)
    print(f"  {len(crime):,} total records")

    # --- Filter: years ---
    crime["year"] = crime["Offense Date"].str[:4].astype(int, errors="ignore")
    crime = crime[(crime["year"] >= year_start) & (crime["year"] <= year_end)].copy()
    num_years = year_end - year_start + 1
    print(f"  {len(crime):,} records in {year_start}–{year_end} ({num_years} years)")

    # --- Filter: crimes against a PERSON only (NIBRS standard) ---
    crime = crime[crime["NIBRS Crime Against Category"] == "PERSON"].copy()
    print(f"  {len(crime):,} PERSON crimes (NIBRS Crime Against Category = PERSON)")
    print(f"  Offense types included:")
    for cat, count in crime["Offense Sub Category"].value_counts().head(12).items():
        print(f"    {cat}: {count:,}")

    # --- Filter: valid Seattle coordinates ---
    crime["Latitude"]  = pd.to_numeric(crime["Latitude"],  errors="coerce")
    crime["Longitude"] = pd.to_numeric(crime["Longitude"], errors="coerce")
    crime = crime[
        (crime["Latitude"]  > 47.48) & (crime["Latitude"]  < 47.74) &
        (crime["Longitude"] > -122.46) & (crime["Longitude"] < -122.22)
    ].copy()
    print(f"  {len(crime):,} with valid Seattle lat/lon")

    if len(crime) == 0:
        sys.exit("ERROR: No crime records after filters.")

    # --- Spatial join via BallTree (haversine) ---
    print(f"\nBuilding BallTree on {len(parks)} park locations ...")
    park_coords  = np.radians(parks[["Y Coord", "X Coord"]].values)
    crime_coords = np.radians(crime[["Latitude", "Longitude"]].values)
    radius_rad   = radius_miles / EARTH_RADIUS_MILES

    tree = BallTree(park_coords, metric="haversine")

    print(f"Querying: crimes within {radius_miles} mile(s) of each park ...")
    indices = tree.query_radius(crime_coords, r=radius_rad)

    # Accumulate per-park counts
    park_total    = np.zeros(len(parks), dtype=np.int64)
    park_violent  = np.zeros(len(parks), dtype=np.int64)
    park_assault  = np.zeros(len(parks), dtype=np.int64)
    park_robbery  = np.zeros(len(parks), dtype=np.int64)
    park_sex      = np.zeros(len(parks), dtype=np.int64)

    sub_cats = crime["Offense Sub Category"].values

    VIOLENT_SUBS = {"AGGRAVATED ASSAULT", "ROBBERY", "HOMICIDE", "RAPE"}
    ASSAULT_SUBS = {"AGGRAVATED ASSAULT", "ASSAULT OFFENSES"}
    ROBBERY_SUBS = {"ROBBERY"}
    SEX_SUBS     = {"RAPE", "SEX OFFENSES", "HUMAN TRAFFICKING"}

    for i, park_idxs in enumerate(indices):
        s = sub_cats[i]
        for pidx in park_idxs:
            park_total[pidx]   += 1
            if s in VIOLENT_SUBS: park_violent[pidx] += 1
            if s in ASSAULT_SUBS: park_assault[pidx] += 1
            if s in ROBBERY_SUBS: park_robbery[pidx] += 1
            if s in SEX_SUBS:     park_sex[pidx]     += 1

    # Annualize
    parks["annual_person_crimes"]  = np.round(park_total   / num_years).astype(int)
    parks["annual_violent_crimes"] = np.round(park_violent / num_years).astype(int)
    parks["annual_assaults"]       = np.round(park_assault / num_years).astype(int)
    parks["annual_robberies"]      = np.round(park_robbery / num_years).astype(int)
    parks["annual_sex_crimes"]     = np.round(park_sex     / num_years).astype(int)

    # Safety score (logistic, anchored to dataset median)
    parks["safety_score"] = logistic_safety(parks["annual_person_crimes"].values.astype(float))

    # --- Output ---
    parks.to_csv(output_path, index=False)
    print(f"\nSaved → {output_path}")
    cols = ["Name", "L_HOOD", "safety_score", "annual_person_crimes", "annual_violent_crimes"]
    print(f"\nTop 10 safest:")
    print(parks[cols].sort_values("safety_score", ascending=False).head(10).to_string(index=False))
    print(f"\nBottom 10:")
    print(parks[cols].sort_values("safety_score").head(10).to_string(index=False))

    print(f"\nScore distribution:")
    bins   = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10.1]
    labels = ["1", "2", "3", "4", "5", "6", "7", "8", "9-10"]
    parks["_bin"] = pd.cut(parks["safety_score"], bins=bins, labels=labels, right=False)
    print(parks["_bin"].value_counts().sort_index().to_string())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[1]
    data_dir = project_root / "data"

    parser = argparse.ArgumentParser(description="Build park safety scores from SPD crime data")
    parser.add_argument("--parks",  default=str(data_dir / "parks_with_neighborhoods.csv"))
    parser.add_argument("--crime",  default=str(data_dir / "SPD_Crime_Data__2008-Present_20260604.csv"))
    parser.add_argument("--output", default=str(data_dir / "parks_with_safety.csv"))
    parser.add_argument("--radius", type=float, default=0.5, help="Radius in miles (default: 0.5)")
    parser.add_argument("--years",  type=int, nargs=2, default=[2020, 2025],
                        metavar=("START", "END"), help="Year range inclusive (default: 2020 2025)")
    args = parser.parse_args()

    build_safety_scores(
        parks_path=args.parks,
        crime_path=args.crime,
        output_path=args.output,
        radius_miles=args.radius,
        year_start=args.years[0],
        year_end=args.years[1],
    )