import io

import pandas as pd


csv = """ts,height_m,speed_kmh,status,note
2026-10-01 08:00:00,12.3,18.5,OK,normal
2026-10-01 08:00:01,12.5,18.6,ok,normal
2026-10-01 08:00:02,,19.1,WARN,high vibration
2026-10-01 08:00:03,12.7,18.4,OK,normal
2026-10-01 08:00:04,12.9,18.7,warn ,climb
2026-10-01 08:00:05,13.1,18.5,OK,normal
2026-10-01 08:00:06,12.8,18.6,OK,normal
2026-10-01 08:00:07,-3.5,18. 3,WARN,telemetry glitch
2026-10-01 08:00:08,13.2,18.8,OK,normal
2026-10-01 08:00:09,13.0,18.5,OK,normal
2026-10-01 08:00:10,13.4,18.9,OK,normal
2026-10-01 08:00:10,13.4,18.9,OK,normal
2026-10-01 08:00:11,14.0,19.2,WARN,high vibration
2026-10-01 08:00:12,14.1,19.3,warn,climb
2026-10-01 08:00:13,200.0,19.0,WARN,stuck sensor
2026-10-01 08:00:14,14.2,19.1,OK,normal
"""

df = pd.read_csv(io.StringIO(csv))

print("== 16.1 读取与体检 ==")
print("shape:", df.shape)
print("列名:", df.columns.tolist())
print("各列数据类型:")
print(df.dtypes.to_string())
print("前 4 行:")
print(df.head(4).to_string(index=False))
print("最后 2 行:")
print(df.tail(2).to_string(index=False))
print("高度列 describe():")
print(df["height_m"].describe().to_string())

print("== 16.2 缺失与重复 ==")
print("每列缺失个数:")
print(df.isna().sum().to_string())
print("按 ts 判重的重复行数:", df.duplicated(subset="ts").sum())

print("== 16.3 状态写法与速度坏值 ==")
status_counts = df["status"].value_counts(dropna=False)
print("status 原始写法及频数:")
for value, count in status_counts.items():
    print(f"{value!r}: {count}")
print("status 写法种数:", len(status_counts))

speed_numeric = pd.to_numeric(df["speed_kmh"], errors="coerce")
bad_mask = ~speed_numeric.notna()
print("速度无法解析的行数:", bad_mask.sum())
print("对应的 ts 与原始 speed_kmh:")
print(df.loc[bad_mask, ["ts", "speed_kmh"]].to_string(index=False))
print("原因: '18. 3' 含数字内部空格，无法作为数值解析；read_csv 因此将整列读为字符串。")
