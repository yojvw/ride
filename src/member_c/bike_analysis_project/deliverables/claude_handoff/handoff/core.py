"""Shared data access and computations for the handoff package."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PKG_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PKG_ROOT / "handoff_config.json"

TARGETS = ("departures", "arrivals")
AM_HOURS = tuple(range(6, 10))
PM_HOURS = tuple(range(16, 20))


def load_config(path: Path | str | None = None) -> dict:
    config_path = Path(path) if path else DEFAULT_CONFIG
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    root = Path(cfg["project_root"])
    if not root.is_absolute():
        root = (config_path.parent / root).resolve()
    cfg["_config_path"] = str(config_path)
    cfg["_root"] = root
    return cfg


def p(cfg: dict, rel: str) -> Path:
    path = Path(rel)
    return path if path.is_absolute() else (cfg["_root"] / path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_inputs(cfg: dict) -> dict:
    checks = {}
    for key, rel in cfg["data"].items():
        path = p(cfg, rel)
        if not path.exists():
            raise FileNotFoundError(f"Missing required input: {key} -> {path}")
        checks[key] = {"path": rel, "sha256": sha256(path), "bytes": path.stat().st_size}
    expected_rows = cfg["expected"]["rides_rows"]
    rides = pd.read_csv(p(cfg, cfg["data"]["rides"]), usecols=["ride_id"])
    if len(rides) != expected_rows:
        raise ValueError(f"rides.csv rows {len(rides)} != expected {expected_rows}")
    if checks["rides"]["sha256"] != cfg["expected"]["rides_sha256"]:
        raise ValueError("rides.csv sha256 does not match the frozen data version")
    checks["rides"]["rows"] = int(len(rides))
    for exp in cfg["experiments"]:
        exp_dir = p(cfg, exp["dir"])
        if not exp_dir.exists():
            raise FileNotFoundError(f"Missing experiment directory: {exp['run_id']} -> {exp_dir}")
        checks.setdefault("experiments", {})[exp["run_id"]] = {
            "path": exp["dir"],
            "files": sorted(x.name for x in exp_dir.iterdir() if x.is_file()),
        }
    return checks


@dataclass
class Data:
    cfg: dict
    rides: pd.DataFrame
    coverage: pd.DataFrame
    stations: pd.DataFrame
    panel: pd.DataFrame
    predictions: pd.DataFrame
    cleaning: dict
    versions: dict


def load_data(cfg: dict) -> Data:
    window_start = pd.Timestamp(cfg["analysis"]["start"])
    window_end = pd.Timestamp(cfg["analysis"]["end"])
    rides = pd.read_csv(
        p(cfg, cfg["data"]["rides"]),
        dtype={"ride_id": "string", "start_station_id": "string", "end_station_id": "string"},
        parse_dates=["started_at", "ended_at"],
    )
    rides = rides[(rides.started_at >= window_start) & (rides.started_at < window_end)].copy()
    rides["weekend"] = rides.started_at.dt.dayofweek >= 5
    coverage = pd.read_csv(p(cfg, cfg["data"]["coverage"]), dtype={"station_id": "string"})
    stations = pd.read_csv(p(cfg, cfg["data"]["stations"]), dtype={"station_id": "string"})
    panel = pd.read_csv(p(cfg, cfg["data"]["panel"]), dtype={"station_id": "string"}, parse_dates=["time"])
    predictions = pd.read_csv(
        p(cfg, cfg["data"]["predictions"]), dtype={"station_id": "string"}, parse_dates=["time"]
    )
    cleaning = json.loads(p(cfg, cfg["data"]["cleaning_report"]).read_text(encoding="utf-8"))
    versions = {
        "rides_sha256": sha256(p(cfg, cfg["data"]["rides"])),
        "rides_rows": int(len(rides)),
        "coverage_rows": int(len(coverage)),
        "coverage_assumed_rows": int((coverage.status == "assumed").sum()),
        "stations_rows": int(len(stations)),
        "panel_rows": int(len(panel)),
        "panel_stations": int(panel.station_id.nunique()),
        "prediction_rows": int(len(predictions)),
        "window_start": str(window_start),
        "window_end": str(window_end),
    }
    return Data(cfg, rides, coverage, stations, panel, predictions, cleaning, versions)


def scope_counts(data: Data) -> pd.DataFrame:
    rides = data.rides
    total = len(rides)
    start_ep = int(rides.start_station_id.notna().sum())
    end_ep = int(rides.end_station_id.notna().sum())
    end_window = int((rides.end_station_id.notna() &
                      (rides.ended_at < pd.Timestamp(data.cfg["analysis"]["end"]))).sum())
    both = int((rides.start_station_id.notna() & rides.end_station_id.notna()).sum())
    rows = [
        {"scope": "全量订单", "rows": total, "share": 1.0,
         "definition": "分析窗口内按 started_at 统计的全部有效骑行"},
        {"scope": "有起点的端点", "rows": start_ep, "share": start_ep / total,
         "definition": "start_station_id 非空，可计入站点借出"},
        {"scope": "有终点的端点（全量）", "rows": end_ep, "share": end_ep / total,
         "definition": "end_station_id 非空；包含 2 月 1 日到达的 35 条跨月订单"},
        {"scope": "到达在窗口内的终点端点", "rows": end_window, "share": end_window / total,
         "definition": "end_station_id 非空且 ended_at < 2024-02-01，可计入站点归还"},
        {"scope": "起终点都有", "rows": both, "share": both / total,
         "definition": "可同时计入借出与归还"},
        {"scope": "建模面板（20 站 × 744 h）", "rows": int(len(data.panel)), "share": np.nan,
         "definition": "仅覆盖选定 20 站的站点小时面板，与全量订单口径不同"},
    ]
    return pd.DataFrame(rows)


def daily_series(data: Data) -> pd.DataFrame:
    rides = data.rides
    daily = rides.groupby(rides.started_at.dt.floor("D")).size().rename("rides").reset_index()
    daily.columns = ["date", "rides"]
    return daily


def hourly_tables(data: Data) -> dict:
    rides = data.rides
    rides = rides.assign(hour=rides.started_at.dt.hour)
    totals = rides.groupby("hour").size().rename("rides_all").reset_index()
    weekday_days = rides.loc[~rides.weekend, "started_at"].dt.floor("D").nunique()
    weekend_days = rides.loc[rides.weekend, "started_at"].dt.floor("D").nunique()
    weekday = (rides[~rides.weekend].groupby("hour").size() / weekday_days).rename("weekday_mean").reset_index()
    weekend = (rides[rides.weekend].groupby("hour").size() / weekend_days).rename("weekend_mean").reset_index()
    table = totals.merge(weekday, on="hour", how="left").merge(weekend, on="hour", how="left")
    return {
        "table": table,
        "weekday_days": int(weekday_days),
        "weekend_days": int(weekend_days),
    }


def weekday_hour_matrix(data: Data) -> pd.DataFrame:
    rides = data.rides
    frame = rides.assign(weekday=rides.started_at.dt.dayofweek, hour=rides.started_at.dt.hour)
    counts = frame.groupby(["weekday", "hour"]).size().unstack(fill_value=0)
    days = frame.groupby(["weekday"])["started_at"].apply(lambda s: s.dt.floor("D").nunique())
    return counts.div(days, axis=0)


def member_bike_tables(data: Data) -> dict:
    rides = data.rides
    member = (rides.groupby("member_type")
              .agg(rides=("ride_id", "size"), median_duration_min=("duration_min", "median"),
                   mean_duration_min=("duration_min", "mean"),
                   p90_duration_min=("duration_min", lambda s: s.quantile(0.9)))
              .reset_index())
    member["share"] = member.rides / len(rides)
    bike = (rides.groupby("bike_type")
            .agg(rides=("ride_id", "size"), median_duration_min=("duration_min", "median"),
                 mean_duration_min=("duration_min", "mean"),
                 p90_duration_min=("duration_min", lambda s: s.quantile(0.9)))
            .reset_index())
    bike["share"] = bike.rides / len(rides)
    cross = pd.crosstab(rides.member_type, rides.bike_type).reset_index()
    hour = rides.assign(hour=rides.started_at.dt.hour)
    by_hour = (hour.groupby("hour")
               .agg(rides=("ride_id", "size"),
                    member_share=("member_type", lambda s: (s == "member").mean()),
                    electric_share=("bike_type", lambda s: (s == "electric").mean()))
               .reset_index())
    return {"member": member, "bike": bike, "cross": cross, "by_hour": by_hour}


def station_name_map(data: Data) -> dict:
    rides = data.rides
    names = {}
    for col, sid in (("start_station_name", "start_station_id"), ("end_station_name", "end_station_id")):
        sub = rides.loc[rides[sid].notna() & rides[col].notna(), [sid, col]]
        for station_id, group in sub.groupby(sid):
            names.setdefault(str(station_id), group[col].value_counts().index[0])
    return names


def station_totals(data: Data) -> pd.DataFrame:
    rides = data.rides
    end = pd.Timestamp(data.cfg["analysis"]["end"])
    departures = rides.groupby("start_station_id").size().rename("departures")
    arrivals = rides.loc[rides.ended_at < end].groupby("end_station_id").size().rename("arrivals")
    table = pd.concat([departures, arrivals], axis=1).fillna(0)
    table.index.name = "station_id"
    table = table.reset_index()
    table["station_id"] = table.station_id.astype(str)
    table["events"] = table.departures + table.arrivals
    table["net"] = table.departures - table.arrivals
    names = station_name_map(data)
    table["station_name"] = table.station_id.map(names)
    table = table.merge(data.stations, on="station_id", how="left")
    return table.sort_values("events", ascending=False).reset_index(drop=True)


def tide_table(data: Data) -> pd.DataFrame:
    rides = data.rides
    start = pd.Timestamp(data.cfg["analysis"]["start"])
    end = pd.Timestamp(data.cfg["analysis"]["end"])
    dep = rides.dropna(subset=["start_station_id"]).assign(
        station_id=lambda d: d.start_station_id.astype(str), hour=lambda d: d.started_at.dt.floor("h"))
    arr = rides[(rides.ended_at >= start) & (rides.ended_at < end)].dropna(subset=["end_station_id"]).assign(
        station_id=lambda d: d.end_station_id.astype(str), hour=lambda d: d.ended_at.dt.floor("h"))
    dep_counts = dep.groupby(["station_id", "hour"]).size().rename("departures")
    arr_counts = arr.groupby(["station_id", "hour"]).size().rename("arrivals")
    hourly = pd.concat([dep_counts, arr_counts], axis=1).fillna(0)
    hourly["net"] = hourly.departures - hourly.arrivals
    hourly["clock"] = hourly.index.get_level_values("hour").hour
    by_clock = hourly.groupby(level="station_id").apply(
        lambda g: pd.Series({
            "am_net": g.loc[g.clock.isin(AM_HOURS), "net"].mean(),
            "pm_net": g.loc[g.clock.isin(PM_HOURS), "net"].mean(),
        }), include_groups=False).reset_index()
    totals = station_totals(data)[["station_id", "station_name", "departures", "arrivals", "events", "net"]]
    table = totals.merge(by_clock, on="station_id", how="left")
    table["amplitude"] = table.am_net.abs() + table.pm_net.abs()
    table["reversal"] = np.sign(table.am_net) * np.sign(table.pm_net) < 0
    return table.sort_values("events", ascending=False).reset_index(drop=True)


def panel_profiles(data: Data) -> pd.DataFrame:
    panel = data.panel.copy()
    panel["weekend"] = panel.time.dt.dayofweek >= 5
    panel["hour"] = panel.time.dt.hour
    profiles = (panel.groupby(["station_id", "weekend", "hour"])
                .agg(departures=("departures", "mean"), arrivals=("arrivals", "mean"),
                     net=("net_outflow", "mean"))
                .reset_index())
    profiles["day_type"] = np.where(profiles.weekend, "weekend", "weekday")
    return profiles[["station_id", "day_type", "hour", "departures", "arrivals", "net"]]


def cumulative_flow(data: Data, station_id: str, day: str) -> pd.DataFrame:
    rides = data.rides
    day_start = pd.Timestamp(day)
    day_end = day_start + pd.Timedelta(days=1)
    dep = rides[(rides.start_station_id == station_id) & (rides.started_at >= day_start) & (rides.started_at < day_end)]
    arr = rides[(rides.end_station_id == station_id) & (rides.ended_at >= day_start) & (rides.ended_at < day_end)]
    steps = pd.date_range(day_start, day_end, freq="h", inclusive="left")
    dep_c = dep.groupby(dep.started_at.dt.floor("h")).size().reindex(steps, fill_value=0)
    arr_c = arr.groupby(arr.ended_at.dt.floor("h")).size().reindex(steps, fill_value=0)
    frame = pd.DataFrame({"time": steps, "departures": dep_c.to_numpy(), "arrivals": arr_c.to_numpy()})
    frame["net"] = frame.departures - frame.arrivals
    frame["cumulative_net"] = frame.net.cumsum()
    return frame


def prediction_metrics(data: Data) -> pd.DataFrame:
    predictions = data.predictions
    rows = []
    keys = ["station_id", "time"]
    for (split, target, model), group in predictions.groupby(["split", "target", "model"]):
        error = group.prediction - group.actual
        peak = (group.actual >= group.peak_threshold) & (group.actual > 0)
        record = {
            "split": split, "target": target, "model": model, "n": len(group),
            "mae": float(error.abs().mean()), "rmse": float(np.sqrt((error ** 2).mean())),
            "bias": float(error.mean()),
            "peak_mae": float(error[peak].abs().mean()) if peak.any() else np.nan,
            "peak_underprediction_rate": float((error[peak] < 0).mean()) if peak.any() else np.nan,
        }
        if "lower" in group and group.lower.notna().any():
            mask = group.lower.notna() & group.upper.notna()
            record["interval_coverage"] = float(
                ((group.loc[mask, "actual"] >= group.loc[mask, "lower"]) &
                 (group.loc[mask, "actual"] <= group.loc[mask, "upper"])).mean())
            record["interval_width"] = float((group.loc[mask, "upper"] - group.loc[mask, "lower"]).mean())
        rows.append(record)
    table = pd.DataFrame(rows)
    baseline = table[table.model == "previous_day"][["split", "target", "mae"]].rename(columns={"mae": "baseline_mae"})
    table = table.merge(baseline, on=["split", "target"], how="left")
    table["improvement_vs_previous_day"] = 1 - table.mae / table.baseline_mae
    return table


def prediction_hourly(data: Data, model: str = "hgb_full", split: str = "test") -> pd.DataFrame:
    frame = data.predictions[(data.predictions.model == model) & (data.predictions.split == split)].copy()
    frame["hour"] = frame.time.dt.hour
    frame["error"] = frame.prediction - frame.actual
    return (frame.groupby("hour")
            .agg(mae=("error", lambda s: s.abs().mean()), bias=("error", "mean"),
                 rmse=("error", lambda s: np.sqrt((s ** 2).mean())), n=("error", "size"))
            .reset_index())


def prediction_curves(data: Data, station_ids, hours: int = 72, model: str = "hgb_full", split: str = "test") -> dict:
    frame = data.predictions[(data.predictions.split == split) & (data.predictions.model == model)]
    curves = []
    for station_id in station_ids:
        for target in TARGETS:
            sub = frame[(frame.station_id == station_id) & (frame.target == target)].sort_values("time").head(hours)
            if sub.empty:
                continue
            curves.append({
                "station_id": station_id,
                "target": target,
                "model": model,
                "split": split,
                "status": "prediction",
                "points": [
                    {"time": row.time.strftime("%Y-%m-%d %H:%M"),
                     "actual": None if pd.isna(row.actual) else float(row.actual),
                     "prediction": None if pd.isna(row.prediction) else float(row.prediction),
                     "lower": None if pd.isna(getattr(row, "lower", np.nan)) else float(row.lower),
                     "upper": None if pd.isna(getattr(row, "upper", np.nan)) else float(row.upper)}
                    for row in sub.itertuples()
                ],
            })
    return curves


def candidate_tables(cfg: dict) -> dict:
    frames = {}
    for exp in cfg["experiments"]:
        exp_dir = p(cfg, exp["dir"])
        if exp["kind"] == "package_tune":
            metrics = pd.read_csv(exp_dir / "validation_cv_metrics.csv")
            pairs = pd.read_csv(exp_dir / "validation_paired_bootstrap.csv")
        else:
            metrics = pd.read_csv(exp_dir / "metrics.csv")
            pairs = pd.read_csv(exp_dir / "paired_bootstrap.csv")
        validation = metrics[metrics.split == "validation"].copy()
        pair_columns = pairs[["target", "model", "mae_difference", "ci_low", "ci_high"]].rename(
            columns={"ci_low": "paired_ci_low", "ci_high": "paired_ci_high"})
        validation = validation.merge(pair_columns, on=["target", "model"], how="left")
        decisions = pd.read_csv(exp_dir / "selection_decisions.csv")
        chosen_path = exp_dir / "OPTIMIZATION_REPORT.md"
        frames[exp["run_id"]] = {
            "metrics": validation,
            "metrics_all": metrics,
            "decisions": decisions,
            "report_exists": chosen_path.exists(),
            "dir": exp["dir"],
            "label": exp.get("label", exp["run_id"]),
        }
    return frames


def round_summary(cfg: dict, tables: dict) -> list:
    out = []
    for exp in cfg["experiments"]:
        table = tables[exp["run_id"]]
        metrics = table["metrics"]
        chosen = exp.get("chosen", {})
        out.append({
            "run_id": exp["run_id"],
            "label": exp.get("label", exp["run_id"]),
            "dir": exp["dir"],
            "candidates": int(metrics.model.nunique() - 1),
            "model_entries": int(metrics.model.nunique()),
            "status": "validation_only",
            "chosen": chosen,
            "baseline_kept_for": [t for t in TARGETS if chosen.get(t, "hgb_full") == "hgb_full"],
        })
    return out


def dispatch_table(data: Data, tide: pd.DataFrame, limit: int = 8) -> pd.DataFrame:
    candidates = tide[tide.events >= 200].copy()
    candidates["priority"] = candidates.amplitude * np.log1p(candidates.events)
    top = candidates.nlargest(limit, "priority")
    rows = []
    for row in top.itertuples():
        if row.am_net > 0 and row.pm_net < 0:
            pattern = "早高峰净流出、晚高峰净流入"
            action = "早间（约 06:30 前）优先补车；晚间（约 16:00–19:00）优先疏解"
        elif row.am_net < 0 and row.pm_net > 0:
            pattern = "早高峰净流入、晚高峰净流出"
            action = "早间优先疏解；晚间优先补车"
        elif row.net > 0:
            pattern = "全天净流出"
            action = "白天持续补车优先于单次调度"
        else:
            pattern = "全天净流入"
            action = "白天持续疏解优先于单次调度"
        rows.append({
            "station_id": row.station_id,
            "station_name": row.station_name,
            "events": int(row.events),
            "daily_net": float(row.net),
            "am_net_per_hour": float(row.am_net),
            "pm_net_per_hour": float(row.pm_net),
            "pattern": pattern,
            "suggested_action": action,
            "missing_info": "站点容量、实时库存、调度车容量与成本、道路可达性均未提供",
        })
    return pd.DataFrame(rows)


def representative_stations(data: Data, tide: pd.DataFrame, limit: int = 5) -> list:
    totals = tide
    picks = []
    busiest = totals.loc[totals.events.idxmax()]
    picks.append((str(busiest.station_id), "全网事件量最高，用于观察“热门但净流量接近 0”"))
    outflow = totals.loc[totals.net.idxmax()]
    picks.append((str(outflow.station_id), "全网净流出最高（借出显著多于归还）"))
    inflow = totals.loc[totals.net.idxmin()]
    picks.append((str(inflow.station_id), "全网净流入最高（归还显著多于借出）"))
    tidal = totals[(totals.reversal) & (totals.events >= 1000)].nlargest(1, "amplitude").iloc[0]
    picks.append((str(tidal.station_id), "潮汐振幅大且发生在高流量站点，用于观察早晚方向反转"))
    balanced = totals[(totals.events.between(800, 1400)) & (totals.net.abs() <= 10)].nlargest(1, "events").iloc[0]
    picks.append((str(balanced.station_id), "中等规模、净流量接近 0，作为对照站点"))
    seen = []
    unique = []
    for station_id, reason in picks:
        if station_id not in seen:
            seen.append(station_id)
            unique.append({"station_id": station_id, "reason": reason})
    return unique[:limit]


def build_findings(data: Data, tide: pd.DataFrame, pred_metrics: pd.DataFrame,
                   rounds: list, cand_tables: dict) -> list:
    rides = data.rides
    hourly = hourly_tables(data)["table"]
    weekday = hourly.set_index("hour")["weekday_mean"]
    weekend = hourly.set_index("hour")["weekend_mean"]
    busiest_hour = int(hourly.loc[hourly.rides_all.idxmax(), "hour"])
    weekday_peak = int(weekday.idxmax())
    weekend_peak = int(weekend.idxmax())
    big = tide[tide.events >= 200]
    reversal_share = float(big.reversal.mean())
    corr = float(big.am_net.corr(big.pm_net))
    top_volume = set(tide.nlargest(20, "events").station_id)
    top_net = set(tide.loc[tide.net.abs().nlargest(20).index, "station_id"])
    overlap = len(top_volume & top_net)
    busiest = tide.loc[tide.events.idxmax()]
    max_out = tide.loc[tide.net.idxmax()]
    max_in = tide.loc[tide.net.idxmin()]
    test = pred_metrics[(pred_metrics.split == "test") & (pred_metrics.model == "hgb_full")]
    dep_test = float(test[test.target == "departures"].mae.iloc[0])
    arr_test = float(test[test.target == "arrivals"].mae.iloc[0])
    dep_gain = float(test[test.target == "departures"].improvement_vs_previous_day.iloc[0])
    arr_gain = float(test[test.target == "arrivals"].improvement_vs_previous_day.iloc[0])
    dep_peak_under = float(test[test.target == "departures"].peak_underprediction_rate.iloc[0])
    arr_peak_under = float(test[test.target == "arrivals"].peak_underprediction_rate.iloc[0])
    candidates = sum(item["candidates"] for item in rounds)
    winners = [(item["run_id"], target, model) for item in rounds for target, model in item["chosen"].items()
               if model != "hgb_full"]
    findings = [
        {"id": "F1", "title": "工作日双峰、周末单峰，城市级需求集中度很高",
         "value": (f"工作日 08:00 均值 {weekday.loc[8]:.0f} 次/日、17:00 {weekday.loc[17]:.0f} 次/日；"
                   f"周末峰值在 {weekend_peak:02d}:00（{weekend.loc[weekend_peak]:.0f} 次/日）。"
                   f"全月最高小时为 {busiest_hour:02d}:00（{hourly.rides_all.max():,} 次）。"),
         "scope": f"全量订单 {len(rides):,} 条，2024-01-01 至 2024-02-01（按 started_at）",
         "source": "data/summary.json → trends.hourly；figures/fig02_hourly_profile.png",
         "figure": "fig02_hourly_profile.png"},
        {"id": "F2", "title": "站点级潮汐普遍存在，早晚方向系统性反转",
         "value": (f"{len(big)} 个事件量 ≥200 的站点中 {reversal_share:.1%}（{int(big.reversal.sum())} 个）"
                   f"早晚净流出符号相反；上午与下午净流出的相关系数 {corr:.3f}。"),
         "scope": "全量订单的站点端点，上午 06–09 时、下午 16–19 时",
         "source": "data/summary.json → stations.tide；figures/fig06_tide_scatter.png",
         "figure": "fig06_tide_scatter.png"},
        {"id": "F3", "title": "“热门站点”不等于“净流出站点”",
         "value": (f"事件量前 20 与净流量绝对值前 20 只有 {overlap} 个重合；最大站 {busiest.station_id}"
                   f"（{int(busiest.events):,} 次）净流量仅 {busiest.net:+.0f}，而净流出最高的是 "
                   f"{max_out.station_id}（{max_out.net:+.0f}），净流入最高的是 {max_in.station_id}"
                   f"（{max_in.net:+.0f}）。"),
         "scope": "761 个有站点端点的站点，2024-01 全月",
         "source": "data/summary.json → stations.list；figures/fig05_station_scatter.png",
         "figure": "fig05_station_scatter.png"},
        {"id": "F4", "title": "已确认模型的预测明显优于基线，但高峰仍被低估",
         "value": (f"确认模型 hgb_full 测试期 MAE 借出 {dep_test:.4f} / 归还 {arr_test:.4f}，"
                   f"较“昨日同小时”基线改善 {dep_gain:.1%} / {arr_gain:.1%}；"
                   f"但峰值样本欠预测率仍有 {dep_peak_under:.1%} / {arr_peak_under:.1%}。"),
         "scope": "20 个建模站点，测试期 2024-01-25 至 2024-02-01，共 3,360 行/目标",
         "source": "data/summary.json → prediction；figures/fig09_prediction_hourly.png",
         "figure": "fig09_prediction_hourly.png"},
        {"id": "F5", "title": "两轮优化实验只有 1 个候选通过验证门槛，且尚无测试成绩",
         "value": (f"两轮共 {candidates} 个候选，仅 {len(winners)} 个通过预注册门槛："
                   + "；".join(f"{t} → {m}" for _, t, m in winners)
                   + "。该候选只有验证集成绩，测试期未评分。"),
         "scope": "experiments/opt_v020_001、experiments/opt_v021_001（仅验证集与滚动 CV）",
         "source": "data/summary.json → optimization；figures/fig10_candidate_validation.png",
         "figure": "fig10_candidate_validation.png"},
    ]
    return findings
