# -*- coding: utf-8 -*-
"""
Step 1：数据清洗
按 README 五条公共约定执行：
  1) 剔除时长 <1 分钟、>1440 分钟
  2) 剔除终点经纬度缺失
  3) 缺失站点填充为「站点外停车」（禁止 dropna）
  4) 生成衍生列 date / hour / dow / is_weekend / duration_min
预期输出（验收标准）：
  清洗后行数 = 233749（剔除 5085）
  清洗后时长中位数 = 8.92
  member=173286 / casual=60463
  electric_bike=118803 / classic_bike=114946
  站点外停车(起点) = 35516
"""
import pandas as pd

DATA_PATH = "data/题5_共享单车骑行_202401.csv"
OUT_PATH = "output/df_clean.pkl"

# ---------- 读取 ----------
d = pd.read_csv(DATA_PATH)
n0 = len(d)
print("原始行数 :", n0)

# ---------- 时间与时长 ----------
d["started_at"] = pd.to_datetime(d["started_at"])
d["ended_at"] = pd.to_datetime(d["ended_at"])
d["duration_min"] = (d["ended_at"] - d["started_at"]).dt.total_seconds() / 60

# ---------- 剔除规则（公共约定 1、2）----------
mask_bad = (
    (d["duration_min"] < 1)
    | (d["duration_min"] > 1440)
    | d["end_lat"].isna()
    | d["end_lng"].isna()
)
print("剔除 <1min          :", (d["duration_min"] < 1).sum())
print("剔除 >1440min       :", (d["duration_min"] > 1440).sum())
print("剔除终点坐标缺失    :", (d["end_lat"].isna() | d["end_lng"].isna()).sum())

d = d[~mask_bad].copy()
print("合计剔除 :", n0 - len(d))

# ---------- 缺失站点填充（公共约定 2：禁止 dropna）----------
for col in ["start_station_name", "start_station_id",
            "end_station_name", "end_station_id"]:
    d[col] = d[col].fillna("站点外停车")

# ---------- 衍生列（公共约定 3）----------
d["date"] = d["started_at"].dt.date
d["hour"] = d["started_at"].dt.hour
d["dow"] = d["started_at"].dt.dayofweek          # 0=周一
d["is_weekend"] = d["dow"].isin([5, 6]).astype(int)

# ---------- 验收输出 ----------
print("\n===== 清洗后验收（对照 README 标准答案）=====")
print("清洗后行数        :", len(d), "（应为 233749）")
print("时长中位数        :", round(d["duration_min"].median(), 2), "（应为 8.92）")
print("member / casual   :", d["member_casual"].value_counts().to_dict())
print("electric / classic:", d["rideable_type"].value_counts().to_dict())
print("站点外停车(起点)  :", (d["start_station_name"] == "站点外停车").sum(),
      "（应为 35516）")

# ---------- 保存 ----------
d.to_pickle(OUT_PATH)
print("\n已保存清洗后数据 ->", OUT_PATH)
