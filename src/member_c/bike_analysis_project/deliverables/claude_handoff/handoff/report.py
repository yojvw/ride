"""JSON summary and documentation writers for the handoff package."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import core

TARGETS = ("departures", "arrivals")


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if value is pd.NaT:
        return None
    return value


def records(frame: pd.DataFrame) -> list:
    return jsonable(frame.replace({np.nan: None}).to_dict(orient="records"))


def build_summary(cfg: dict, data: core.Data, tide: pd.DataFrame, metrics: pd.DataFrame,
                  hourly: dict, tables: dict, rounds: list, reps: list, dispatch: pd.DataFrame,
                  findings: list, figures: dict, checks: dict) -> dict:
    daily = core.daily_series(data)
    member = core.member_bike_tables(data)
    stations = core.station_totals(data)
    profiles = core.panel_profiles(data)
    by_hour = core.prediction_hourly(data, "hgb_full", "test")
    panel_stations = set(data.panel.station_id.unique())
    curve_ids = [r["station_id"] for r in reps if r["station_id"] in panel_stations][:3]
    if len(curve_ids) < 3:
        ranked = core.station_totals(data).sort_values("events", ascending=False).station_id
        for station_id in ranked:
            if station_id in panel_stations and station_id not in curve_ids:
                curve_ids.append(station_id)
            if len(curve_ids) == 3:
                break
    curves = core.prediction_curves(data, curve_ids, hours=72)
    stations = stations.merge(
        tide[["station_id", "am_net", "pm_net", "reversal", "amplitude"]], on="station_id", how="left")
    stations["in_panel"] = stations.station_id.isin(panel_stations)
    big = tide[tide.events >= 200]
    overview = {
        "total_rides": int(len(data.rides)),
        "days": int(daily.shape[0]),
        "stations_with_activity": int(len(stations)),
        "avg_daily_rides": float(daily.rides.mean()),
        "max_day": {"date": str(daily.loc[daily.rides.idxmax(), "date"].date()), "rides": int(daily.rides.max())},
        "min_day": {"date": str(daily.loc[daily.rides.idxmin(), "date"].date()), "rides": int(daily.rides.min())},
        "member_share": float((data.rides.member_type == "member").mean()),
        "electric_share": float((data.rides.bike_type == "electric").mean()),
        "median_duration_min": float(data.rides.duration_min.median()),
    }
    candidate_rows = []
    for exp in cfg["experiments"]:
        frame = tables[exp["run_id"]]["metrics"]
        cv = tables[exp["run_id"]]["metrics_all"]
        cv = cv[cv.split.str.startswith("cv_")]
        cv_mean = (cv.groupby(["target", "model"])
                   .apply(lambda g: np.average(g.mae, weights=g.n), include_groups=False)
                   .rename("cv_mae").reset_index())
        base = frame[frame.model == "hgb_full"].set_index("target").mae
        cv_base = cv_mean[cv_mean.model == "hgb_full"].set_index("target").cv_mae
        for row in frame.itertuples():
            cv_value = cv_mean[(cv_mean.target == row.target) & (cv_mean.model == row.model)].cv_mae
            candidate_rows.append({
                "run_id": exp["run_id"],
                "target": row.target,
                "model": row.model,
                "is_baseline": row.model == "hgb_full",
                "validation_mae": float(row.mae),
                "validation_rmse": float(row.rmse),
                "validation_bias": float(row.bias),
                "validation_peak_mae": float(row.peak_mae),
                "validation_peak_underprediction_rate": float(row.peak_underprediction_rate),
                "relative_gain_vs_baseline": float(1 - row.mae / base[row.target]),
                "cv_mae": None if cv_value.empty else float(cv_value.iloc[0]),
                "cv_gain_vs_baseline": None if cv_value.empty else float(1 - cv_value.iloc[0] / cv_base[row.target]),
                "paired_ci_low": None if pd.isna(row.paired_ci_low) else float(row.paired_ci_low),
                "paired_ci_high": None if pd.isna(row.paired_ci_high) else float(row.paired_ci_high),
                "test_mae": None,
                "status": "validation_only",
            })
    selected = []
    for exp in cfg["experiments"]:
        for target, model in exp["chosen"].items():
            if model != "hgb_full":
                row = next(r for r in candidate_rows
                           if r["run_id"] == exp["run_id"] and r["target"] == target and r["model"] == model)
                selected.append({
                    "run_id": exp["run_id"], "target": target, "model": model,
                    "validation_mae": row["validation_mae"],
                    "baseline_validation_mae": float(row["validation_mae"] / (1 - row["relative_gain_vs_baseline"])),
                    "relative_gain_vs_baseline": row["relative_gain_vs_baseline"],
                    "paired_ci": [row["paired_ci_low"], row["paired_ci_high"]],
                    "test_mae": None,
                    "status": "validation_only_not_finalized",
                })
    summary = {
        "meta": {
            "package": cfg["package_name"],
            "version": cfg["package_version"],
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "generator": "scripts/export_all.py",
            "project": cfg["project_label"],
            "city": "Washington, DC (US Eastern)",
            "time_basis": "本地墙钟、无时区偏移的 naive 时间戳；2024-01 无夏令时切换",
            "data_version": {
                "rides_sha256": data.versions["rides_sha256"],
                "rides_rows": data.versions["rides_rows"],
                "window": [data.versions["window_start"], data.versions["window_end"]],
                "coverage_rows": data.versions["coverage_rows"],
                "coverage_assumed_rows": data.versions["coverage_assumed_rows"],
                "stations": data.versions["stations_rows"],
                "panel_rows": data.versions["panel_rows"],
                "panel_stations": data.versions["panel_stations"],
            },
            "model_version": {
                "confirmed": {
                    "model": cfg["confirmed_model"]["model"],
                    "run_id": cfg["confirmed_model"]["run_id"],
                    "status": "test_evaluated",
                    "note": cfg["confirmed_model"]["note"],
                },
                "candidates": selected,
            },
            "experiment_dirs": [{"run_id": e["run_id"], "dir": e["dir"], "status": "validation_only"}
                                 for e in cfg["experiments"]],
            "units": {"rides": "次", "duration": "分钟", "flow_hour": "次/小时", "mae": "辆/站·小时",
                      "coordinates": "WGS84 十进制度", "share": "比例（0–1）"},
        },
        "scope": {
            "definitions": records(core.scope_counts(data)),
            "warning": "全量订单、站点端点、建模面板三种口径不能互换；指标中标注了各自的口径。",
        },
        "overview": overview,
        "trends": {
            "daily": records(daily),
            "hourly": records(hourly["table"]),
            "weekday_hour_mean": jsonable(core.weekday_hour_matrix(data).round(2).to_numpy().tolist()),
            "hourly_meta": {"weekday_days": hourly["weekday_days"], "weekend_days": hourly["weekend_days"]},
        },
        "member_bike": {
            "member": records(member["member"]),
            "bike": records(member["bike"]),
            "cross": records(member["cross"]),
            "by_hour": records(member["by_hour"]),
        },
        "stations": {
            "count": int(len(stations)),
            "coordinate_note": "坐标为入桩端点坐标的稳健中位数（每站 90 分位偏差 ≤ 50.2 m）；"
                               "无站点的自由停放端点坐标仅 2 位小数，未用于站点坐标；站点容量/库存未知。",
            "list": records(stations[["station_id", "station_name", "lat", "lng", "departures", "arrivals",
                                      "net", "events", "in_panel", "am_net", "pm_net", "reversal", "amplitude"]]),
            "tide_summary": {
                "active_threshold_events": 200,
                "active_stations": int(len(big)),
                "reversal_count": int(big.reversal.sum()),
                "reversal_share": float(big.reversal.mean()),
                "corr_am_pm": float(big.am_net.corr(big.pm_net)),
                "panel_reversal_count": int(tide[tide.station_id.isin(panel_stations)].reversal.sum()),
                "panel_stations": len(panel_stations),
            },
            "profiles": records(profiles),
            "representative": jsonable(reps),
        },
        "prediction": {
            "run_id": cfg["confirmed_model"]["run_id"],
            "status": "confirmed",
            "splits": {"validation": "2024-01-19 至 2024-01-25",
                       "test": "2024-01-25 至 2024-02-01",
                       "cv_1": "2024-01-15 至 2024-01-17", "cv_2": "2024-01-17 至 2024-01-19"},
            "selected_model": cfg["confirmed_model"]["model"],
            "metrics": records(metrics),
            "by_hour": records(by_hour),
            "curves": curves,
            "note": "测试期只评估过一次；曲线来自冻结的 predictions.csv，未重新训练。",
        },
        "optimization": {
            "test_budget": {"used": 1, "maximum": 3,
                            "note": "测试预算只统计本工具链；候选实验没有评分测试集"},
            "rounds": jsonable(rounds),
            "candidates": jsonable(candidate_rows),
            "selected_candidates": jsonable(selected),
            "policy": "只使用验证集与滚动 CV；候选没有任何测试成绩；未运行 finalize。",
        },
        "dispatch": {
            "items": records(dispatch),
            "caveats": [
                "净流量是借出减归还的记录差，不是真实缺车量。",
                "站点容量、实时库存、调度车容量、成本、道路可达性均未提供，建议仅为条件性优先级。",
                "未运行调度模拟；本包不提供任何模拟收益数字。",
            ],
        },
        "findings": jsonable(findings),
        "limitations": jsonable(LIMITATIONS),
        "metrics_catalog": METRICS_CATALOG,
        "figures": [{"name": k, "file": f"figures/{Path(v).name}", **FIGURE_CATALOG.get(k, {})}
                    for k, v in figures.items()],
        "acceptance": jsonable(checks),
    }
    return jsonable(summary)


LIMITATIONS = [
    {"id": "L1", "title": "站点覆盖是假设而非证实",
     "text": "coverage.csv 的 985 段区间全部为 assumed，没有运营日志或站点状态源。站点中途开关会在边界处失真。"},
    {"id": "L2", "title": "站外端点不计入站点流量",
     "text": "15.6% 的骑行没有起点站、16.6% 没有终点站（几乎都是电动车自由停放）。站点借还只是“有站点记录”的部分。"},
    {"id": "L3", "title": "只有单月数据",
     "text": "2024-01 一个月无法证明季节性、年度规律或其他城市可迁移；所有结论限定在该月与 761 个站点。"},
    {"id": "L4", "title": "验证期只有 6 天、测试期只有 7 天",
     "text": "验证 2,880 行/目标、测试 3,360 行/目标；1% 级别的 MAE 差异在日块 bootstrap 下无法判定。"},
    {"id": "L5", "title": "测试期已经被查看过",
     "text": "测试集结果已用于诊断与报告；任何后续在测试期上的比较都只是探索性复核，不是独立盲测。"},
    {"id": "L6", "title": "候选模型没有测试成绩",
     "text": "v0.2.0 与 v0.2.1 的候选只有验证集与滚动 CV 成绩；本包不生成、不推测其测试成绩。"},
    {"id": "L7", "title": "没有库存、容量与成本数据",
     "text": "stations.csv 只有坐标；调度建议只能是条件性优先级，不能换算成缺车量、调度车次或经济收益。"},
    {"id": "L8", "title": "坐标为估计值",
     "text": "站点坐标来自入桩端点中位数；无站点端点的坐标只有约 1 km 精度，未用于站点定位。"},
]

FIGURE_CATALOG = {
    "fig01_daily_trips": {"title": "每日观测骑行量", "unit": "次/日", "status": "observed",
                          "source": "data/clean/rides.csv"},
    "fig02_hourly_profile": {"title": "工作日/周末日均小时曲线", "unit": "次/（日·小时）", "status": "observed",
                             "source": "data/clean/rides.csv"},
    "fig03_weekday_hour_heatmap": {"title": "星期×小时平均骑行量", "unit": "次/（日·小时）", "status": "observed",
                                   "source": "data/clean/rides.csv"},
    "fig04_member_bike": {"title": "会员/车型构成与时长", "unit": "次；分钟", "status": "observed",
                          "source": "data/clean/rides.csv"},
    "fig05_station_scatter": {"title": "站点事件量与净流量", "unit": "次；次（净）", "status": "observed",
                              "source": "data/clean/rides.csv"},
    "fig06_tide_scatter": {"title": "早晚净流出四象限（潮汐）", "unit": "次/小时", "status": "observed",
                           "source": "data/clean/rides.csv"},
    "fig07_representative_cumulative": {"title": "代表站点日内累计净流量", "unit": "次（累计）", "status": "observed",
                                        "source": "data/clean/rides.csv；单日 2024-01-10"},
    "fig08_prediction_models": {"title": "确认模型在测试集的 MAE 对比", "unit": "辆/站·小时", "status": "prediction",
                                "source": "results/real_run_01/tables/predictions.csv；模型 hgb_full 等 5 个"},
    "fig09_prediction_hourly": {"title": "分小时误差（测试集）", "unit": "辆/站·小时", "status": "prediction",
                                "source": "results/real_run_01/tables/predictions.csv；模型 hgb_full"},
    "fig10_candidate_validation": {"title": "两轮候选的验证集相对增益", "unit": "%（相对基线 MAE）",
                                   "status": "validation_experiment",
                                   "source": "experiments/opt_v020_001；experiments/opt_v021_001；仅验证集"},
    "fig11_prediction_example": {"title": "预测示例（31623 借出，测试前 72 小时）", "unit": "次/小时",
                                 "status": "prediction", "source": "results/real_run_01/tables/predictions.csv"},
}

METRICS_CATALOG = {
    "overview.total_rides": {"unit": "次", "time_range": "2024-01-01 至 2024-02-01", "scope": "全量订单",
                             "denominator": "无", "source": "data/clean/rides.csv", "status": "observed"},
    "overview.avg_daily_rides": {"unit": "次/日", "time_range": "2024-01-01 至 2024-02-01", "scope": "全量订单",
                                 "denominator": "31 天", "source": "data/clean/rides.csv", "status": "observed"},
    "trends.daily.rides": {"unit": "次", "time_range": "单日", "scope": "全量订单（按 started_at）",
                           "denominator": "无", "source": "data/clean/rides.csv", "status": "observed"},
    "trends.hourly.rides_all": {"unit": "次", "time_range": "全月同钟点累计", "scope": "全量订单",
                                "denominator": "无", "source": "data/clean/rides.csv", "status": "observed"},
    "trends.hourly.weekday_mean": {"unit": "次/（日·小时）", "time_range": "全月工作日", "scope": "全量订单",
                                   "denominator": "23 个工作日", "source": "data/clean/rides.csv", "status": "observed"},
    "member_bike.member.rides": {"unit": "次", "time_range": "全月", "scope": "全量订单",
                                 "denominator": "无", "source": "data/clean/rides.csv", "status": "observed"},
    "member_bike.duration": {"unit": "分钟", "time_range": "全月", "scope": "全量订单",
                             "denominator": "无", "source": "data/clean/rides.csv", "status": "observed"},
    "stations.list.departures": {"unit": "次", "time_range": "全月", "scope": "有起点的端点",
                                 "denominator": "无", "source": "data/clean/rides.csv", "status": "observed"},
    "stations.list.arrivals": {"unit": "次", "time_range": "全月", "scope": "有终点的端点（到达在窗口内）",
                               "denominator": "无", "source": "data/clean/rides.csv", "status": "observed"},
    "stations.list.net": {"unit": "次", "time_range": "全月", "scope": "该站点",
                          "denominator": "无", "source": "departures − arrivals", "status": "observed"},
    "stations.tide.am_net": {"unit": "次/小时", "time_range": "06–09 时", "scope": "该站点",
                             "denominator": "4 个小时 × 31 天", "source": "data/clean/rides.csv", "status": "observed"},
    "stations.tide.pm_net": {"unit": "次/小时", "time_range": "16–19 时", "scope": "该站点",
                             "denominator": "4 个小时 × 31 天", "source": "data/clean/rides.csv", "status": "observed"},
    "stations.profiles": {"unit": "次/小时", "time_range": "全月平均", "scope": "20 个建模站点",
                          "denominator": "该站该类型的小时数", "source": "hourly_panel.csv", "status": "observed"},
    "prediction.metrics.mae": {"unit": "辆/站·小时", "time_range": "验证 1/19–1/25；测试 1/25–2/1",
                               "scope": "20 个建模站点", "denominator": "该划分的样本行数",
                               "source": "results/real_run_01/tables/predictions.csv", "status": "prediction"},
    "prediction.by_hour.mae": {"unit": "辆/站·小时", "time_range": "测试期", "scope": "20 个建模站点",
                               "denominator": "该小时的站点数×天数",
                               "source": "results/real_run_01/tables/predictions.csv", "status": "prediction"},
    "optimization.candidates.validation_mae": {"unit": "辆/站·小时", "time_range": "验证 1/19–1/25",
                                               "scope": "20 个建模站点", "denominator": "2,880 行/目标",
                                               "source": "experiments/opt_v020_001、opt_v021_001",
                                               "status": "validation_experiment"},
    "dispatch.items.daily_net": {"unit": "次", "time_range": "全月", "scope": "该站点",
                                 "denominator": "无", "source": "data/clean/rides.csv", "status": "observed"},
}
