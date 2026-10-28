# 给 AI 的指令 —— Step 3 空间维度分析

> 用法：复制下面代码块里的全部内容发给 AI。
> 「运行验收标准」那一段是给你自己对答案的，不要发给 AI。

```
【项目卡】
课程：上海大学《Python数据分析编程》小组项目（3人）
选题：题目五 城市共享单车出行时空分析与调度优化
数据：清洗后的数据存于 output/df_clean.pkl，233749 行
城市：华盛顿特区（纬度约 38.78~39.13，经度约 -77.37~-76.83）
字段：ride_id / rideable_type(electric_bike|classic_bike) / started_at / ended_at /
      start_station_name|id / end_station_name|id / start_lat|lng / end_lat|lng /
      member_casual(member|casual) / date / hour / dow / is_weekend / duration_min

重要：**起点站点缺失的记录已统一标记为字符串「站点外停车」（共 35516 条），
它不是 NaN**。做站点维度统计时必须先把「站点外停车」这一项单独排除，
并在输出中说明排除了多少条；禁止用 dropna，也禁止把「站点外停车」算作一个站点。

已完成：step2 时间维度分析（结论：峰值 17:00 共 23392 次，早高峰 8:00；
周三最高 44916、周日最低 25076；工作日:周末日均比 1.17:1；
临时用户周末出行占比 28.22%，比会员 21.01% 高 7.2 个百分点）。

硬约定：
- 禁止 dropna()；随机种子 random_state=42
- 建模按时间切分：1/1-1/24 训练，1/25-1/31 测试；指标 RMSE/MAE/R²
环境：Python 3.14.6，已装 pandas 3.0.6 / numpy 2.5.1 / matplotlib 3.11.2 / seaborn 0.13.2 / sklearn 1.9.1
禁止使用未安装的库（folium / plotly / tqdm / statsmodels / jieba / geopy 都没有）。

【本步任务】写一个完整的 step3_space_analysis.py：
读取 output/df_clean.pkl，做空间维度分析，输出 3 张图到 figures/（dpi=150）：

① fig05_start_scatter.png：起点地理位置散点图
   - 横轴 start_lng、纵轴 start_lat，点要半透明（alpha 0.1~0.2）且尺寸小
   - 数据量大于 5 万时先随机抽样再画（用 random_state=42），避免图糊成一团
   - 坐标轴等比例（ax.set_aspect('equal')），否则地图形状会被拉歪

② fig06_top_stations.png：TOP20 热门起点站横向条形图
   - 排除「站点外停车」后再统计
   - 从高到低排列，柱子上标注次数
   - 分会员 / 临时用户两组颜色堆叠展示（可选，能用就做）

③ fig07_distance.png：骑行直线距离分布直方图
   - 用起点和终点经纬度按球面距离（Haversine 公式，地球半径 6371 km）计算直线距离
   - 只画 0~10 km 区间，超出部分计入最右一个 bin，标注被截断的条数
   - 用两条不同颜色的线标出中位数与均值

要求：
- 脚本开头 matplotlib.use('Agg')，不要 plt.show()
- 图中中文正常显示：plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
- 每张图有标题和坐标轴标签
- 关键数字 print 出来（见下方五项）
- 全部中文注释

需要打印的数字：
1) 排除了多少条「站点外停车」记录，剩下的有效有站点记录数、真实站点总数
2) TOP10 热门起点站的站名与骑行次数，以及 TOP10 / TOP20 站点占全部有站点记录的比例
3) 起点经纬度范围、中心点（经纬度均值）
4) 骑行直线距离的中位数、均值、最大值，以及起终点重合（<50 米，视为原地还车）的占比
5) 会员与临时用户的平均直线距离分别是多少（谁骑得更远）
```

---

## 运行验收标准（自己留着对，不要发给 AI）

| 应该看到 | 参考值 |
|---|---|
| 「站点外停车」条数 | 35,516 |
| 排除后有效记录 | 198,233 |
| 真实站点总数 | 759 个 |
| TOP1 热门起点站 | Columbus Circle / Union Station（约 2,973 次） |
| TOP10 / TOP20 占比 | 约 9.9% / 16.9%（说明骑行很分散） |
| 直线距离中位数 / 均值 | 约 1.46 km / 1.80 km |
| 原地还车（<50 m）占比 | 约 4.1% |

## 跑完后提交 GitHub

Summary 填：`step3: 空间维度分析（散点地图/热门站点/距离分布）`
然后 Commit to main → Push origin（报 SSL 错多点几次）
