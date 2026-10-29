"""Builds bike_analysis.ipynb from markdown and code cells."""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

KERNEL = {"display_name": "Bike Handoff (venv)", "language": "python", "name": "bike-handoff"}


def _md(text: str):
    return new_markdown_cell(text.strip("\n"))


def _code(text: str):
    source = text.strip("\n")
    if "#" in source:
        raise ValueError("Code cells must not contain comments or '#' characters")
    return new_code_cell(source)


def cells() -> list:
    out = []
    out.append(_md("""
# 共享单车分析（2024-01）：数据、站点潮汐与预测评估

本 Notebook 复现课程成果包中的关键统计与图表，**不重新训练模型，也不重新评估测试集**。

- 数据：`data/clean/rides.csv`（238,699 行，2024-01-01 至 2024-02-01）
- 已确认模型：`hgb_full`（`results/real_run_01`，测试期只评估过一次）
- 候选实验：`opt_v020_001`、`opt_v021_001`（**只有验证成绩**）
- 本 Notebook 依赖原工程数据与冻结结果，不能脱离工程独立运行；所有路径由 `handoff_config.json` 统一配置。
"""))
    out.append(_md("""
## 1. 环境与数据加载

配置给出工程根目录、数据文件与实验目录；加载后先核对行数与版本。
"""))
    out.append(_code("""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display, Image, Markdown

sys.path.insert(0, str(Path.cwd()))
from handoff import core, figures

cfg = core.load_config(Path.cwd() / "handoff_config.json")
data = core.load_data(cfg)
pd.set_option("display.width", 180)
print("project root:", cfg["_root"])
print("rides:", len(data.rides))
print("coverage:", len(data.coverage))
print("panel:", len(data.panel), "rows;", data.panel.station_id.nunique(), "stations")
"""))
    out.append(_md("""
## 2. 数据与口径

三种口径不能互换：全量订单（238,699）、有站点端点的子集（201,574 / 199,070）、建模面板（20 站 × 744 小时）。
"""))
    out.append(_code("""
scope = core.scope_counts(data)
display(scope)
versions = pd.DataFrame([data.versions]).T
versions.columns = ["value"]
display(versions)
"""))
    out.append(_md("""
## 3. 清洗结果审计

保留 238,699 条、拒绝 135 条（44 条负时长、91 条零时长）。站点缺失与长时长记录被保留并打标，不删除。
"""))
    out.append(_code("""
cleaning = data.cleaning
audit = pd.DataFrame([
    {"item": "raw_rows", "value": cleaning["raw_rows"]},
    {"item": "retained_rows", "value": cleaning["retained_rows"]},
    {"item": "rejected_unique_rows", "value": cleaning["rejected_unique_rows"]},
    {"item": "exact_duplicates_removed", "value": cleaning["exact_duplicates_removed"]},
    {"item": "missing_start_station", "value": cleaning["quality_flag_counts"]["missing_start_station"]},
    {"item": "missing_end_station", "value": cleaning["quality_flag_counts"]["missing_end_station"]},
    {"item": "long_duration_ge_180min", "value": cleaning["quality_flag_counts"]["long_duration_reviewed"]},
    {"item": "duration_at_24h_cap", "value": cleaning["quality_flag_counts"]["duration_at_24h_cap"]},
])
display(audit)
display(pd.Series(cleaning["duration_summary_retained"]).to_frame("value"))
rejected = pd.read_csv(core.p(cfg, "data/clean/rejected_rows.csv"), dtype=str)
display(rejected.rejection_reason.value_counts().rename("rows").to_frame())
"""))
    out.append(_md("""
## 4. 出行规律

工作日双峰（08:00、17:00），周末单峰（14–16 时）。先看每日总量，再看工作日/周末的日均小时曲线。
"""))
    out.append(_code("""
daily = core.daily_series(data)
display(daily.head(3))
display(daily.tail(3))
figures.fig_daily(data, Path("figures"))
display(Image(filename="figures/fig01_daily_trips.png"))
"""))
    out.append(_code("""
hourly = core.hourly_tables(data)
display(hourly["table"].round(1))
print("weekday days:", hourly["weekday_days"], "weekend days:", hourly["weekend_days"])
figures.fig_hourly(data, Path("figures"))
display(Image(filename="figures/fig02_hourly_profile.png"))
"""))
    out.append(_code("""
matrix = core.weekday_hour_matrix(data)
display(matrix.round(1).loc[:, [6, 7, 8, 17, 18]])
figures.fig_heatmap(data, Path("figures"))
display(Image(filename="figures/fig03_weekday_hour_heatmap.png"))
"""))
    out.append(_md("""
会员占 74.1%，电动车占 51.1%。casual 与 classic 的骑行时长中位数更高。
"""))
    out.append(_code("""
mb = core.member_bike_tables(data)
display(mb["member"].round(3))
display(mb["bike"].round(3))
display(mb["cross"])
figures.fig_member_bike(data, Path("figures"))
display(Image(filename="figures/fig04_member_bike.png"))
"""))
    out.append(_md("""
## 5. 站点潮汐与失衡

净流量 = 借出 − 归还，是**记录差**，不是真实缺车量。站点容量与库存未知。
"""))
    out.append(_code("""
stations = core.station_totals(data)
tide = core.tide_table(data)
display(stations.head(8)[["station_id", "station_name", "departures", "arrivals", "net", "events"]])
"""))
    out.append(_code("""
top_events = set(tide.nlargest(20, "events").station_id)
top_net = set(tide.nlargest(20, "net").station_id) | set(tide.nsmallest(20, "net").station_id)
print("事件量前20 与 |净流量| 前20 的重合站点数:", len(top_events & top_net))
print("Spearman(事件量, |净流量|):", round(tide.events.corr(tide.net.abs(), method="spearman"), 3))
display(tide.nlargest(5, "net")[["station_id", "net", "events"]])
display(tide.nsmallest(5, "net")[["station_id", "net", "events"]])
"""))
    out.append(_code("""
big = tide[tide.events >= 200]
print("active stations:", len(big))
print("reversal stations:", int(big.reversal.sum()), "share:", round(big.reversal.mean(), 3))
print("corr(am_net, pm_net):", round(big.am_net.corr(big.pm_net), 3))
figures.fig_station_scatter(data, tide, Path("figures"))
display(Image(filename="figures/fig05_station_scatter.png"))
figures.fig_tide(data, tide, Path("figures"))
display(Image(filename="figures/fig06_tide_scatter.png"))
"""))
    out.append(_md("""
代表站点按固定规则选取：最大事件量、最大净流出、最大净流入、最大潮汐振幅（高流量）、中等规模且净流量接近 0 的对照站。
"""))
    out.append(_code("""
reps = core.representative_stations(data, tide)
display(pd.DataFrame(reps))
figures.fig_cumulative(data, reps, cfg["representative_day"], Path("figures"))
display(Image(filename="figures/fig07_representative_cumulative.png"))
"""))
    out.append(_md("""
## 6. 预测评估（冻结结果复核）

模型与划分都已在既有实验结果中确定：验证集选模，测试集只评估一次。这里只读取 `predictions.csv` 重新计算指标，不做训练。
"""))
    out.append(_code("""
metrics = core.prediction_metrics(data)
test = metrics[metrics.split == "test"]
display(test[["target", "model", "n", "mae", "rmse", "bias", "peak_mae",
              "peak_underprediction_rate", "interval_coverage", "improvement_vs_previous_day"]].round(4))
validation = metrics[metrics.split == "validation"]
display(validation[["target", "model", "n", "mae", "rmse", "bias"]].round(4))
figures.fig_prediction_models(data, metrics, Path("figures"))
display(Image(filename="figures/fig08_prediction_models.png"))
"""))
    out.append(_code("""
by_hour = core.prediction_hourly(data, "hgb_full", "test")
display(by_hour.round(3))
figures.fig_prediction_hourly(data, Path("figures"))
display(Image(filename="figures/fig09_prediction_hourly.png"))
figures.fig_prediction_example(data, "31623", Path("figures"))
display(Image(filename="figures/fig11_prediction_example.png"))
"""))
    out.append(_md("""
## 7. 优化实验总结（仅验证成绩）

两轮实验共 13 个新候选（v0.2.0 五个、v0.2.1 八个），只有 v0.2.1 的 `reg_leaf15_min30` 通过归还目标的预设门槛。
**候选没有任何测试成绩**，下表与 JSON 中的 `test_mae` 均为空。
"""))
    out.append(_code("""
tables = core.candidate_tables(cfg)
rounds = core.round_summary(cfg, tables)
display(pd.DataFrame(rounds))
for run_id, frame in tables.items():
    print(run_id)
    display(frame["metrics"][["target", "model", "mae", "paired_ci_low", "paired_ci_high"]].round(4))
figures.fig_candidates(tables, cfg, Path("figures"))
display(Image(filename="figures/fig10_candidate_validation.png"))
"""))
    out.append(_code("""
for run_id, frame in tables.items():
    decisions = frame["decisions"]
    eligible = decisions[decisions.eligible == True]
    print(run_id, "eligible rows:", len(eligible))
    display(eligible[["target", "model"]])
"""))
    out.append(_md("""
## 8. 调度建议（条件性）

基于站点净流量与潮汐方向给出补车/疏解优先级。没有容量、库存、成本与道路信息，不能换算成缺车量或收益。
"""))
    out.append(_code("""
dispatch = core.dispatch_table(data, tide, 8)
display(dispatch[["station_id", "station_name", "events", "daily_net", "am_net_per_hour", "pm_net_per_hour", "pattern"]].round(2))
display(dispatch[["station_id", "suggested_action", "missing_info"]])
"""))
    out.append(_md("""
## 9. 局限

覆盖区间全部为 assumed；15.6% 的骑行没有起点站；单月数据；验证 6 天、测试 7 天；测试期已经被查看过；候选没有测试成绩。
"""))
    out.append(_code("""
limits = pd.DataFrame(data.cleaning["assumptions"], columns=["assumptions"])
display(limits)
coverage = data.coverage
print("coverage rows:", len(coverage), "assumed:", int((coverage.status == "assumed").sum()))
print("no station at start:", int(data.rides.start_station_id.isna().sum()))
print("no station at end:", int(data.rides.end_station_id.isna().sum()))
"""))
    out.append(_md("""
## 10. 复现

本 Notebook 由 `scripts/export_all.py` 生成并执行；HTML 是这份已执行 Notebook 的直接导出。
重跑命令见包内 `运行说明.md`。
"""))
    return out


def build(path: Path) -> Path:
    notebook = new_notebook(cells=cells(), metadata={"kernelspec": KERNEL, "language_info": {"name": "python"}})
    nbformat.write(notebook, path)
    return path
