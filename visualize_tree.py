#!/usr/bin/env python3
"""
visualize_tree.py - Visualize Decision Tree from Trained Pilot Model

Extracts an individual decision tree estimator from pilot_model.pkl and
provides multiple visualization options:
1. High-resolution PNG/SVG/PDF rendering using matplotlib and scikit-learn plot_tree.
2. Textual hierarchy representation in terminal / text file using export_text.
3. Interactive window display.

Usage:
    python visualize_tree.py
    python visualize_tree.py --tree-index 0 --max-depth 4 --output docs/decision_tree.png
    python visualize_tree.py --text-only
"""

import os
import sys
import argparse
import joblib

try:
    import matplotlib.pyplot as plt
    from sklearn.tree import plot_tree, export_text
except ImportError as e:
    print(f"Error: Missing required library: {e}", file=sys.stderr)
    print("Run: pip install matplotlib scikit-learn", file=sys.stderr)
    sys.exit(1)


def load_model_and_tree(model_path: str, tree_index: int):
    """Loads the trained model artifact and extracts the selected decision tree estimator."""
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model file '{model_path}' not found.")

    artifact = joblib.load(model_path)

    # Support both dictionary artifact and raw classifier
    if isinstance(artifact, dict) and "model" in artifact:
        rf_model = artifact["model"]
        feature_names = artifact.get(
            "feature_names", ["dist_left_mm", "dist_center_mm", "dist_right_mm"]
        )
        classes = [str(c) for c in artifact.get("classes", rf_model.classes_)]
    else:
        rf_model = artifact
        feature_names = ["dist_left_mm", "dist_center_mm", "dist_right_mm"]
        classes = [str(c) for c in getattr(rf_model, "classes_", [])]

    if not hasattr(rf_model, "estimators_"):
        raise ValueError(
            f"The loaded model of type {type(rf_model).__name__} does not contain decision tree estimators."
        )

    num_trees = len(rf_model.estimators_)
    if tree_index < 0 or tree_index >= num_trees:
        raise IndexError(
            f"Invalid tree index {tree_index}. Forest contains {num_trees} trees (0 to {num_trees - 1})."
        )

    tree = rf_model.estimators_[tree_index]
    return tree, feature_names, classes, num_trees


def export_tree_text(tree, feature_names, max_depth: int | None = None):
    """Generates an ASCII text representation of the decision tree."""
    return export_text(
        tree,
        feature_names=feature_names,
        max_depth=max_depth,
        spacing=3,
        decimals=1,
    )


def plot_tree_image(
    tree,
    feature_names,
    classes,
    max_depth: int | None = None,
    output_path: str | None = None,
    dpi: int = 300,
    show: bool = False,
):
    """Plots and optionally saves/displays the decision tree."""
    # Set figure size proportional to depth and breadth
    effective_depth = max_depth if max_depth is not None else min(tree.get_depth(), 5)
    fig_width = max(18, effective_depth * 4)
    fig_height = max(10, effective_depth * 2.5)

    plt.figure(figsize=(fig_width, fig_height), dpi=dpi)

    plot_tree(
        tree,
        feature_names=feature_names,
        class_names=classes,
        filled=True,
        rounded=True,
        fontsize=9,
        max_depth=max_depth,
        proportion=False,
        precision=1,
    )

    title_text = f"Random Forest - Decision Tree (max_depth={max_depth if max_depth else 'full'})"
    plt.title(title_text, fontsize=16, fontweight="bold", pad=15)
    plt.tight_layout()

    if output_path:
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        plt.savefig(output_path, dpi=dpi, bbox_inches="tight")
        print(f"Tree visualization successfully saved to: {output_path}")

    if show:
        print("Displaying interactive plot window (close window to exit)...")
        plt.show()

    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Visualize a Decision Tree from the trained Random Forest model"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="pilot_model.pkl",
        help="Path to trained model file (default: pilot_model.pkl)",
    )
    parser.add_argument(
        "--tree-index",
        type=int,
        default=0,
        help="Index of the tree estimator within the random forest (default: 0)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=4,
        help="Maximum depth to display for readability (default: 4, set -1 for full depth)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="docs/decision_tree.png",
        help="Image output path (.png, .svg, .pdf) (default: docs/decision_tree.png)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Resolution in DPI for image export (default: 300)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Open an interactive matplotlib window",
    )
    parser.add_argument(
        "--text-only",
        action="store_true",
        help="Only output text/ASCII tree structure to terminal",
    )
    args = parser.parse_args()

    max_depth = None if args.max_depth < 0 else args.max_depth

    try:
        tree, feature_names, classes, num_trees = load_model_and_tree(
            args.model, args.tree_index
        )
        print(
            f"Loaded Random Forest model from '{args.model}' ({num_trees} estimators)."
        )
        print(
            f"Selected Tree #{args.tree_index}: Depth={tree.get_depth()}, Leaves={tree.get_n_leaves()}"
        )
        print(f"Features: {feature_names}")
        print(f"Classes: {classes}\n")

        # Text export / overview
        tree_text = export_tree_text(tree, feature_names, max_depth=max_depth)
        print("--- Decision Tree Structure (Text) ---")
        print(tree_text)
        print("--------------------------------------\n")

        if not args.text_only:
            plot_tree_image(
                tree=tree,
                feature_names=feature_names,
                classes=classes,
                max_depth=max_depth,
                output_path=args.output,
                dpi=args.dpi,
                show=args.show,
            )

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
