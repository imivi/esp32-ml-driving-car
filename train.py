#!/usr/bin/env python3
"""
train.py - Train Random Forest Classifier for Autonomous RC Car Driving

Reads distance sensor telemetry and direction labels from track_data.csv,
trains an ensemble Random Forest model to predict direction ('FORWARD',
'FORWARD_LEFT', 'FORWARD_RIGHT'), and exports the trained model to pilot_model.pkl.
"""

import os
import sys
import argparse
import time
from datetime import datetime

try:
    import pandas as pd
    import numpy as np
    import joblib
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import (
        train_test_split,
        StratifiedKFold,
        cross_val_score,
    )
    from sklearn.metrics import (
        classification_report,
        confusion_matrix,
        accuracy_score,
        f1_score,
    )
except ImportError as e:
    print(f"Error: Missing required machine learning library: {e}")
    print("Please install requirements using:")
    print("   uv add scikit-learn pandas joblib")
    print("or:")
    print("   pip install scikit-learn pandas joblib")
    sys.exit(1)


FEATURE_COLUMNS = ["dist_left_mm", "dist_center_mm", "dist_right_mm"]
TARGET_COLUMN = "direction"
VALID_DIRECTIONS = ["FORWARD", "FORWARD_LEFT", "FORWARD_RIGHT"]


def load_and_preprocess_data(csv_path: str):
    """Loads and validates track_data.csv."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Dataset file '{csv_path}' not found.")

    print(f"Loading dataset from: {csv_path}")
    df = pd.read_csv(csv_path)

    # Check required columns
    missing_cols = [
        col for col in FEATURE_COLUMNS + [TARGET_COLUMN] if col not in df.columns
    ]
    if missing_cols:
        raise ValueError(f"CSV is missing required columns: {missing_cols}")

    initial_len = len(df)

    # Filter to valid direction classes only (exclude STOP or REVERSE if present)
    df = df[df[TARGET_COLUMN].isin(VALID_DIRECTIONS)].copy()

    # Drop any NaN / infinite values
    df = df.dropna(subset=FEATURE_COLUMNS + [TARGET_COLUMN])

    print(
        f"Dataset loaded: {len(df)} valid samples (filtered from {initial_len} total rows)"
    )
    print("\nClass Distribution:")
    class_counts = df[TARGET_COLUMN].value_counts()
    for label, count in class_counts.items():
        percentage = (count / len(df)) * 100.0
        print(f"  • {label:<15}: {count:5d} ({percentage:5.1f}%)")

    return df


def train_model(
    df: pd.DataFrame,
    n_estimators: int = 150,
    max_depth: int = 12,
    test_size: float = 0.20,
    random_state: int = 42,
):
    """Trains and evaluates the Random Forest Classifier."""
    X = df[FEATURE_COLUMNS]
    y = df[TARGET_COLUMN]

    # Stratified Train/Test Split
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=random_state,
        stratify=y,
    )

    print(f"\nTraining set size: {len(X_train)} samples")
    print(f"Testing set size:  {len(X_test)} samples")

    # Initialize Random Forest with balanced class weights to account for class imbalance
    clf = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_split=4,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=random_state,
        n_jobs=-1,
    )

    # 5-Fold Stratified Cross Validation
    print("\nRunning 5-Fold Stratified Cross-Validation...")
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=random_state)
    cv_acc = cross_val_score(clf, X_train, y_train, cv=skf, scoring="accuracy")
    cv_f1 = cross_val_score(clf, X_train, y_train, cv=skf, scoring="f1_macro")
    print(f"  • CV Accuracy: {cv_acc.mean():.4f} (+/- {cv_acc.std():.4f})")
    print(f"  • CV Macro F1: {cv_f1.mean():.4f} (+/- {cv_f1.std():.4f})")

    # Fit final model on training set
    print("\nFitting final model on training set...")
    t0 = time.time()
    clf.fit(X_train, y_train)
    fit_time = time.time() - t0
    print(f"Training completed in {fit_time:.2f} seconds.")

    # Evaluate on held-out test set
    y_pred = clf.predict(X_test)
    test_acc = accuracy_score(y_test, y_pred)
    test_f1 = f1_score(y_test, y_pred, average="macro")

    print("\n" + "=" * 55)
    print(
        f" TEST SET EVALUATION (Accuracy: {test_acc * 100:.2f}%, Macro F1: {test_f1:.4f})"
    )
    print("=" * 55)
    print(classification_report(y_test, y_pred, digits=4))

    print("Confusion Matrix:")
    cm = confusion_matrix(y_test, y_pred, labels=clf.classes_)
    cm_df = pd.DataFrame(
        cm,
        index=[f"True {c}" for c in clf.classes_],
        columns=[f"Pred {c}" for c in clf.classes_],
    )
    print(cm_df.to_string())

    print("\nFeature Importances:")
    importances = sorted(
        zip(FEATURE_COLUMNS, clf.feature_importances_), key=lambda x: x[1], reverse=True
    )
    for name, imp in importances:
        bar = "█" * int(imp * 40)
        print(f"  • {name:<16}: {imp:6.3f} {bar}")

    # Retrain on full dataset for maximum deployment robustness
    print("\nRefitting model on 100% of dataset for production deployment...")
    final_clf = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_split=4,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=random_state,
        n_jobs=-1,
    )
    final_clf.fit(X, y)

    # Package model metadata
    model_artifact = {
        "model": final_clf,
        "feature_names": FEATURE_COLUMNS,
        "classes": list(final_clf.classes_),
        "metrics": {
            "test_accuracy": float(test_acc),
            "test_f1_macro": float(test_f1),
            "cv_accuracy_mean": float(cv_acc.mean()),
            "cv_f1_mean": float(cv_f1.mean()),
        },
        "trained_at": datetime.now().isoformat(),
        "n_samples": len(df),
    }

    return model_artifact


def main():
    parser = argparse.ArgumentParser(
        description="Train Random Forest autonomous driving classifier for ESP32 RC Car"
    )
    parser.add_argument(
        "--data",
        type=str,
        default="track_data.csv",
        help="Path to training CSV file (default: track_data.csv)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="pilot_model.pkl",
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
    args = parser.parse_args()

    try:
        df = load_and_preprocess_data(args.data)
        artifact = train_model(
            df=df,
            n_estimators=args.n_estimators,
            max_depth=args.max_depth,
        )

        joblib.dump(artifact, args.output)
        print(f"\nTrained model successfully saved to: '{args.output}'")
        print(f"Classes: {artifact['classes']}")
        print(f"Model ready for inference with 'autopilot.py'!\n")

    except Exception as e:
        print(f"\nTraining failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
