"""Phase 6 (part 1): load all raw CSVs and show what we have."""
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


def load_all() -> pd.DataFrame:
    files = sorted(RAW_DIR.glob("posture_*.csv"))
    if not files:
        raise SystemExit("No CSV files found in ml/data/raw")
    frames = []
    for f in files:
        df = pd.read_csv(f)
        df["source_file"] = f.name
        frames.append(df)
        print(f"{f.name}: {len(df)} rows")
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    df = load_all()
    print("\nTotal rows:", len(df))

    print("\nRows per label:")
    print(df["label"].value_counts().to_string())

    print("\nRows per session:")
    print(df.groupby(["session_id", "label"]).size().to_string())

    print("\nMissing values per column (should be 0):")
    print(df.isna().sum()[lambda s: s > 0].to_string() or "none")

    print("\nDuplicate rows:", df.duplicated().sum())


if __name__ == "__main__":
    main()