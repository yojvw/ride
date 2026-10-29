#!/usr/bin/env python3
"""Round-2 ablation for the shared-bike optimization package (v0.2.1 experiments).

Eight pre-registered candidates, no cross-combination:

  A. feature reduction - base features plus exactly ONE added feature pair
     (the same statistic for departures and arrivals):
       feat_mean168        departures/arrivals mean of the past 168 hours
       feat_ewm72          departures/arrivals 72 h half-life exponential mean
       feat_same_hour_7d   departures/arrivals mean of the same clock hour over the past 7 days

  B. regularization - base features, only the tree shape changes:
       reg_leaf8_min15, reg_leaf15_min30, reg_leaf8_min30

  C. online error correction on the baseline prediction, per station and target,
     state reset at the start of every fold, predict-then-update, error = actual - base
     prediction, halflife 24 h, coefficients 0.25 and 0.50, clipped at zero:
       online_ema_025, online_ema_050

Protocol: identical splits, stations and evaluation rows as v0.2.0; only rolling CV and
the validation window are scored; the test window is never read. The original project
validation code, tests, and the v0.2.0 package modules are NOT modified.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bike_optimization.engine import Adapter, compare_reference, config_read, resolve, save_json
from bike_optimization.features import common_rows
from bike_optimization.metrics import choose, summarize
from bike_optimization.state import append_ledger

TARGETS = ("departures", "arrivals")
BASE_PARAMS = {"max_iter": 80, "max_leaf_nodes": 15, "min_samples_leaf": 15,
               "l2_regularization": 1.0, "learning_rate": 0.1}


def design(frame: pd.DataFrame, cols):
    return pd.concat(
        [frame[cols], pd.get_dummies(frame.station_id.astype(str), prefix="station", dtype=float)],
        axis=1,
    )


def fit_poisson(train, target, cols, params, seed):
    """Fit a Poisson-loss HGB on the given columns and return a predict(frame) callable."""
    x = design(train, cols)
    y = train[target].to_numpy(float)
    model = HistGradientBoostingRegressor(
        loss="poisson",
        max_iter=int(params["max_iter"]),
        max_leaf_nodes=int(params["max_leaf_nodes"]),
        min_samples_leaf=int(params["min_samples_leaf"]),
        l2_regularization=float(params.get("l2_regularization", 1.0)),
        learning_rate=float(params.get("learning_rate", 0.1)),
        early_stopping=False,
        random_state=seed,
    )
    with threadpool_limits(limits=1):
        model.fit(x, y)

    def predict(frame):
        z = design(frame, cols).reindex(columns=list(x.columns), fill_value=0)
        with threadpool_limits(limits=1):
            return np.maximum(0.0, model.predict(z))

    return predict


def online_corrected(test, target, base, coefficient, half_life_hours):
    """base + coefficient * EWM(actual - base); strictly past errors, per station, reset each fold."""
    base = np.asarray(base, dtype=float)
    frame = pd.DataFrame(
        {
            "station_id": test["station_id"].to_numpy(),
            "time": test["time"].to_numpy(),
            "base": base,
            "error": test[target].to_numpy(float) - base,
        },
        index=test.index,
    ).sort_values(["station_id", "time"])
    frame["ema"] = (
        frame.groupby("station_id")["error"]
        .transform(lambda s: s.shift(1).ewm(halflife=half_life_hours, adjust=False, min_periods=1).mean())
        .fillna(0.0)
    )
    corrected = np.maximum(0.0, frame["base"].to_numpy() + coefficient * frame["ema"].to_numpy())
    return pd.Series(corrected, index=frame.index).reindex(test.index).to_numpy(dtype=float)


def fold_splits(hostcfg):
    a = pd.Timestamp(hostcfg["train_end"])
    b = pd.Timestamp(hostcfg["validation_end"])
    folds = int(hostcfg.get("rolling_folds", 2))
    days = int(hostcfg.get("rolling_validation_days", 2))
    out = []
    for i in range(folds):
        end = a - pd.Timedelta(days=days * (folds - 1 - i))
        out.append((f"cv_{i + 1}", end - pd.Timedelta(days=days), end))
    out.append(("validation", a, b))
    return out


def split_predictions(adapter, features, protocol, split, start, end, seed):
    rows = []
    base_params = {**BASE_PARAMS, "max_iter": int(protocol.get("baseline_max_iter", 80))}
    for target in TARGETS:
        eligible = common_rows(features, target, adapter.original_columns)
        train = eligible[eligible.time < start]
        test = eligible[(eligible.time >= start) & (eligible.time < end)]
        if len(train) < adapter.hostcfg.get("min_training_rows", 100) or test.empty:
            raise ValueError(f"Too few samples for {split}/{target}: train={len(train)} test={len(test)}")
        expected = protocol.get("expected_rows", {}).get(split)
        if expected is not None and len(test) != int(expected):
            raise AssertionError(f"{split}/{target} rows {len(test)} != frozen {expected}")

        base_predict = adapter.baseline_fit(train, target).predict(test)
        peak = train.groupby("station_id")[target].quantile(0.9)

        def add(name, values):
            piece = test[["station_id", "time", target]].rename(columns={target: "actual"}).copy()
            piece["prediction"] = np.asarray(values, dtype=float)
            piece["model"] = name
            piece["target"] = target
            piece["split"] = split
            piece["peak_threshold"] = piece.station_id.map(peak)
            rows.append(piece)

        add("hgb_full", base_predict)
        for cand in protocol["candidates"]:
            kind = cand["kind"]
            if kind == "features":
                cols = list(adapter.original_columns) + list(cand["add"])
                missing = [c for c in cand["add"] if c not in features.columns]
                if missing:
                    raise KeyError(f"Missing feature columns: {missing}")
                values = fit_poisson(train, target, cols, base_params, seed)(test)
            elif kind == "params":
                params = {**base_params, **cand["params"]}
                values = fit_poisson(train, target, list(adapter.original_columns), params, seed)(test)
            elif kind == "online":
                values = online_corrected(test, target, base_predict, float(cand["coefficient"]),
                                          float(cand["half_life_hours"]))
            else:
                raise ValueError(f"Unknown candidate kind: {kind}")
            add(cand["name"], values)
    return pd.concat(rows, ignore_index=True)


def figure(summary, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    val = summary[summary.split == "validation"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    for ax, target in zip(axes, TARGETS):
        g = val[val.target == target].sort_values("mae")
        ax.barh(g.model, g.mae)
        ax.set_title(target)
        ax.set_xlabel("validation MAE")
        for i, (name, mae) in enumerate(zip(g.model, g.mae)):
            ax.text(mae, i, f" {mae:.4f}", va="center", fontsize=8)
    fig.suptitle("v0.2.1 ablation | rolling one-hour-ahead, NOT day-ahead")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Round-2 ablation: features / regularization / online correction.")
    parser.add_argument("--config", default=str(ROOT / "configs" / "optimization_v021.json"))
    parser.add_argument("--project-root", default=str(ROOT))
    args = parser.parse_args(argv)

    root = Path(args.project_root).resolve()
    protocol = config_read(args.config)
    run_id = protocol["run_id"]
    out = resolve(root, protocol.get("ledger_dir", "experiments")) / run_id
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite existing run directory: {out}")
    out.mkdir(parents=True)
    ledger = resolve(root, protocol.get("ledger_dir", "experiments"))
    append_ledger(ledger, {"run_id": run_id, "phase": "ablation", "status": "started",
                           "details": "8 pre-registered candidates; CV + validation only"})

    adapter = Adapter(root, protocol)
    features, extra = adapter.frame(False)
    if not (features.time < pd.Timestamp(adapter.hostcfg["validation_end"])).all():
        raise AssertionError("Test rows entered the ablation features")

    pieces = []
    folds = fold_splits(adapter.hostcfg)
    for split, start, end in folds:
        pieces.append(split_predictions(adapter, features, protocol, split, start, end,
                                        int(protocol.get("seed", 42))))
    pred = pd.concat(pieces, ignore_index=True)
    if (pred.time >= pd.Timestamp(adapter.hostcfg["validation_end"])).any():
        raise AssertionError("Test labels leaked into ablation output")

    reproduction = compare_reference(adapter, pred)
    summary = summarize(pred)
    chosen, paired, decisions = choose(pred, summary, protocol)

    pred.to_csv(out / "predictions.csv", index=False)
    summary.to_csv(out / "metrics.csv", index=False)
    paired.to_csv(out / "paired_bootstrap.csv", index=False)
    decisions.to_csv(out / "selection_decisions.csv", index=False)
    save_json(reproduction, out / "baseline_reproduction.json")
    save_json({"run_id": run_id, "protocol": protocol,
               "folds": [{"split": s, "start": str(a), "end": str(b)} for s, a, b in folds],
               "baseline_columns": list(adapter.original_columns),
               "extra_feature_pool": list(extra)}, out / "protocol_snapshot.json")
    save_json({"python": platform.python_version(),
               "packages": adapter.meta["packages"],
               "inputs": adapter.meta["inputs"],
               "source": adapter.meta["source"],
               "rows": {f"{k[0]}/{k[1]}": int(v) for k, v in pred.groupby(["split", "target"]).size().items()}},
              out / "environment.json")

    val = summary[summary.split == "validation"].copy()
    base = val[val.model == "hgb_full"].set_index("target")["mae"]
    val["relative_gain"] = val.apply(lambda r: 1 - r.mae / base[r.target], axis=1)
    cv = summary[summary.split.str.startswith("cv_")].copy()
    cv_mean = (cv.groupby(["target", "model"])
                 .apply(lambda g: np.average(g.mae, weights=g.n), include_groups=False)
                 .rename("cv_weighted_mae").reset_index())
    cv_base = cv_mean[cv_mean.model == "hgb_full"].set_index("target")["cv_weighted_mae"]
    cv_mean["cv_gain"] = cv_mean.apply(lambda r: 1 - r.cv_weighted_mae / cv_base[r.target], axis=1)

    figure(summary, out / "validation_comparison.png")

    lines = ["# v0.2.1 对照实验：特征精简 / 正则化 / 在线误差修正", "",
             f"run_id：{run_id}　候选：8 个（不交叉组合）", "",
             "测试集未评分；所有候选只在此前的滚动 CV 与验证窗上比较，样本掩码与原 `hgb_full` 完全一致。", ""]
    lines += ["## 1. 基线复现", "",
              f"- 状态：{reproduction.get('status')}",
              f"- 验证期逐样本最大差：{reproduction.get('max_absolute_prediction_delta')}（n={reproduction.get('n')}）", ""]
    lines += ["## 2. 验证集结果（每目标 2,880 行）", "",
              "| 目标 | 模型 | MAE | 相对基线 | RMSE | 偏差 | 峰值 MAE | 峰值欠预测率 |",
              "|---|---|---:|---:|---:|---:|---:|---:|"]
    for target in TARGETS:
        for r in val[val.target == target].sort_values("mae").itertuples():
            mark = " **(保留)**" if r.model == "hgb_full" else ""
            lines.append(f"| {target} | {r.model}{mark} | {r.mae:.4f} | {r.relative_gain * 100:+.2f}% | "
                         f"{r.rmse:.4f} | {r.bias:+.3f} | {r.peak_mae:.4f} | {r.peak_underprediction_rate:.4f} |")
    lines += ["", "## 3. 滚动 CV（两折加权 MAE）", "",
              "| 目标 | 模型 | CV 加权 MAE | 相对基线 |", "|---|---|---:|---:|"]
    for target in TARGETS:
        for r in cv_mean[cv_mean.target == target].sort_values("cv_weighted_mae").itertuples():
            lines.append(f"| {target} | {r.model} | {r.cv_weighted_mae:.4f} | {r.cv_gain * 100:+.2f}% |")
    lines += ["", "## 4. 配对日块 bootstrap（候选 − 基线，负数=更好，6 个日块）", "",
              "| 目标 | 模型 | 差值 | 95% 区间 | 上界<0 |", "|---|---|---:|---|---|"]
    for r in paired.sort_values(["target", "mae_difference"]).itertuples():
        lines.append(f"| {r.target} | {r.model} | {r.mae_difference:+.4f} | "
                     f"[{r.ci_low:+.4f}, {r.ci_high:+.4f}] | {'是' if r.ci_high < 0 else '否'} |")
    lines += ["", "## 5. 选择结论", "",
              f"- 借出：{chosen['departures']}　归还：{chosen['arrivals']}", ""]
    lines += ["## 6. 门槛判定（每候选）", "",
              "| 目标 | 模型 | 相对增益 | CV 不退化 | 峰值不恶化 | 区间上界<0 | 入选 |",
              "|---|---|---:|---|---|---|---|"]
    for r in decisions.itertuples():
        lines.append(f"| {r.target} | {r.model} | {r.relative_validation_gain * 100:+.2f}% | "
                     f"{'是' if r.cv_ok else '否'} | {'是' if r.peak_ok else '否'} | "
                     f"{'是' if r.ci_ok else '否'} | {'是' if r.eligible else '否'} |")
    lines += ["", "## 7. 口径说明", "",
              "- 特征类候选只改“新增哪一对统计量”，其余与原模型一致；特征全部由 shift(1) 之后的过去值计算。",
              "- 正则化类候选只改 (max_leaf_nodes, min_samples_leaf)，其余超参与原模型相同。",
              "- 在线修正候选：每折独立、按站点与目标维护 EWM(实际−原预测)，半衰期 24 h，先预测后更新，修正值下限 0；",
              "  其信息集与 1 小时滚动预测一致（第 t 小时只用到 t−1 及更早的实际值）。",
              "- 同一验证集已被反复使用，选择后区间未做多重比较校正；只能作为保守筛选依据。",
              "- 测试期（1/25–2/1）从头到尾没有被评分，测试预算未消耗。"]

    (out / "ABLATION_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    append_ledger(ledger, {"run_id": run_id, "phase": "ablation", "status": "completed",
                           "details": json.dumps(chosen)})
    print(json.dumps({"run_id": run_id, "chosen": chosen, "test_scored": False,
                      "directory": str(out)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
