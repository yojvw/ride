#!/usr/bin/env python3
"""
clean_data.py - auditable cleaning of the raw shared-bike trip CSV (2024-01).

Input : the raw monthly trip CSV (never modified, sha256 recorded).
Output: rides.csv, coverage.csv, stations.csv, rejected_rows.csv,
        cleaning_report.json, data_dictionary.md, station_coordinate_log.csv

Rules follow docs/DEEPSEEK_HANDOFF.md v0.1.0:
  * every dropped row is written to rejected_rows.csv with an explicit reason;
  * missing station / missing coordinates / missing categories are handled
    separately and never cause a row with valid timestamps to be dropped;
  * station ids are read and written as strings (leading zeros preserved);
  * nothing is imputed that was not measured (no zero fills, no invented ids).

Run:
    python scripts/clean_data.py                     # uses data/raw + data/clean
    python scripts/clean_data.py --raw PATH --out DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW = PROJECT_ROOT / "data" / "raw" / "题5_共享单车骑行_202401(1).csv"
DEFAULT_OUT = PROJECT_ROOT / "data" / "clean"

RAW_COLUMNS = [
    "ride_id",
    "rideable_type",
    "started_at",
    "ended_at",
    "start_station_name",
    "start_station_id",
    "end_station_name",
    "end_station_id",
    "start_lat",
    "start_lng",
    "end_lat",
    "end_lng",
    "member_casual",
]

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
ANALYSIS_START = pd.Timestamp("2024-01-01 00:00:00")
ANALYSIS_END = pd.Timestamp("2024-02-01 00:00:00")

# -- documented, fixed thresholds (see cleaning_report.json / data_dictionary.md)
COORD_OUTLIER_M = 200.0          # row coordinate further than this from its station centre
COORD_BOUNDS_LAT = (38.0, 39.5)  # Washington DC metro sanity envelope
COORD_BOUNDS_LNG = (-78.0, -76.5)
LONG_DURATION_MIN = 180.0        # flag only, never a deletion rule
CAP_DURATION_MIN = 1440.0        # flag only: 24h+ cluster around the 25h upload cap
GAP_ALPHA = 0.01                 # coverage: Poisson plausibility level for a silence run,
                                 # after scaling by that day's network-wide trip volume

BIKE_MAP = {"classic_bike": "classic", "electric_bike": "electric"}
MEMBER_MAP = {"member": "member", "casual": "casual"}

STATUS_ASSUMED = "assumed"


# --------------------------------------------------------------------------- helpers
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def haversine_m(lat1, lng1, lat2, lng2):
    r = 6371000.0
    p1 = np.radians(np.asarray(lat1, dtype=float))
    p2 = np.radians(np.asarray(lat2, dtype=float))
    dp = p2 - p1
    dl = np.radians(np.asarray(lng2, dtype=float) - np.asarray(lng1, dtype=float))
    a = np.sin(dp / 2.0) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2.0) ** 2
    return 2.0 * r * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def clean_text(series: pd.Series) -> pd.Series:
    out = series.astype("string")
    out = out.str.replace("\u00a0", " ", regex=False)
    out = out.str.replace(r"\s+", " ", regex=True)
    return out.str.strip()


def load_raw(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""], encoding="utf-8-sig")
    missing = [c for c in RAW_COLUMNS if c not in df.columns]
    if missing:
        raise SystemExit(f"Raw file is missing expected columns: {missing}")
    df = df[RAW_COLUMNS].copy()
    df.insert(0, "source_row", np.arange(2, len(df) + 2, dtype=int))
    return df


# --------------------------------------------------------------------------- cleaning
def split_rejected(raw: pd.DataFrame):
    """Return (retained, rejected, stats). Order: exact duplicates, then timing."""
    start_ts = pd.to_datetime(raw["started_at"], format=TIME_FORMAT, errors="coerce")
    end_ts = pd.to_datetime(raw["ended_at"], format=TIME_FORMAT, errors="coerce")
    duration = (end_ts - start_ts).dt.total_seconds() / 60.0

    exact_dup = raw.duplicated(subset=RAW_COLUMNS, keep="first")
    bad_time = start_ts.isna() | end_ts.isna()
    nonpositive = (~bad_time) & (duration <= 0.0)

    # rule 6: same ride_id with conflicting content must be reported, never silently keyed away
    content_cols = [c for c in RAW_COLUMNS if c != "ride_id"]
    unique_content = raw[RAW_COLUMNS].drop_duplicates(subset=["ride_id"] + content_cols)
    per_id = unique_content.groupby("ride_id", dropna=False).size()
    conflict_ids = per_id[per_id > 1].index.tolist()

    reasons = []
    for dup, bad, nonpos in zip(exact_dup.to_numpy(), bad_time.to_numpy(), nonpositive.to_numpy()):
        parts = []
        if dup:
            parts.append("exact_duplicate_row")
        if bad:
            parts.append("unparseable_timestamp")
        if nonpos:
            parts.append("end_not_after_start")
        reasons.append(";".join(parts))
    reasons = pd.Series(reasons, index=raw.index, dtype="object")

    rejected_mask = exact_dup | bad_time | nonpositive
    rejected = raw.loc[rejected_mask].copy()
    rejected["rejection_reason"] = reasons[rejected_mask]
    rejected["started_at_parsed"] = start_ts[rejected_mask].dt.strftime(TIME_FORMAT)
    rejected["ended_at_parsed"] = end_ts[rejected_mask].dt.strftime(TIME_FORMAT)
    rejected["duration_min_computed"] = duration[rejected_mask].round(6)

    stats = {
        "exact_duplicate_rows": int(exact_dup.sum()),
        "unparseable_timestamp_rows": int(bad_time.sum()),
        "end_not_after_start_rows": int(nonpositive.sum()),
        "rejected_unique_rows": int(rejected_mask.sum()),
        "ride_id_conflict_ids": conflict_ids,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "duration": duration,
    }
    return raw.loc[~rejected_mask].copy(), rejected, stats


def build_station_centres(rides: pd.DataFrame):
    """Robust per-station coordinate centres from both endpoints."""
    starts = rides.loc[rides.start_station_id.notna() & rides.start_lat.notna(),
                       ["start_station_id", "start_lat", "start_lng"]]
    starts.columns = ["station_id", "lat", "lng"]
    ends = rides.loc[rides.end_station_id.notna() & rides.end_lat.notna(),
                     ["end_station_id", "end_lat", "end_lng"]]
    ends.columns = ["station_id", "lat", "lng"]
    obs = pd.concat([starts.assign(endpoint="start"), ends.assign(endpoint="end")], ignore_index=True)
    centre = obs.groupby("station_id")[["lat", "lng"]].median()
    return obs, centre


def clear_outlier_coordinates(rides: pd.DataFrame):
    """Blank coordinates that cannot belong to the recorded station; never fill, never drop."""
    rides = rides.copy()
    flags = pd.Series([[] for _ in range(len(rides))], index=rides.index, dtype="object")
    outlier_count = {"start": 0, "end": 0, "start_envelope": 0, "end_envelope": 0}

    for side in ("start", "end"):
        lat, lng, sid = f"{side}_lat", f"{side}_lng", f"{side}_station_id"
        rides[lat] = pd.to_numeric(rides[lat], errors="coerce")
        rides[lng] = pd.to_numeric(rides[lng], errors="coerce")

        out_of_env = (
            rides[lat].notna()
            & (
                ~rides[lat].between(*COORD_BOUNDS_LAT)
                | ~rides[lng].between(*COORD_BOUNDS_LNG)
            )
        )
        if out_of_env.any():
            outlier_count[f"{side}_envelope"] = int(out_of_env.sum())
            for ix in rides.index[out_of_env]:
                flags[ix].append(f"{side}_coords_out_of_envelope")
            rides.loc[out_of_env, [lat, lng]] = np.nan

    # station-relative outliers (only where the station id is known)
    obs, centre = build_station_centres(rides)
    for side in ("start", "end"):
        lat, lng, sid = f"{side}_lat", f"{side}_lng", f"{side}_station_id"
        has = rides[sid].notna() & rides[lat].notna()
        if not has.any():
            continue
        joined = rides.loc[has, [sid, lat, lng]].join(
            centre.rename(columns={"lat": "c_lat", "lng": "c_lng"}), on=sid
        )
        dist = haversine_m(joined[lat], joined[lng], joined["c_lat"], joined["c_lng"])
        bad_ix = joined.index[dist > COORD_OUTLIER_M]
        if len(bad_ix):
            outlier_count[side] = int(len(bad_ix))
            for ix in bad_ix:
                flags[ix].append(f"{side}_coord_outlier")
            rides.loc[bad_ix, [lat, lng]] = np.nan

    rides["_coord_flags"] = flags
    return rides, outlier_count


def build_rides_table(raw_valid: pd.DataFrame, start_ts: pd.Series, end_ts: pd.Series,
                      duration: pd.Series, source_name: str, source_sha: str):
    idx = raw_valid.index
    out = pd.DataFrame(index=idx)
    out["ride_id"] = raw_valid["ride_id"].astype("string").str.strip()
    out["started_at"] = start_ts.loc[idx].dt.strftime(TIME_FORMAT)
    out["ended_at"] = end_ts.loc[idx].dt.strftime(TIME_FORMAT)
    out["start_station_id"] = clean_text(raw_valid["start_station_id"])
    out["end_station_id"] = clean_text(raw_valid["end_station_id"])
    out["member_type"] = (
        clean_text(raw_valid["member_casual"]).map(lambda x: MEMBER_MAP.get(str(x).lower(), str(x).lower())
                                                   if pd.notna(x) else "unknown")
    )
    out["bike_type"] = (
        clean_text(raw_valid["rideable_type"]).map(lambda x: BIKE_MAP.get(str(x).lower(), str(x).lower())
                                                   if pd.notna(x) else "unknown")
    )
    out["duration_min"] = duration.loc[idx].round(6)
    out["start_lat"] = pd.to_numeric(raw_valid["start_lat"], errors="coerce")
    out["start_lng"] = pd.to_numeric(raw_valid["start_lng"], errors="coerce")
    out["end_lat"] = pd.to_numeric(raw_valid["end_lat"], errors="coerce")
    out["end_lng"] = pd.to_numeric(raw_valid["end_lng"], errors="coerce")
    out["start_station_name"] = clean_text(raw_valid["start_station_name"])
    out["end_station_name"] = clean_text(raw_valid["end_station_name"])
    out["source_member_casual"] = clean_text(raw_valid["member_casual"])
    out["source_rideable_type"] = clean_text(raw_valid["rideable_type"])
    out["source_file"] = source_name
    out["source_row"] = raw_valid["source_row"].astype("int64")

    # "missing" is measured on the source values, before any range-based clearing
    src_missing_start_coords = (
        pd.to_numeric(raw_valid["start_lat"], errors="coerce").isna()
        | pd.to_numeric(raw_valid["start_lng"], errors="coerce").isna()
    )
    src_missing_end_coords = (
        pd.to_numeric(raw_valid["end_lat"], errors="coerce").isna()
        | pd.to_numeric(raw_valid["end_lng"], errors="coerce").isna()
    )

    out, outlier_count = clear_outlier_coordinates(out)
    coord_flags = out.pop("_coord_flags")

    # ---- quality flags (informational only; nothing below removes a row)
    flags = pd.Series([[] for _ in range(len(out))], index=out.index, dtype="object")
    for ix, fl in coord_flags.items():
        if fl:
            flags[ix].extend(fl)

    missing_start_station = out["start_station_id"].isna()
    missing_end_station = out["end_station_id"].isna()
    missing_start_coords = src_missing_start_coords
    missing_end_coords = src_missing_end_coords
    long_dur = out["duration_min"] >= LONG_DURATION_MIN
    cap_dur = out["duration_min"] >= CAP_DURATION_MIN
    next_month = end_ts.loc[idx] >= ANALYSIS_END
    same_station = out["start_station_id"].notna() & (out["start_station_id"] == out["end_station_id"])

    flag_masks = [
        ("missing_start_station", missing_start_station),
        ("missing_end_station", missing_end_station),
        ("missing_start_coords", missing_start_coords),
        ("missing_end_coords", missing_end_coords),
        ("long_duration_reviewed", long_dur),
        ("duration_at_24h_cap", cap_dur),
        ("end_in_next_month", next_month),
        ("same_start_end_station", same_station),
    ]
    for name, mask in flag_masks:
        mask = mask.fillna(False).astype(bool)
        for ix in out.index[mask.to_numpy()]:
            flags[ix].append(name)

    out["quality_flags"] = [";".join(dict.fromkeys(fl)) for fl in flags]

    out = out[[
        "ride_id", "started_at", "ended_at", "start_station_id", "end_station_id",
        "member_type", "bike_type", "duration_min",
        "start_lat", "start_lng", "end_lat", "end_lng",
        "quality_flags", "source_file", "source_row",
        "start_station_name", "end_station_name",
        "source_member_casual", "source_rideable_type",
    ]]
    out = out.sort_values(["started_at", "ride_id"], kind="mergesort").reset_index(drop=True)

    counts = {
        "missing_start_station": int(missing_start_station.sum()),
        "missing_end_station": int(missing_end_station.sum()),
        "missing_start_coords": int(missing_start_coords.sum()),
        "missing_end_coords": int(missing_end_coords.sum()),
        "long_duration_reviewed": int(long_dur.sum()),
        "duration_at_24h_cap": int(cap_dur.sum()),
        "end_in_next_month": int(next_month.sum()),
        "same_start_end_station": int(same_station.sum()),
        "start_coord_outlier": outlier_count["start"],
        "end_coord_outlier": outlier_count["end"],
        "start_coords_out_of_envelope": outlier_count.get("start_envelope", 0),
        "end_coords_out_of_envelope": outlier_count.get("end_envelope", 0),
    }
    return out, counts


def build_coverage(rides: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp):
    """Station availability intervals.  Status is always 'assumed' (no operational log)."""
    ev = pd.concat(
        [
            rides.loc[rides.start_station_id.notna(), ["start_station_id", "started_at"]]
            .rename(columns={"start_station_id": "station_id", "started_at": "t"}),
            rides.loc[rides.end_station_id.notna(), ["end_station_id", "ended_at"]]
            .rename(columns={"end_station_id": "station_id", "ended_at": "t"}),
        ],
        ignore_index=True,
    )
    ev["t"] = pd.to_datetime(ev["t"], format=TIME_FORMAT, errors="coerce")
    ev = ev[(ev["t"] >= start) & (ev["t"] < end)]
    ev["day"] = ev["t"].dt.floor("D")

    days = pd.date_range(start, end, freq="D", inclusive="left")
    daily = ev.groupby(["station_id", "day"]).size().unstack(fill_value=0).reindex(columns=days, fill_value=0)

    # Network-wide volume per day rescales every station's expectation, so a snow day with a
    # genuine near-zero keeps its zeros while an unexplained silence on a normal day is masked.
    network_daily = daily.sum(axis=0).to_numpy(dtype=float)
    factors = network_daily / network_daily.mean() if network_daily.mean() > 0 else np.ones_like(network_daily)

    threshold = -math.log(GAP_ALPHA)
    rows = []
    gap_stations = []
    gap_days_total = 0
    for station_id, series in daily.iterrows():
        vals = series.to_numpy()
        nz = np.flatnonzero(vals > 0)
        if nz.size == 0:
            continue
        first, last = int(nz[0]), int(nz[-1])
        segment = vals[first:last + 1]
        rate = segment.sum() / segment.size  # events per active-window day

        interval = [days[first], days[last] + pd.Timedelta(days=1)]
        gaps = []
        i = 0
        while i < segment.size:
            if segment[i] == 0:
                j = i
                while j < segment.size and segment[j] == 0:
                    j += 1
                expected = rate * float(factors[first + i:first + j].sum())
                if expected >= threshold:
                    gaps.append((days[first + i], days[first + j]))
                i = j
            else:
                i += 1

        pieces = [tuple(interval)]
        for g0, g1 in gaps:
            nxt = []
            for a, b in pieces:
                if g1 <= a or g0 >= b:
                    nxt.append((a, b))
                    continue
                if a < g0:
                    nxt.append((a, min(b, g0)))
                if g1 < b:
                    nxt.append((max(a, g1), b))
            pieces = nxt
        if gaps:
            gap_stations.append(station_id)
            gap_days_total += int(sum((g1 - g0).days for g0, g1 in gaps))
        for a, b in pieces:
            a = max(a, start)
            b = min(b, end)
            if b > a:
                rows.append({"station_id": station_id, "start": a, "end": b, "status": STATUS_ASSUMED})

    coverage = pd.DataFrame(rows).sort_values(["station_id", "start"]).reset_index(drop=True)
    coverage["start"] = coverage["start"].dt.strftime(TIME_FORMAT)
    coverage["end"] = coverage["end"].dt.strftime(TIME_FORMAT)
    meta = {
        "stations_with_coverage": int(coverage.station_id.nunique()),
        "coverage_rows": int(len(coverage)),
        "stations_with_interior_gap": len(gap_stations),
        "interior_gap_days_total": gap_days_total,
        "gap_rule": (
            "interior silence runs are treated as unobserved only when the station's expected trip count over "
            "the run (own activity rate scaled by that day's network-wide volume) makes an exact zero implausible "
            f"at the {GAP_ALPHA} Poisson level; weather-driven near-zero days therefore stay observed"
        ),
    }
    return coverage, meta


def build_stations(rides: pd.DataFrame):
    obs, centre = build_station_centres(rides)
    names = {}
    for col, sid in (("start_station_name", "start_station_id"), ("end_station_name", "end_station_id")):
        sub = rides.loc[rides[sid].notna() & rides[col].notna(), [sid, col]]
        for station_id, grp in sub.groupby(sid):
            vc = grp[col].value_counts()
            names.setdefault(station_id, vc.index[0])

    n_start = rides.loc[rides.start_station_id.notna() & rides.start_lat.notna()].groupby("start_station_id").size()
    n_end = rides.loc[rides.end_station_id.notna() & rides.end_lat.notna()].groupby("end_station_id").size()

    centre = centre.rename(columns={"lat": "lat", "lng": "lng"})
    stations = centre.reset_index()
    stations["station_id"] = stations["station_id"].astype("string")
    stations = stations.rename(columns={"lat": "lat", "lng": "lng"})
    stations["station_name"] = stations["station_id"].map(names)

    # per-station dispersion of inlier observations around the centre
    joined = obs.join(centre, on="station_id", rsuffix="_c")
    joined["dist"] = haversine_m(joined["lat"], joined["lng"], joined["lat_c"], joined["lng_c"])
    p90 = joined.groupby("station_id")["dist"].quantile(0.90)

    start_only = obs[obs.endpoint == "start"].groupby("station_id")[["lat", "lng"]].median()
    end_only = obs[obs.endpoint == "end"].groupby("station_id")[["lat", "lng"]].median()
    sep = {}
    for station_id in centre.index:
        if station_id in start_only.index and station_id in end_only.index:
            sep[station_id] = float(haversine_m(start_only.loc[station_id, "lat"], start_only.loc[station_id, "lng"],
                                                end_only.loc[station_id, "lat"], end_only.loc[station_id, "lng"]))
        else:
            sep[station_id] = float("nan")

    stations["n_start_records"] = stations["station_id"].map(n_start).fillna(0).astype(int)
    stations["n_end_records"] = stations["station_id"].map(n_end).fillna(0).astype(int)
    stations["p90_distance_to_centre_m"] = stations["station_id"].map(p90).round(1)
    stations["centre_separation_m"] = stations["station_id"].map(sep).round(1)

    log = stations.copy()
    log["note"] = np.where(
        log["centre_separation_m"].fillna(0) > 100.0,
        "start-derived and end-derived centres differ by >100 m; combined median used, relocation or miscoded records possible",
        "start and end derived centres agree",
    )
    log["coordinate_source"] = "median of inlier trip endpoints (start and end), raw file"
    log["coordinate_source"] = str("median of inlier trip endpoint coordinates in the raw file")

    stations_out = stations[["station_id", "lat", "lng"]].copy()
    stations_out["lat"] = stations_out["lat"].round(6)
    stations_out["lng"] = stations_out["lng"].round(6)

    log_out = pd.DataFrame({
        "station_id": log["station_id"],
        "station_name": log["station_name"],
        "n_start_records": log["n_start_records"],
        "n_end_records": log["n_end_records"],
        "start_center_lat": log["station_id"].map(start_only["lat"]).round(6),
        "start_center_lng": log["station_id"].map(start_only["lng"]).round(6),
        "end_center_lat": log["station_id"].map(end_only["lat"]).round(6),
        "end_center_lng": log["station_id"].map(end_only["lng"]).round(6),
        "centre_separation_m": log["centre_separation_m"],
        "p90_distance_to_centre_m": log["p90_distance_to_centre_m"],
        "coordinate_source": log["coordinate_source"],
        "note": log["note"],
    }).sort_values("station_id").reset_index(drop=True)

    meta = {
        "stations": int(len(stations_out)),
        "stations_with_disagreeing_centres": int((log["centre_separation_m"].fillna(0) > 100).sum()),
        "max_p90_distance_m": float(log["p90_distance_to_centre_m"].max()),
        "max_centre_separation_m": float(log["centre_separation_m"].max()),
    }
    return stations_out, log_out, meta


# --------------------------------------------------------------------------- report
def missing_rates(frame: pd.DataFrame, columns) -> dict:
    """Share of rows without a usable value; an empty string counts as missing."""
    out = {}
    n = len(frame)
    for col in columns:
        if col in frame:
            blank = frame[col].astype("string").fillna("") == ""
            out[col] = round(float(blank.mean()), 6) if n else 0.0
    return out


def duration_summary(series: pd.Series) -> dict:
    s = pd.to_numeric(series, errors="coerce").dropna()
    qs = [0.5, 0.9, 0.95, 0.99, 0.999]
    return {
        "count": int(len(s)),
        "min": round(float(s.min()), 4),
        "p50": round(float(s.quantile(0.5)), 4),
        "p90": round(float(s.quantile(0.9)), 4),
        "p95": round(float(s.quantile(0.95)), 4),
        "p99": round(float(s.quantile(0.99)), 4),
        "p999": round(float(s.quantile(0.999)), 4),
        "max": round(float(s.max()), 4),
        "mean": round(float(s.mean()), 4),
        "ge_180_min": int((s >= 180).sum()),
        "ge_1440_min": int((s >= 1440).sum()),
        "ge_1490_min": int((s >= 1490).sum()),
    }


def write_outputs(out_dir: Path, rides, coverage, stations, rejected, coord_log, report, dictionary):
    out_dir.mkdir(parents=True, exist_ok=True)
    rides.to_csv(out_dir / "rides.csv", index=False, encoding="utf-8")
    coverage.to_csv(out_dir / "coverage.csv", index=False, encoding="utf-8")
    stations.to_csv(out_dir / "stations.csv", index=False, encoding="utf-8")
    rejected.to_csv(out_dir / "rejected_rows.csv", index=False, encoding="utf-8")
    coord_log.to_csv(out_dir / "station_coordinate_log.csv", index=False, encoding="utf-8")
    (out_dir / "cleaning_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (out_dir / "data_dictionary.md").write_text(dictionary, encoding="utf-8")


def build_dictionary(report, rides, coverage, stations) -> str:
    bt = chr(96)
    fence = bt * 3
    lines = []
    lines.append("# Data dictionary - cleaned shared-bike trips (2024-01)")
    lines.append("")
    lines.append(f"Generated by {bt}scripts/clean_data.py{bt} from "
                 f"{bt}{report['source_files'][0]['name']}{bt}.")
    lines.append(f"Raw rows: {report['raw_rows']}; retained rows: {report['retained_rows']}; "
                 f"rejected rows: {report['rejected_unique_rows']}.")
    lines.append("")
    lines.append("## Time basis")
    lines.append("")
    lines.append(report["time_basis"])
    lines.append("")
    lines.append(f"- {bt}started_at{bt} / {bt}ended_at{bt}: {bt}YYYY-MM-DD HH:MM:SS{bt}, local wall clock, "
                 "no UTC offset, no DST transition inside January 2024.")
    lines.append(f"- {bt}duration_min{bt}: minutes, computed as ({bt}ended_at{bt} - {bt}started_at{bt}) / 60 s. "
                 "Never taken from a source column (the source has no duration column).")
    lines.append("- Cross-month rides are kept: 35 rides start on 31 January and end on 1 February and are "
                 "flagged " + bt + "end_in_next_month" + bt + ".")
    lines.append("")
    lines.append("## rides.csv columns")
    lines.append("")
    lines.append(f"| column | type | source | rule |")
    lines.append("|---|---|---|---|")
    rows = [
        ("ride_id", "string", "ride_id", "kept verbatim; unique in the raw file; never regenerated"),
        ("started_at", "datetime string", "started_at", "parsed with strict format " + TIME_FORMAT),
        ("ended_at", "datetime string", "ended_at", "parsed with strict format " + TIME_FORMAT),
        ("start_station_id", "string or empty", "start_station_id", "string, leading zeros preserved, no coordinate-based guessing"),
        ("end_station_id", "string or empty", "end_station_id", "string, leading zeros preserved"),
        ("member_type", "string", "member_casual", "member->member, casual->casual, missing->unknown"),
        ("bike_type", "string", "rideable_type", "classic_bike->classic, electric_bike->electric, missing->unknown"),
        ("duration_min", "float", "derived", "ended_at - started_at in minutes, 6 decimals"),
        ("start_lat/start_lng", "float or empty", "start_lat/start_lng", "blanked when outside the metro envelope or >200 m from the station centre"),
        ("end_lat/end_lng", "float or empty", "end_lat/end_lng", "same rule; empty when the source has none"),
        ("quality_flags", "string", "derived", "semicolon-separated; empty when no flag applies"),
        ("source_file", "string", "file name", "raw file name for traceability"),
        ("source_row", "int", "line number", "1-based physical line in the raw CSV (header = line 1)"),
        ("start_station_name/end_station_name", "string or empty", "names", "informational only; downstream joins on station id"),
        ("source_member_casual", "string", "member_casual", "raw value, for audit"),
        ("source_rideable_type", "string", "rideable_type", "raw value, for audit"),
    ]
    for a, b, c, d in rows:
        lines.append(f"| {bt}{a}{bt} | {b} | {bt}{c}{bt} | {d} |")
    lines.append("")
    lines.append("## quality_flags vocabulary")
    lines.append("")
    lines.append("| flag | meaning | rows |")
    lines.append("|---|---|---:|")
    for flag, n in report["quality_flag_counts"].items():
        meanings = {
            "missing_start_station": "start station id and name are absent (undocked / free-floating start)",
            "missing_end_station": "end station id and name are absent (undocked / free-floating end)",
            "missing_start_coords": "no start coordinates in the source (range-cleared coordinates are flagged separately)",
            "missing_end_coords": "no end coordinates in the source",
            "start_coord_outlier": "start coordinate was >200 m from the station centre and was blanked",
            "end_coord_outlier": "end coordinate was >200 m from the station centre and was blanked",
            "long_duration_reviewed": "duration >= 180 min; retained on purpose, review before modelling",
            "duration_at_24h_cap": "duration >= 1440 min; sits on the apparent 25 h upload cap",
            "end_in_next_month": "ride ends on 1 February; kept, but the analysis window cuts arrivals at 1 February 00:00",
            "same_start_end_station": "same origin and destination station; not an error, kept",
            "start_coords_out_of_envelope": "start coordinate outside the Washington DC metro envelope; blanked",
            "end_coords_out_of_envelope": "end coordinate outside the envelope; blanked",
            "possible_duplicate_trip": "identical start/end time and route but a different ride id; kept, not deduplicated",
        }
        lines.append(f"| {flag} | {meanings.get(flag, '')} | {n} |")
    lines.append("")
    lines.append("## Coordinates")
    lines.append("")
    lines.append("- Endpoint coordinates for docked trips repeat the station location with a few metres of jitter: "
                 f"for every station the 90th percentile distance to its centre is at most "
                 f"{report['station_summary']['max_p90_distance_m']:.1f} m.")
    lines.append("- Endpoint coordinates for undocked trips (no station id) are published with at most 2 decimal "
                 "places, i.e. roughly 1 km precision; they are not meter-accurate and were not refined.")
    lines.append(f"- {report['station_summary']['stations']} station centres are in {bt}stations.csv{bt}; no capacity "
                 "or inventory is stored there because none is observed.")
    lines.append("")
    lines.append("## coverage.csv")
    lines.append("")
    lines.append(f"- One row per contiguous {bt}[start, end){bt} station-availability interval, whole hours, "
                 "non-overlapping per station.")
    lines.append(f"- Every row is {bt}assumed{bt}: no operational log, station status feed or platform statement "
                 "was supplied, so completeness cannot be confirmed.")
    sc = report["coverage_summary"]["status_counts"]
    lines.append(f"- Status counts: assumed {sc.get('assumed', 0)}, confirmed {sc.get('confirmed', 0)}.")
    lines.append("- Gap rule: " + report["coverage_summary"]["gap_rule"] + ".")
    lines.append("")
    lines.append("## Files in this directory")
    lines.append("")
    lines.append("| file | content |")
    lines.append("|---|---|")
    lines.append(f"| {bt}rides.csv{bt} | cleaned trip records, one row per retained ride |")
    lines.append(f"| {bt}coverage.csv{bt} | station availability intervals, all {bt}assumed{bt} |")
    lines.append(f"| {bt}stations.csv{bt} | one robust coordinate per station |")
    lines.append(f"| {bt}rejected_rows.csv{bt} | rows excluded from rides.csv with the reason and source row |")
    lines.append(f"| {bt}cleaning_report.json{bt} | rule hits, missing rates, assumptions, open questions |")
    lines.append(f"| {bt}station_coordinate_log.csv{bt} | per-station coordinate evidence and consistency |")
    lines.append(f"| {bt}data_dictionary.md{bt} | this document |")
    lines.append("")
    lines.append("## Units")
    lines.append("")
    lines.append("- distance: metres; duration: minutes; coordinates: decimal degrees (WGS84), latitude first.")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- main
def main(argv=None):
    parser = argparse.ArgumentParser(description="Clean the raw 2024-01 shared-bike trip CSV.")
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--analysis-start", default=str(ANALYSIS_START))
    parser.add_argument("--analysis-end", default=str(ANALYSIS_END))
    args = parser.parse_args(argv)

    raw_path = args.raw.resolve()
    out_dir = args.out.resolve()
    if not raw_path.exists():
        raise SystemExit(f"Raw file not found: {raw_path}")
    if out_dir == raw_path.parent:
        raise SystemExit("Refusing to write outputs next to the raw file.")

    analysis_start = pd.Timestamp(args.analysis_start)
    analysis_end = pd.Timestamp(args.analysis_end)

    raw = load_raw(raw_path)
    n_raw = len(raw)

    valid_raw, rejected, stats = split_rejected(raw)
    source_name = raw_path.name
    source_sha = sha256_file(raw_path)

    rides, flag_counts = build_rides_table(
        valid_raw, stats["start_ts"], stats["end_ts"], stats["duration"], source_name, source_sha
    )

    # rule 7: same trip signature, different ride id -> keep both, flag both
    sig_cols = ["started_at", "ended_at", "start_station_id", "end_station_id", "member_type", "bike_type"]
    sig_dup = rides.duplicated(subset=sig_cols, keep=False)
    if sig_dup.any():
        for ix in rides.index[sig_dup]:
            tags = [t for t in str(rides.at[ix, "quality_flags"]).split(";") if t]
            tags.append("possible_duplicate_trip")
            rides.at[ix, "quality_flags"] = ";".join(dict.fromkeys(tags))
    flag_counts["possible_duplicate_trip"] = int(sig_dup.sum())

    coverage, coverage_meta = build_coverage(rides, analysis_start, analysis_end)
    stations, coord_log, station_meta = build_stations(rides)

    # ---------------- integrity checks (fail loudly instead of shipping bad data)
    checks = {}
    checks["ride_id_nonempty_unique"] = bool(
        rides.ride_id.notna().all() and not rides.ride_id.duplicated().any()
    )
    checks["all_durations_positive"] = bool((rides.duration_min > 0).all())
    checks["duration_matches_timestamps"] = bool(
        (
            (
                pd.to_datetime(rides.ended_at) - pd.to_datetime(rides.started_at)
            ).dt.total_seconds() / 60.0
            - rides.duration_min
        ).abs().max() <= 0.001
    )
    checks["station_ids_are_strings"] = bool(
        rides.start_station_id.dropna().map(lambda x: isinstance(x, str)).all()
        and rides.end_station_id.dropna().map(lambda x: isinstance(x, str)).all()
    )
    checks["coverage_hour_aligned"] = bool(
        (pd.to_datetime(coverage.start).dt.minute == 0).all()
        and (pd.to_datetime(coverage.end).dt.minute == 0).all()
    )
    checks["coverage_positive_length"] = bool((pd.to_datetime(coverage.end) > pd.to_datetime(coverage.start)).all())
    overlap_free = True
    cov_t = coverage.assign(s=pd.to_datetime(coverage.start), e=pd.to_datetime(coverage.end))
    for station_id, grp in cov_t.groupby("station_id"):
        s = grp.sort_values("s")
        if (s.e.iloc[:-1].to_numpy() > s.s.iloc[1:].to_numpy()).any():
            overlap_free = False
            break
    checks["coverage_non_overlapping"] = bool(overlap_free)
    checks["stations_unique"] = bool(not stations.station_id.duplicated().any())
    checks["row_accounting"] = bool(
        n_raw == len(rides) + len(rejected) + stats["exact_duplicate_rows"]
    )
    if not all(checks.values()):
        raise SystemExit(f"Integrity check failed: {checks}")

    # ---------------- statistics for the report
    before_cols = RAW_COLUMNS
    after_cols = [c for c in rides.columns]
    status_counts = coverage.status.value_counts().to_dict()

    dur_retained = duration_summary(rides.duration_min)
    dur_raw = duration_summary(stats["duration"])

    rule_hits = {
        "R1_time_unparseable": {"rows": stats["unparseable_timestamp_rows"],
                                "excluded": stats["unparseable_timestamp_rows"]},
        "R1_end_not_after_start": {"rows": stats["end_not_after_start_rows"],
                                   "excluded": stats["end_not_after_start_rows"]},
        "R2_exact_duplicate_row": {"rows": stats["exact_duplicate_rows"],
                                   "excluded": stats["exact_duplicate_rows"]},
        "R2_duplicate_ride_id_conflict": {"rows": len(stats["ride_id_conflict_ids"]),
                                          "excluded": 0},
        "R3_missing_start_station": {"rows": flag_counts["missing_start_station"], "excluded": 0},
        "R3_missing_end_station": {"rows": flag_counts["missing_end_station"], "excluded": 0},
        "R4_long_duration_ge_180min": {"rows": flag_counts["long_duration_reviewed"], "excluded": 0},
        "R5_same_start_end_station": {"rows": flag_counts["same_start_end_station"], "excluded": 0},
        "R6_missing_end_coords": {"rows": flag_counts["missing_end_coords"], "excluded": 0},
        "R6_coord_outlier_cleared": {"rows": flag_counts["start_coord_outlier"] + flag_counts["end_coord_outlier"],
                                     "excluded": 0},
        "R7_same_trip_signature_different_id": {"rows": flag_counts["possible_duplicate_trip"], "excluded": 0},
        "R8_member_or_bike_missing": {"rows": int((rides.member_type == "unknown").sum()),
                                      "excluded": 0},
        "R10_end_in_next_month": {"rows": flag_counts["end_in_next_month"], "excluded": 0},
    }
    overlap_explanation = (
        "Each row is counted once per rule it triggers, so rule hits overlap by design. "
        f"Only R1 (timing) and R2 (exact duplicate) remove rows; their union is {len(rejected)} unique rows, "
        "which is exactly rejected_unique_rows. No other rule deletes anything: long durations, "
        "same-station round trips, missing stations, missing coordinates and same-signature trips are all retained "
        "and flagged. Summing the rule hits would therefore double count and is not the deletion total."
    )

    report = {
        "report_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "scripts/clean_data.py",
        "source_files": [{
            "name": source_name,
            "path": str(raw_path),
            "sha256": source_sha,
            "bytes": int(raw_path.stat().st_size),
            "encoding": "utf-8 (read as utf-8-sig, no BOM present)",
        }],
        "time_basis": (
            "Local wall-clock time, timezone-naive, as published in the source monthly trip file. "
            "The file carries no UTC offset and no timezone metadata; the station names and coordinates "
            "(38.71-39.13 N, -77.37 to -76.83 W; Washington DC / Arlington / Montgomery County) identify the "
            "operating area as US Eastern (America/New_York). January 2024 contains no daylight-saving "
            "transition, so every timestamp maps unambiguously to Eastern Standard Time (UTC-5)."
        ),
        "time_basis_evidence": [
            "station names and coordinates place the network in the Washington DC metropolitan area",
            "all timestamps are 19-character 'YYYY-MM-DD HH:MM:SS' strings without offset or 'Z'",
            "all trip starts fall in January 2024; 35 rides end on 1 February 2024",
        ],
        "raw_rows": int(n_raw),
        "retained_rows": int(len(rides)),
        "rejected_unique_rows": int(len(rejected)),
        "exact_duplicates_removed": int(stats["exact_duplicate_rows"]),
        "rule_hits": rule_hits,
        "overlap_explanation": overlap_explanation,
        "missing_rates_before": missing_rates(raw, before_cols),
        "missing_rates_after": missing_rates(rides, after_cols),
        "field_mapping": {
            "ride_id": "ride_id",
            "started_at": "started_at",
            "ended_at": "ended_at",
            "start_station_id": "start_station_id",
            "end_station_id": "end_station_id",
            "member_type": "member_casual (member->member, casual->casual, missing->unknown)",
            "bike_type": "rideable_type (classic_bike->classic, electric_bike->electric, missing->unknown)",
            "duration_min": "derived from ended_at - started_at",
            "quality_flags": "derived",
        },
        "value_mapping": {
            "member_casual": {k: v for k, v in MEMBER_MAP.items()},
            "rideable_type": {k: v for k, v in BIKE_MAP.items()},
            "unknown_policy": "missing category -> 'unknown'; no membership or bike type is inferred",
        },
        "duration_summary_retained": dur_retained,
        "duration_summary_raw_parsed": dur_raw,
        "quality_flag_counts": {k: int(v) for k, v in flag_counts.items()},
        "station_summary": {
            **station_meta,
            "stations_with_start_records": int(rides.start_station_id.nunique()),
            "stations_with_end_records": int(rides.end_station_id.nunique()),
        },
        "coverage_summary": {
            **coverage_meta,
            "status_counts": status_counts,
            "confirmed_rows": int(status_counts.get("confirmed", 0)),
            "assumed_rows": int(status_counts.get("assumed", 0)),
            "regular_interval_hours": 1,
        },
        "coverage_evidence": [
            "No operational log, station-status feed, capacity file or platform statement was delivered with the "
            "raw CSV, so no interval qualifies as 'confirmed' under the handoff definition.",
            "Every coverage row is therefore 'assumed'. It records where a station shows activity in this month's "
            "file, extended to the whole first and last active day, not a verified open/close date.",
            "Interior silence runs are removed from coverage only when the station's expected trips over the run, "
            f"scaled by that day's network-wide volume, make a Poisson zero implausible at the {GAP_ALPHA} level; "
            "a quiet station on a low-demand day therefore keeps its observed zeros.",
            "Downstream must set allow_assumed_coverage=true deliberately; the guard in bikeproject/io.py is not "
            "bypassed by relabelling these rows.",
        ],
        "assumptions": [
            "The raw file is the complete set of trips that started in January 2024 for this network; no filtering "
            "was applied by the provider beyond the usual monthly cut.",
            "A station that shows activity on a day was operating during that whole day.",
            "A silence at a station is unobserved coverage, not a demand collapse, when the station's own activity "
            "rate scaled by that day's network-wide volume makes an exact zero implausible.",
            "Endpoint coordinates within 200 m of the station centre describe the station, and the small jitter is "
            "measurement noise rather than station relocation.",
            "The 25-hour duration cap is a provider-side trip-closing artefact, not a real 25-hour ride.",
        ],
        "unresolved_questions": [
            "Station operating windows are unverified: coverage.csv is assumed, not confirmed. A station that opened "
            "or closed mid-month will be misrepresented around its boundary.",
            f"{flag_counts['duration_at_24h_cap']} rides pile up just under 25 hours (max {dur_retained['max']} min) "
            "with no ride above 1500 min and most lacking an end station, which looks like a censoring/auto-close "
            "rule at the provider. True durations for these rides are unknown; they are retained and flagged.",
            f"{flag_counts['missing_start_station']} rides have no start station id and "
            f"{flag_counts['missing_end_station']} no end station id (about 30% of electric-bike endpoints versus "
            "under 0.2% of classic-bike endpoints). They are plausibly free-floating e-bike trips, but the file "
            "carries no dock/undock indicator, so this is unconfirmed.",
            "Coordinates of undocked endpoints are published with at most 2 decimal places (~1 km), so those "
            "endpoint positions are coarse; they were kept but must not be treated as precise.",
            "No station capacity, inventory, dock count or outage record exists in this source, so none is "
            "supplied in stations.csv.",
            "Whether January 2024 is representative of other months cannot be established from one monthly file.",
        ],
        "validation": {k: bool(v) for k, v in checks.items()},
        "row_accounting": {
            "raw_rows": int(n_raw),
            "exact_duplicates_removed": int(stats["exact_duplicate_rows"]),
            "rejected_rows": int(len(rejected)),
            "retained_rows": int(len(rides)),
        },
        "analysis_window": {
            "start": str(analysis_start),
            "end": str(analysis_end),
            "note": "coverage intervals are clipped to this window; rides are not clipped, downstream filters "
                    "departures by started_at and arrivals by ended_at",
        },
    }

    # per-station all-month activity is cheap and useful for the audit
    ev_days = pd.concat([
        rides.loc[rides.start_station_id.notna(), ["start_station_id", "started_at"]]
        .rename(columns={"start_station_id": "sid", "started_at": "t"}),
        rides.loc[rides.end_station_id.notna(), ["end_station_id", "ended_at"]]
        .rename(columns={"end_station_id": "sid", "ended_at": "t"}),
    ], ignore_index=True).dropna()
    ev_days["d"] = pd.to_datetime(ev_days.t, format=TIME_FORMAT).dt.floor("D")
    activity = ev_days.groupby("sid")["d"].nunique()
    report["station_summary"]["stations_active_every_day"] = int((activity == 31).sum())
    report["station_summary"]["median_active_days"] = int(activity.median())
    report["station_summary"]["stations_total_in_file"] = int(len(activity))

    report["output_files"] = {
        "rides.csv": int(len(rides)),
        "coverage.csv": int(len(coverage)),
        "stations.csv": int(len(stations)),
        "rejected_rows.csv": int(len(rejected)),
        "station_coordinate_log.csv": int(len(coord_log)),
    }
    dictionary = build_dictionary(report, rides, coverage, stations)
    write_outputs(out_dir, rides, coverage, stations, rejected, coord_log, report, dictionary)

    print(json.dumps({
        "raw_rows": len(raw),
        "retained_rows": len(rides),
        "rejected_rows": len(rejected),
        "stations": len(stations),
        "coverage_rows": len(coverage),
        "flags": {k: v for k, v in flag_counts.items() if v},
        "output_dir": str(out_dir),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
