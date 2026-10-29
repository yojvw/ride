#!/usr/bin/env python3
"""
block_bootstrap.py - day-block bootstrap confidence intervals for forecast errors.

Why: the holdout period is only 7 days. A raw MAE difference between two models can
easily be sampling noise. This script resamples whole days (blocks) with replacement,
keeps each day's rows together, and reports a percentile interval for

  * each model's MAE, and
  * paired differences between two models on exactly the same resampled days.

Usage:
    python scripts/block_bootstrap.py --predictions results/real_run_01/tables/predictions.csv
    python scripts/block_bootstrap.py --predictions <path> --split test --reps 5000 --seed 7
    python scripts/block_bootstrap.py --predictions <path> --out experiments/bootstrap_test.csv

Input: predictions.csv produced by bikeproject (needs columns
station_id, time, actual, prediction, model, target, split).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

BASELINE_MODEL = "previous_day"


def day_block_bootstrap(mae_per_day: pd.DataFrame, reps: int, rng: np.random.Generator, alpha: float = 0.05):
    """mae_per_day: columns [day, abs_error_sum, n]. Returns (point, lo, hi)."""
    n_days = len(mae_per_day)
    sums = mae_per_day["abs_error_sum"].to_numpy(dtype=float)
    counts = mae_per_day["n"].to_numpy(dtype=float)
    draws = rng.integers(0, n_days, size=(reps, n_days))
    mae = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    point = sums.sum() / counts.sum()
    return point, float(np.quantile(mae, alpha / 2)), float(np.quantile(mae, 1 - alpha / 2))


def paired_day_bootstrap(a: pd.DataFrame, b: pd.DataFrame, reps: int, rng: np.random.Generator, alpha: float = 0.05):
    """Resample days once and evaluate both models on the same days."""
    merged = a.merge(b, on="day", suffixes=("_a", "_b"), validate="one_to_one")
    n_days = len(merged)
    draws = rng.integers(0, n_days, size=(reps, n_days))

    def mean_diff(rows):
        sa = merged["abs_error_sum_a"].to_numpy(dtype=float)[rows].sum(axis=1)
        sb = merged["abs_error_sum_b"].to_numpy(dtype=float)[rows].sum(axis=1)
        cnt = merged["n_a"].to_numpy(dtype=float)[rows].sum(axis=1)
        return (sa - sb) / cnt

    diffs = mean_diff(draws)
    point = (merged["abs_error_sum_a"].sum() - merged["abs_error_sum_b"].sum()) / merged["n_a"].sum()
    return point, float(np.quantile(diffs, alpha / 2)), float(np.quantile(diffs, 1 - alpha / 2))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Day-block bootstrap of forecast MAE.")
    parser.add_argument("--predictions", type=Path,
                        default=Path("results/real_run_01/tables/predictions.csv"))
    parser.add_argument("--split", default="test", choices=["test", "validation", "cv_1", "cv_2"])
    parser.add_argument("--reps", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--reference", default=None,
                        help="model to compare every other model against; default: the validation-selected point "
                             "estimate of the best model on this split")
    parser.add_argument("--out", type=Path, default=None, help="optional CSV path for the table")
    args = parser.parse_args(argv)

    df = pd.read_csv(args.predictions, parse_dates=["time"])
    df = df[df["split"] == args.split].copy()
    if df.empty:
        raise SystemExit(f"No rows for split={args.split}")
    df["day"] = df["time"].dt.normalize()
    df["abs_error"] = (df["prediction"] - df["actual"]).abs()

    daily = (df.groupby(["target", "model", "day"])
               .agg(abs_error_sum=("abs_error", "sum"), n=("abs_error", "size"))
               .reset_index())
    rng = np.random.default_rng(args.seed)

    rows = []
    for target, frame in daily.groupby("target"):
        models = sorted(frame["model"].unique())
        reference = args.reference or min(
            models, key=lambda m: frame.loc[frame.model == m, "abs_error_sum"].sum()
            / frame.loc[frame.model == m, "n"].sum()
        )
        for model in models:
            g = frame[frame.model == model].sort_values("day")
            point, lo, hi = day_block_bootstrap(g, args.reps, rng)
            rows.append({"target": target, "model": model, "n": int(g["n"].sum()),
                         "days": len(g), "mae": round(point, 4),
                         "ci_low": round(lo, 4), "ci_high": round(hi, 4),
                         "comparison": "reference" if model == reference else f"vs {reference}",
                         "diff": 0.0, "diff_low": np.nan, "diff_high": np.nan})
        base = frame[frame.model == reference].sort_values("day")
        for model in models:
            if model == reference:
                continue
            g = frame[frame.model == model].sort_values("day")
            diff, dlo, dhi = paired_day_bootstrap(g, base, args.reps, rng)
            row = next(r for r in rows if r["target"] == target and r["model"] == model)
            row["comparison"] = f"vs {reference}"
            row["diff"] = round(diff, 4)
            row["diff_low"] = round(dlo, 4)
            row["diff_high"] = round(dhi, 4)

    table = pd.DataFrame(rows)
    with pd.option_context("display.width", 200):
        print(table.to_string(index=False))
    print()
    print(f"split={args.split}, reps={args.reps}, day blocks={table.days.max()}, "
          f"negative diff = model has lower MAE than {args.reference or 'the best model'}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(args.out, index=False)
        print(f"written: {args.out}")


if __name__ == "__main__":
    main()
