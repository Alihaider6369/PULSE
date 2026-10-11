"""Phase 6: clean the raw data and run EDA (charts saved to ml/data/processed).

Steps:
  1. Load all raw CSVs
  2. Drop test sessions (too small to be useful)
  3. Check missing values, duplicates, and out-of-range features
  4. Save the cleaned dataset to ml/data/processed/posture_clean.csv
  5. Make charts: class balance, feature distributions, correlation heatmap
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")          # save charts to files, no popup windows
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import sys
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_PATH))

from ml.pulse_features import FEATURE_NAMES

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "ml" / "data" / "raw"
PROC_DIR = ROOT / "ml" / "data" / "processed"

MIN_ROWS_PER_SESSION = 100     # smaller sessions are treated as tests
MIN_CLASSES_PER_SESSION = 5    # a useful session has all 5 labels


def load_raw() -> pd.DataFrame:
    files = sorted(RAW_DIR.glob("posture_*.csv"))
    if not files:
        raise SystemExit("No CSV files found in ml/data/raw")
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)


def keep_good_sessions(df: pd.DataFrame) -> pd.DataFrame:
    stats = df.groupby("session_id").agg(
        rows=("label", "size"),
        classes=("label", "nunique"),
    )
    keep = stats[(stats["rows"] >= MIN_ROWS_PER_SESSION)
                 & (stats["classes"] >= MIN_CLASSES_PER_SESSION)].index
    dropped = set(stats.index) - set(keep)
    print("Kept sessions:", list(keep))
    print("Dropped test sessions:", sorted(dropped))
    return df[df["session_id"].isin(keep)].copy()


def clean(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)
    df = df.dropna(subset=FEATURE_NAMES + ["label"])
    df = df.drop_duplicates()

    # Physical sanity limits (wide on purpose: we only remove impossible values)
    ok = (
        df["shoulder_width_ratio"].between(0.05, 0.9)
        & df["shoulder_tilt_deg"].between(-45, 45)
        & df["head_offset_x"].between(-3, 3)
        & df["nose_height"].between(-3, 5)
        & df["neck_angle_deg"].between(-90, 90)
    )
    df = df[ok]
    print(f"Cleaning: {before} -> {len(df)} rows")
    return df


def class_balance_chart(df: pd.DataFrame) -> None:
    plt.figure(figsize=(7, 4))
    order = df["label"].value_counts().index
    sns.countplot(data=df, x="label", order=order, hue="label", legend=False)
    plt.title("Class balance (rows per posture)")
    plt.xlabel("Posture label")
    plt.ylabel("Rows")
    plt.tight_layout()
    plt.savefig(PROC_DIR / "eda_class_balance.png", dpi=120)
    plt.close()


def feature_distribution_chart(df: pd.DataFrame) -> None:
    key_features = ["shoulder_tilt_deg", "head_offset_x", "nose_height",
                    "neck_angle_deg", "head_shoulder_dist", "shoulder_width_ratio"]
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    for ax, feat in zip(axes.ravel(), key_features):
        sns.boxplot(data=df, x="label", y=feat, ax=ax, hue="label", legend=False)
        ax.set_title(feat)
        ax.tick_params(axis="x", rotation=30)
        ax.set_xlabel("")
    fig.suptitle("Feature distribution per posture", fontsize=14)
    fig.tight_layout()
    fig.savefig(PROC_DIR / "eda_feature_boxplots.png", dpi=120)
    plt.close(fig)


def correlation_chart(df: pd.DataFrame) -> None:
    corr = df[FEATURE_NAMES].corr()
    plt.figure(figsize=(11, 9))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm",
                vmin=-1, vmax=1, annot_kws={"size": 7})
    plt.title("Feature correlation")
    plt.tight_layout()
    plt.savefig(PROC_DIR / "eda_correlation.png", dpi=120)
    plt.close()


def main() -> None:
    PROC_DIR.mkdir(parents=True, exist_ok=True)

    raw = load_raw()
    print(f"Raw rows: {len(raw)}")
    good = keep_good_sessions(raw)
    clean_df = clean(good)

    out = PROC_DIR / "posture_clean.csv"
    clean_df.to_csv(out, index=False)
    print(f"Saved cleaned data: {out}")

    print("\nRows per label after cleaning:")
    print(clean_df["label"].value_counts().to_string())

    print("\nFeature summary (mean / std):")
    print(clean_df[FEATURE_NAMES].agg(["mean", "std"]).T.round(2).to_string())

    class_balance_chart(clean_df)
    feature_distribution_chart(clean_df)
    correlation_chart(clean_df)
    print("\nCharts saved in ml/data/processed/")


if __name__ == "__main__":
    main()