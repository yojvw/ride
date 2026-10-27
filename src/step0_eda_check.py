# -*- coding: utf-8 -*-
"""
Step 0：数据体检
只读数据、打印关键统计，不做任何修改。
预期输出（验收标准见 README）：
  shape = (238834, 13)
  缺失：start_station_name=37220, end_station_name=39741, end_lat=203
"""
import pandas as pd

DATA_PATH = "data/题5_共享单车骑行_202401.csv"

d = pd.read_csv(DATA_PATH)

print("===== 数据体检 =====")
print("行数 x 列数 :", d.shape)

print("\n--- 缺失统计 ---")
miss = d.isna().sum()
print(miss[miss > 0])

print("\n--- 车辆类型 ---")
print(d["rideable_type"].value_counts())

print("\n--- 用户类型 ---")
print(d["member_casual"].value_counts())

print("\n--- 站点数 ---")
print("起点站:", d["start_station_name"].nunique(),
      " 终点站:", d["end_station_name"].nunique())

print("\n--- 时间范围 ---")
s = pd.to_datetime(d["started_at"])
e = pd.to_datetime(d["ended_at"])
print("最早:", s.min(), " 最晚:", e.max())

print("\n--- 骑行时长（分钟）---")
dur = (e - s).dt.total_seconds() / 60
print("中位数:", round(dur.median(), 2))
print("负数条数        :", (dur <= 0).sum())
print("< 1 分钟        :", (dur < 1).sum())
print("> 1440 分钟(24h):", (dur > 1440).sum())

print("\n--- 结构性缺失验证 ---")
m = d["start_station_name"].isna()
print("起点站缺失共", m.sum(), "条，其中车辆类型分布：")
print(d.loc[m, "rideable_type"].value_counts())

print("\n--- ride_id 重复 ---", d["ride_id"].duplicated().sum())

print("\n[核对] 以下数字应与 README 标准答案一致：")
print("  238834 / 37220 / 39741 / 203")
