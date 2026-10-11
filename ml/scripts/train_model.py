"""Phase 7: compare models with Leave-One-Session-Out CV and save the best one.

Steps:
  1. Load the cleaned dataset (ml/data/processed/posture_clean.csv)
  2. For each session: train on the other sessions, test on it
  3. Compare 6 models by macro-F1 (average over sessions)
  4. Save the final model (trained on ALL sessions) to ml/models/
  5. Save the confusion matrix and the classification report
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
RANDOM_STATE = 42


def get_models() -> dict:
    return {
        "dummy_most_frequent": DummyClassifier(strategy="most_frequent"),
        "logistic_regression": make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=2000, random_state=RANDOM_STATE)),
        "decision_tree": DecisionTreeClassifier(
            max_depth=6, random_state=RANDOM_STATE),
        "random_forest": RandomForestClassifier(
            n_estimators=200, random_state=RANDOM_STATE, n_jobs=-1),
        "svm_rbf": make_pipeline(
            StandardScaler(), SVC(kernel="rbf", C=1.0, probability=False)),
        "gradient_boosting": GradientBoostingClassifier(
            random_state=RANDOM_STATE),
    }


def cross_validate(model_factory, X, y, groups) -> tuple[list, list]:
    """Leave-One-Session-Out. Returns per-fold macro-F1 and the true/predicted labels."""
    logo = LeaveOneGroupOut()
    fold_scores, all_true, all_pred = [], [], []
    for train_idx, test_idx in logo.split(X, y, groups):
        model = model_factory()
        model.fit(X[train_idx], y[train_idx])
        pred = model.predict(X[test_idx])
        fold_scores.append(f1_score(y[test_idx], pred, average="macro"))
        all_true.extend(y[test_idx])
        all_pred.extend(pred)
    return fold_scores, (np.array(all_true), np.array(all_pred))


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA_PATH)

    X = df[FEATURE_NAMES].to_numpy()
    y = df["label"].to_numpy()
    groups = df["session_id"].to_numpy()
    print(f"Rows: {len(df)}, sessions: {sorted(set(groups))}")

    results = {}
    best_name, best_mean, best_true_pred = None, -1.0, None

    for name, model in get_models().items():
        # sklearn clones the model inside each fold, so we rebuild from a fresh copy
        from sklearn.base import clone
        factory = lambda m=model: clone(m)
        folds, (yt, yp) = cross_validate(factory, X, y, groups)
        mean_f1 = float(np.mean(folds))
        results[name] = {"fold_macro_f1": [round(f, 4) for f in folds],
                         "mean_macro_f1": round(mean_f1, 4)}
        print(f"{name:22s} folds={[round(f, 3) for f in folds]}  mean macro-F1={mean_f1:.3f}")
        if mean_f1 > best_mean:
            best_name, best_mean, best_true_pred = name, mean_f1, (yt, yp)

    print(f"\nBest model: {best_name} (mean macro-F1 {best_mean:.3f})")

    # Confusion matrix and report for the best model (pooled over all held-out folds)
    yt, yp = best_true_pred
    labels = sorted(set(y))
    print("\nClassification report (pooled over held-out sessions):")
    print(classification_report(yt, yp, labels=labels, digits=3, zero_division=0))

    fig, ax = plt.subplots(figsize=(7, 6))
    ConfusionMatrixDisplay.from_predictions(yt, yp, labels=labels, ax=ax,
                                            xticks_rotation=30, cmap="Blues")
    ax.set_title(f"Confusion matrix: {best_name}")
    fig.tight_layout()
    fig.savefig(ROOT / "ml" / "data" / "processed" / "confusion_matrix.png", dpi=120)
    plt.close(fig)

    # Final model: train on ALL sessions and save
    from sklearn.base import clone
    final_model = clone(get_models()[best_name])
    final_model.fit(X, y)
    model_path = MODEL_DIR / "pulse_model.joblib"
    joblib.dump(final_model, model_path)

    meta = {
        "model_name": best_name,
        "feature_names": FEATURE_NAMES,
        "labels": labels,
        "cv": "leave-one-session-out",
        "results": results,
        "best_mean_macro_f1": round(best_mean, 4),
        "trained_rows": int(len(df)),
        "sessions": sorted(set(groups)),
    }
    (MODEL_DIR / "model_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"\nSaved model: {model_path}")
    print(f"Saved metadata: {MODEL_DIR / 'model_metadata.json'}")
    print(f"Saved confusion matrix: {ROOT / 'ml' / 'data' / 'processed' / 'confusion_matrix.png'}")


if __name__ == "__main__":
    main()