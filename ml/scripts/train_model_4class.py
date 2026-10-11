"""Phase 7 (final): train the 4-class model (forward_head + slouch -> poor_posture).

Steps:
  1. Load the cleaned dataset
  2. Merge forward_head and slouch into 'poor_posture'
  3. Leave-One-Session-Out CV, compare 6 models by macro-F1
  4. Save the best model trained on ALL sessions to ml/models/pulse_model.joblib
  5. Save metadata and confusion matrix

The 5-class model is kept as pulse_model_5class.joblib (renamed, not deleted).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import ConfusionMatrixDisplay, classification_report, f1_score
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier

from ml.pulse_features import FEATURE_NAMES

DATA_PATH = ROOT / "ml" / "data" / "processed" / "posture_clean.csv"
MODEL_DIR = ROOT / "ml" / "models"
PROC_DIR = ROOT / "ml" / "data" / "processed"
RANDOM_STATE = 42

MERGE_MAP = {"forward_head": "poor_posture", "slouch": "poor_posture"}


def get_models() -> dict:
    return {
        "dummy_most_frequent": DummyClassifier(strategy="most_frequent"),
        "logistic_regression": make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=2000, random_state=RANDOM_STATE)),
        "decision_tree": DecisionTreeClassifier(max_depth=6, random_state=RANDOM_STATE),
        "random_forest": RandomForestClassifier(
            n_estimators=200, random_state=RANDOM_STATE, n_jobs=-1),
        "svm_rbf": make_pipeline(StandardScaler(), SVC(kernel="rbf", C=1.0, probability=True, random_state=RANDOM_STATE)),
        "gradient_boosting": GradientBoostingClassifier(random_state=RANDOM_STATE),
    }


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Keep the old 5-class model under a clear name (do not delete it)
    old_model = MODEL_DIR / "pulse_model.joblib"
    if old_model.exists():
        old_model.replace(MODEL_DIR / "pulse_model_5class.joblib")
        print("Renamed old model to pulse_model_5class.joblib")

    df = pd.read_csv(DATA_PATH)
    df["label"] = df["label"].replace(MERGE_MAP)

    X = df[FEATURE_NAMES].to_numpy()
    y = df["label"].to_numpy()
    groups = df["session_id"].to_numpy()
    print(f"Rows: {len(df)}, sessions: {sorted(set(groups))}")
    print(f"Classes: {sorted(set(y))}")

    results = {}
    best_name, best_mean, best_pred = None, -1.0, None

    for name, model in get_models().items():
        fold_scores, all_true, all_pred = [], [], []
        for tr, te in LeaveOneGroupOut().split(X, y, groups):
            m = clone(model)
            m.fit(X[tr], y[tr])
            pred = m.predict(X[te])
            fold_scores.append(f1_score(y[te], pred, average="macro"))
            all_true.extend(y[te])
            all_pred.extend(pred)
        mean_f1 = float(np.mean(fold_scores))
        results[name] = {"fold_macro_f1": [round(f, 4) for f in fold_scores],
                         "mean_macro_f1": round(mean_f1, 4)}
        print(f"{name:22s} folds={[round(f, 3) for f in fold_scores]}  mean macro-F1={mean_f1:.3f}")
        if mean_f1 > best_mean:
            best_name, best_mean = name, mean_f1
            best_pred = (np.array(all_true), np.array(all_pred))

    print(f"\nBest model: {best_name} (mean macro-F1 {best_mean:.3f})")

    labels = sorted(set(y))
    yt, yp = best_pred
    print("\nClassification report (pooled over held-out sessions):")
    print(classification_report(yt, yp, labels=labels, digits=3, zero_division=0))

    cm_path = PROC_DIR / "confusion_matrix_4class.png"
    fig, ax = plt.subplots(figsize=(6, 5))
    ConfusionMatrixDisplay.from_predictions(yt, yp, labels=labels, ax=ax,
                                            xticks_rotation=30, cmap="Blues")
    ax.set_title(f"4-class confusion matrix: {best_name}")
    fig.tight_layout()
    fig.savefig(cm_path, dpi=120)
    plt.close(fig)

    final_model = clone(get_models()[best_name])
    final_model.fit(X, y)
    model_path = MODEL_DIR / "pulse_model.joblib"
    joblib.dump(final_model, model_path)

    meta = {
        "model_name": best_name,
        "classes": labels,
        "merged_classes": {"poor_posture": ["forward_head", "slouch"]},
        "feature_names": FEATURE_NAMES,
        "cv": "leave-one-session-out",
        "results": results,
        "best_mean_macro_f1": round(best_mean, 4),
        "trained_rows": int(len(df)),
        "sessions": sorted(set(groups)),
    }
    (MODEL_DIR / "model_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"\nSaved model: {model_path}")
    print(f"Saved metadata: {MODEL_DIR / 'model_metadata.json'}")
    print(f"Saved confusion matrix: {cm_path}")


if __name__ == "__main__":
    main()