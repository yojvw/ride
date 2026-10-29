"""Figures for the handoff package. Every figure is written to PNG and reused by the notebook."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import core

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 120
plt.rcParams["savefig.dpi"] = 150
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.25
plt.rcParams["axes.spines.top"] = False
plt.rcParams["axes.spines.right"] = False


def _save(fig, out_dir: Path, name: str) -> Path:
    path = Path(out_dir) / name
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def fig_daily(data: core.Data, out_dir: Path) -> Path:
    daily = core.daily_series(data)
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(daily.date, daily.rides, marker="o", markersize=2.5, linewidth=1.2)
    ax.set_title("每日观测骑行量（按借出时间，2024-01）")
    ax.set_ylabel("骑行次数")
    ax.set_xlabel("日期")
    fig.autofmt_xdate()
    return _save(fig, out_dir, "fig01_daily_trips.png")


def fig_hourly(data: core.Data, out_dir: Path) -> Path:
    table = core.hourly_tables(data)["table"]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.plot(table.hour, table.weekday_mean, marker="o", markersize=3, label="工作日（日均）")
    ax.plot(table.hour, table.weekend_mean, marker="s", markersize=3, label="周末（日均）")
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlabel("小时（本地时间）")
    ax.set_ylabel("每小时骑行次数（日均）")
    ax.set_title("工作日双峰与周末午后单峰")
    ax.legend()
    return _save(fig, out_dir, "fig02_hourly_profile.png")


def fig_heatmap(data: core.Data, out_dir: Path) -> Path:
    matrix = core.weekday_hour_matrix(data)
    fig, ax = plt.subplots(figsize=(10, 3.4))
    im = ax.imshow(matrix.to_numpy(), aspect="auto", cmap="YlGnBu")
    ax.set_yticks(range(len(matrix.index)),
                  ["周一", "周二", "周三", "周四", "周五", "周六", "周日"])
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlabel("小时")
    ax.set_title("星期 × 小时的平均骑行量（每个格子是该星期几该钟点的日均次数）")
    fig.colorbar(im, ax=ax, label="次数")
    return _save(fig, out_dir, "fig03_weekday_hour_heatmap.png")


def fig_member_bike(data: core.Data, out_dir: Path) -> Path:
    tables = core.member_bike_tables(data)
    member = tables["member"].set_index("member_type")
    bike = tables["bike"].set_index("bike_type")
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    labels = ["member", "casual"]
    values = [member.loc[x, "rides"] for x in labels]
    total = sum(values)
    axes[0].bar(labels, values, color=["#2b6cb0", "#dd6b20"])
    for i, v in enumerate(values):
        axes[0].text(i, v, f"{v:,}\n{v / total:.1%}", ha="center", va="bottom", fontsize=9)
    axes[0].set_title("会员类型构成（全量订单）")
    axes[0].set_ylabel("骑行次数")
    names = ["member", "casual", "classic", "electric"]
    medians = [member.loc["member", "median_duration_min"], member.loc["casual", "median_duration_min"],
               bike.loc["classic", "median_duration_min"], bike.loc["electric", "median_duration_min"]]
    means = [member.loc["member", "mean_duration_min"], member.loc["casual", "mean_duration_min"],
             bike.loc["classic", "mean_duration_min"], bike.loc["electric", "mean_duration_min"]]
    positions = np.arange(len(names))
    axes[1].bar(positions - 0.2, medians, width=0.4, label="中位数", color="#2b6cb0")
    axes[1].bar(positions + 0.2, means, width=0.4, label="均值", color="#dd6b20")
    axes[1].set_xticks(positions, names, rotation=15)
    axes[1].set_ylabel("骑行时长（分钟）")
    axes[1].set_title("时长分布：casual 与 classic 更长")
    axes[1].legend(fontsize=8)
    return _save(fig, out_dir, "fig04_member_bike.png")


def fig_station_scatter(data: core.Data, tide: pd.DataFrame, out_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    ax.scatter(tide.events, tide.net, s=12, alpha=0.55,
               c=np.where(tide.reversal, "#2b6cb0", "#a0aec0"))
    ax.axhline(0, color="black", linewidth=0.8)
    for label_row in [tide.loc[tide.events.idxmax()], tide.loc[tide.net.idxmax()],
                      tide.loc[tide.net.idxmin()]]:
        ax.annotate(label_row.station_id, (label_row.events, label_row.net), fontsize=8)
    ax.set_xlabel("站点事件量（借出 + 归还）")
    ax.set_ylabel("净流量（借出 − 归还）")
    ax.set_title("站点规模与净流量：热门站点大多接近 0，净流出集中在中等规模站点")
    return _save(fig, out_dir, "fig05_station_scatter.png")


def fig_tide(data: core.Data, tide: pd.DataFrame, out_dir: Path) -> Path:
    big = tide[tide.events >= 200]
    fig, ax = plt.subplots(figsize=(6.6, 5.2))
    ax.scatter(big.am_net, big.pm_net, s=np.clip(big.events / 30, 6, 120), alpha=0.5, color="#2b6cb0")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("上午 06–09 时平均净流出（每小时）")
    ax.set_ylabel("下午 16–19 时平均净流出（每小时）")
    ax.set_title(f"站点潮汐：{int(big.reversal.sum())}/{len(big)} 个站点早晚方向相反")
    return _save(fig, out_dir, "fig06_tide_scatter.png")


def fig_cumulative(data: core.Data, reps: list, day: str, out_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9, 4.2))
    colors = ["#2b6cb0", "#c53030", "#2f855a", "#805ad5", "#b7791f"]
    for color, rep in zip(colors, reps):
        frame = core.cumulative_flow(data, rep["station_id"], day)
        ax.plot(frame.time, frame.cumulative_net, label=rep["station_id"], color=color)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("小时")
    ax.set_ylabel("累计净流出（借出 − 归还）")
    ax.set_title(f"代表站点的日内累计净流量（{day}，单日示例，不代表全部日期）")
    ax.legend(ncol=5, fontsize=8)
    fig.autofmt_xdate()
    return _save(fig, out_dir, "fig07_representative_cumulative.png")


def fig_prediction_models(data: core.Data, metrics: pd.DataFrame, out_dir: Path) -> Path:
    test = metrics[metrics.split == "test"].copy()
    targets = ["departures", "arrivals"]
    models = ["hgb_full", "hgb_own_history", "hgb_calendar", "historical_mean", "previous_day"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.8), sharey=False)
    for ax, target in zip(axes, targets):
        sub = test[test.target == target].set_index("model").loc[models]
        ax.barh(sub.index, sub.mae, color="#2b6cb0")
        for i, (name, row) in enumerate(sub.iterrows()):
            ax.text(row.mae, i, f" {row.mae:.4f}", va="center", fontsize=8)
        ax.set_title(f"{target}：测试集 MAE（越小越好）")
        ax.set_xlabel("MAE（辆/站·小时）")
        ax.invert_yaxis()
    return _save(fig, out_dir, "fig08_prediction_models.png")


def fig_prediction_hourly(data: core.Data, out_dir: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.8))
    for ax, target in zip(axes, ["departures", "arrivals"]):
        frame = data.predictions
        frame = frame[(frame.split == "test") & (frame.model == "hgb_full") & (frame.target == target)].copy()
        frame["hour"] = frame.time.dt.hour
        frame["error"] = frame.prediction - frame.actual
        grouped = frame.groupby("hour").error.agg(mae=lambda s: s.abs().mean(), bias="mean")
        ax.bar(grouped.index, grouped.mae, color="#cbd5e0", label="MAE")
        ax.plot(grouped.index, grouped.bias, color="#c53030", marker="o", markersize=3, label="偏差（预测−实际）")
        ax.set_xticks(range(0, 24, 2))
        ax.set_xlabel("小时")
        ax.set_title(f"{target}：分小时误差（测试期）")
        ax.legend(fontsize=8)
    axes[0].set_ylabel("辆/站·小时")
    return _save(fig, out_dir, "fig09_prediction_hourly.png")


def fig_candidates(tables: dict, cfg: dict, out_dir: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    for ax, exp in zip(axes, cfg["experiments"]):
        metrics = tables[exp["run_id"]]["metrics"]
        names = sorted(metrics.model.unique())
        targets = ["departures", "arrivals"]
        base = metrics[metrics.model == "hgb_full"].set_index("target").mae
        width = 0.38
        positions = np.arange(len(names))
        for offset, target in zip([-width / 2, width / 2], targets):
            sub = metrics[metrics.target == target].set_index("model").reindex(names)
            gains = 1 - sub.mae / base[target]
            ax.bar(positions + offset, gains * 100, width=width, label=target)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xticks(positions)
        ax.set_xticklabels(names, rotation=25, ha="right", fontsize=8)
        ax.set_ylabel("验证集 MAE 相对基线（%）")
        ax.set_title(f"{exp['run_id']}（{exp['label']}，仅验证集）")
        ax.legend(fontsize=8)
    return _save(fig, out_dir, "fig10_candidate_validation.png")


def fig_prediction_example(data: core.Data, station_id: str, out_dir: Path) -> Path:
    frame = data.predictions
    sub = frame[(frame.split == "test") & (frame.model == "hgb_full") &
                (frame.target == "departures") & (frame.station_id == station_id)].sort_values("time").head(72)
    fig, ax = plt.subplots(figsize=(10.5, 3.8))
    ax.plot(sub.time, sub.actual, label="实际", linewidth=1.1)
    ax.plot(sub.time, sub.prediction, label="预测", linewidth=1.1)
    if sub.lower.notna().any():
        ax.fill_between(sub.time, sub.lower, sub.upper, alpha=0.2, label="名义 90% 区间")
    ax.set_title(f"预测示例：站点 {station_id} 借出量，测试期前 72 小时")
    ax.set_ylabel("借出次数/小时")
    ax.legend(fontsize=8)
    fig.autofmt_xdate()
    return _save(fig, out_dir, "fig11_prediction_example.png")


def render_all(data: core.Data, tide: pd.DataFrame, metrics: pd.DataFrame, tables: dict,
               reps: list, cfg: dict, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "fig01_daily_trips": fig_daily(data, out_dir),
        "fig02_hourly_profile": fig_hourly(data, out_dir),
        "fig03_weekday_hour_heatmap": fig_heatmap(data, out_dir),
        "fig04_member_bike": fig_member_bike(data, out_dir),
        "fig05_station_scatter": fig_station_scatter(data, tide, out_dir),
        "fig06_tide_scatter": fig_tide(data, tide, out_dir),
        "fig07_representative_cumulative": fig_cumulative(data, reps, cfg["representative_day"], out_dir),
        "fig08_prediction_models": fig_prediction_models(data, metrics, out_dir),
        "fig09_prediction_hourly": fig_prediction_hourly(data, out_dir),
        "fig10_candidate_validation": fig_candidates(tables, cfg, out_dir),
        "fig11_prediction_example": fig_prediction_example(data, reps[0]["station_id"], out_dir),
    }
    return paths
