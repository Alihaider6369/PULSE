"""Check: does merging forward_head + slouch into 'poor_posture' help?

This script does NOT overwrite the saved model. It only prints scores.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import f1_score
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from ml.pulse_features import FEATURE_NAMES

DATA_PATH = ROOT / "ml" / "data" / "processed" / "posture_clean.csv"
RANDOM_STATE = 42


def cv_scores(model, X, y, groups) -> list:
    scores = []
    for tr, te in LeaveOneGroupOut().split(X, y, groups):
        m = clone(model)
        m.fit(X[tr], y[tr])
        scores.append(f1_score(y[te], m.predict(X[te]), average="macro"))
    return scores


def main() -> None:
    df = pd.read_csv(DATA_PATH)
    X = df[FEATURE_NAMES].to_numpy()
    groups = df["session_id"].to_numpy()
    model = make_pipeline(StandardScaler(), SVC(kernel="rbf", C=1.0))

    # Setup A: 5 classes (current)
    y5 = df["label"].to_numpy()
    s5 = cv_scores(model, X, y5, groups)
    print(f"5 classes      folds={[round(s, 3) for s in s5]}  mean macro-F1={np.mean(s5):.3f}")

    # Setup B: forward_head + slouch merged -> 4 classes
    y4 = df["label"].replace({"forward_head": "poor_posture", "slouch": "poor_posture"}).to_numpy()
    s4 = cv_scores(model, X, y4, groups)
    print(f"4 classes (merged) folds={[round(s, 3) for s in s4]}  mean macro-F1={np.mean(s4):.3f}")

    print("\nNote: the 4-class score is on a different task, so it is not directly comparable.")
    print("Use it to decide whether the merged class is reliable enough for live feedback.")


if __name__ == "__main__":
    main()