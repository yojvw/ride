# 给 AI 的指令 —— Step 2 时间维度分析

> 用法：把下面整个代码块里的内容全部复制，发给 AI。
> AI 回复代码后，按 README 的方式运行。

```
【项目卡】
课程：上海大学《Python数据分析编程》小组项目（3人）
选题：题目五 城市共享单车出行时空分析与调度优化
数据：data/题5_共享单车骑行_202401.csv，238834行×13列，2024-01-01~2024-01-31，华盛顿特区
字段：ride_id / rideable_type(electric_bike|classic_bike) / started_at / ended_at /
      start_station_name|id / end_station_name|id / start_lat|lng / end_lat|lng /
      member_casual(member|casual)

已完成 step1 清洗，清洗后数据保存在 output/df_clean.pkl，已含衍生列：
date / hour / dow(0=周一) / is_weekend / duration_min
缺失站点已统一填为字符串「站点外停车」（不是 NaN）。

清洗后真实数字（结论必须基于这些，不得编造）：
- 行数 233749；时长中位数 8.92 分钟
- member 173286 / casual 60463
- electric_bike 118803 / classic_bike 114946
- 「站点外停车」35516 条

硬约定：
- 禁止 dropna()
- random_state=42；建模按时间切分：1/1-1/24 训练，1/25-1/31 测试；指标 RMSE/MAE/R²
环境：Python 3.14.6，已装 pandas 3.0.6 / numpy 2.5.1 / matplotlib 3.11.2 / seaborn 0.13.2 / sklearn 1.9.1
禁止使用未安装的库（folium / plotly / tqdm / statsmodels / jieba 都没有）。

【本步任务】写一个完整的 step2_time_analysis.py：
读取 output/df_clean.pkl，做时间维度分析，输出 4 张图到 figures/（dpi=150）：
① fig01_hourly.png：按小时骑行量折线图，member 与 casual 两条线，标注早晚双峰
② fig02_weekday.png：按星期（周一~周日）骑行量柱状图
③ fig03_daily.png：按日期（1~31日）骑行量折线图，标出最高与最低的那天
④ fig04_heatmap.png：小时×星期的骑行量热力图（seaborn）

要求：
- 脚本开头用 matplotlib.use('Agg')，不要 plt.show()
- 图中中文正常显示：plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
- 每张图有标题和坐标轴标签
- 关键数字 print 出来：峰值小时及次数、最低小时、工作日总量 vs 周末总量、casual 与 member 的周末/工作日占比差异
- 全部中文注释
```

---

## 运行验收标准（数字对不上就说明有问题）

| 应该看到 | 参考值 |
|---|---|
| figures/ 里出现 4 张 png | — |
| 峰值小时 | 17 点（约 23000+ 次），次峰 8 点 |
| 星期最高 | 周三附近；最低周日 |
| 工作日总量 | 明显高于周末 |

## 跑完后提交 GitHub（Desktop 三步）

1. Desktop 会自动显示变更的文件
2. 左下角 Summary 填：`step2: 时间维度分析（小时/星期/日期/热力图）`
3. 点 `Commit to main` → 顶部点 `Push origin`
