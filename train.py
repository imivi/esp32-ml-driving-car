#!/usr/bin/env python3
"""Train a Random Forest classifier for autonomous RC car driving."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split

FEATURE_COLUMNS = ["dist_left_mm", "dist_center_mm", "dist_right_mm"]
TARGET_COLUMN = "direction"
VALID_DIRECTIONS = ["FORWARD", "FORWARD_LEFT", "FORWARD_RIGHT"]
CV_SPLITS = 5


def load_and_preprocess_data(csv_path: Path) -> pd.DataFrame:
    """Load, validate, and clean the training dataset."""
    if not csv_path.is_file():
        raise FileNotFoundError(f"Dataset file not found: {csv_path}")

    df = pd.read_csv(csv_path)
    required_cols = FEATURE_COLUMNS + [TARGET_COLUMN]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"CSV is missing required columns: {missing_cols}")

    initial_len = len(df)
    df = df[df[TARGET_COLUMN].isin(VALID_DIRECTIONS)].copy()

    for col in FEATURE_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    finite_mask = np.isfinite(df[FEATURE_COLUMNS]).all(axis=1)
    df = df.loc[finite_mask].dropna(subset=required_cols)

    if df.empty:
        raise ValueError("No valid samples remain after filtering and cleaning.")

    class_counts = df[TARGET_COLUMN].value_counts()
    min_count = int(class_counts.min())
    if min_count < CV_SPLITS:
        raise ValueError(
            f"Smallest class has {min_count} samples; at least {CV_SPLITS} are required for {CV_SPLITS}-fold CV."
        )

    print(f"Loaded {len(df)}/{initial_len} valid samples from {csv_path}")
    print("Class distribution:")
    for label, count in class_counts.items():
        pct = (count / len(df)) * 100.0
        print(f"  {label:<15} {count:5d} ({pct:5.1f}%)")

    return df


def build_classifier(n_estimators: int, max_depth: int) -> RandomForestClassifier:
    """Construct a Random Forest classifier with standard hyperparameters."""
    return RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_split=4,
        min_samples_leaf=2,
        class_weight="balanced",
        n_jobs=-1,
    )


def train_model(
    df: pd.DataFrame,
    n_estimators: int = 150,
    max_depth: int = 12,
    test_size: float = 0.20,
) -> dict[str, Any]:
    """Evaluate via CV and held-out split, then refit on the full dataset."""
    X = df[FEATURE_COLUMNS]
    y = df[TARGET_COLUMN]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=test_size,
        stratify=y,
    )
    print(f"\nSplit: {len(X_train)} train, {len(X_test)} test")

    clf = build_classifier(n_estimators=n_estimators, max_depth=max_depth)

    skf = StratifiedKFold(n_splits=CV_SPLITS, shuffle=True)
    cv_results = cross_validate(
        clf,
        X_train,
        y_train,
        cv=skf,
        scoring=["accuracy", "f1_macro"],
    )
    cv_acc = cv_results["test_accuracy"]
    cv_f1 = cv_results["test_f1_macro"]
    print(
        f"{CV_SPLITS}-fold CV: "
        f"accuracy={cv_acc.mean():.4f} (+/- {cv_acc.std():.4f}), "
        f"f1_macro={cv_f1.mean():.4f} (+/- {cv_f1.std():.4f})"
    )

    t0 = time.perf_counter()
    clf.fit(X_train, y_train)
    fit_time = time.perf_counter() - t0
    print(f"Train fit completed in {fit_time:.2f}s")

    y_pred = clf.predict(X_test)
    test_acc = float(accuracy_score(y_test, y_pred))
    test_f1 = float(f1_score(y_test, y_pred, average="macro"))

    print(f"\nTest evaluation (accuracy={test_acc:.4f}, f1_macro={test_f1:.4f}):")
    print(classification_report(y_test, y_pred, digits=4))

    cm = confusion_matrix(y_test, y_pred, labels=clf.classes_)
    cm_df = pd.DataFrame(
        cm,
        index=[f"True {c}" for c in clf.classes_],
        columns=[f"Pred {c}" for c in clf.classes_],
    )
    print("Confusion matrix:")
    print(cm_df.to_string())

    print("\nFeature importances:")
    for name, imp in sorted(
        zip(FEATURE_COLUMNS, clf.feature_importances_),
        key=lambda item: item[1],
        reverse=True,
    ):
        print(f"  {name:<16} {imp:.4f}")

    final_clf = build_classifier(n_estimators=n_estimators, max_depth=max_depth)
    final_clf.fit(X, y)

    return {
        "model": final_clf,
        "feature_names": FEATURE_COLUMNS,
        "classes": list(final_clf.classes_),
        "metrics": {
            "test_accuracy": test_acc,
            "test_f1_macro": test_f1,
            "cv_accuracy_mean": float(cv_acc.mean()),
            "cv_f1_mean": float(cv_f1.mean()),
        },
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": len(df),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train Random Forest autonomous driving classifier for ESP32 RC Car."
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("track_data.csv"),
        help="Path to training CSV file (default: track_data.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("pilot_model.pkl"),
        help="Destination path for trained model artifact (default: pilot_model.pkl)",
    )
    parser.add_argument(
        "--n-estimators",
        type=int,
        default=150,
        help="Number of decision trees in random forest (default: 150)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=12,
        help="Maximum depth of trees (default: 12)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        df = load_and_preprocess_data(args.data)
        artifact = train_model(
            df=df,
            n_estimators=args.n_estimators,
            max_depth=args.max_depth,
        )
        joblib.dump(artifact, args.output)
        print(
            f"\nSaved model artifact to {args.output} (classes: {artifact['classes']})"
        )
    except Exception as exc:
        print(f"Training failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
