# 给 AI 的指令 —— Step 4 站点供需失衡分析（题目核心考点）

> 用法：复制下面代码块里的全部内容发给 AI。
> 「运行验收标准」那一段是给你自己对答案的，不要发给 AI。

```
【项目卡】
课程：上海大学《Python数据分析编程》小组项目（3人）
选题：题目五 城市共享单车出行时空分析与调度优化
数据：清洗后的数据存于 output/df_clean.pkl，233749 行
城市：华盛顿特区
字段：ride_id / rideable_type(electric_bike|classic_bike) / started_at / ended_at /
      start_station_name|id / end_station_name|id / start_lat|lng / end_lat|lng /
      member_casual(member|casual) / date / hour / dow / is_weekend / duration_min

重要：**起点或终点站点缺失的记录已统一标记为字符串「站点外停车」（共 35516 条起点缺失），
它不是 NaN**。站点维度的供需计算必须先把「站点外停车」排除掉，并在输出里说明排除了多少条；
禁止 dropna，也禁止把「站点外停车」当作一个站点参与排名。

已完成：
- step2 时间维度：峰值 17:00 共 23392 次，早高峰 8:00 共 17837 次；周三最高、周日最低；
  工作日日均 7838 次 vs 周末日均 6684 次；临时用户周末出行占比 28.22%（会员 21.01%）
- step3 空间维度：真实站点 759 个（按起点站名去重）；TOP1 = Columbus Circle / Union Station 2973 次；
  TOP20 仅占 16.86%（骑行高度分散）；平均直线距离 1.801 km，4.14% 为原地还车

硬约定：
- 禁止 dropna()；随机种子 random_state=42
- 建模（下一步）按时间切分：1/1-1/24 训练，1/25-1/31 测试；指标 RMSE/MAE/R²
环境：Python 3.14.6，已装 pandas 3.0.6 / numpy 2.5.1 / matplotlib 3.11.2 / seaborn 0.13.2 / sklearn 1.9.1
禁止使用未安装的库（folium / plotly / tqdm / statsmodels / jieba / geopy 都没有）。

【本步任务】写一个完整的 step4_supply_demand.py：
读取 output/df_clean.pkl，量化站点供需失衡，输出 2 张图 + 1 个结果表：

定义（按此实现）：
- 某站点的 inflow  = 以该站为「终点」的骑行次数
- 某站点的 outflow = 以该站为「起点」的骑行次数
- net_flow = inflow − outflow（正数=净流入，车会堆积；负数=净流出，车会被借空）
- 失衡指数 imbalance = |net_flow| / (inflow + outflow) × 100%
- 为避免小样本站点霸榜，排名时只统计全月进出总量 ≥ 100 次的站点，但要单独说明被过滤掉多少个

产出：
① output/top_imbalance_stations.csv：全部站点的一张表，列为
   station_name / inflow / outflow / total / net_flow / imbalance_pct
   按 net_flow 绝对值降序排列，用 utf-8-sig 编码保存（Excel 打开中文不乱码）

② fig08_top_imbalance.png：横向条形图一张
   取 net_flow 绝对值最大的 TOP20 站点（同上需 ≥100 次），正负用两种颜色区分
   （净流入=暖色、净流出=冷色），柱子上标注 net_flow 数值，0 位置画一条竖线

③ fig09_hour_netflow.png：全市净流量随时小时变化的图
   对「早高峰净流出型站点」（全天 net_flow 最负的 TOP20 个站点）和
   「晚高峰净流入型站点」（全天 net_flow 最正的 TOP20 个站点），
   分别统计它们按小时的净流量（inflow − outflow）合计，画两条折线，0 点画水平参考线
   用以证明"早/晚高峰潮汐"的存在

要求：
- 脚本开头 matplotlib.use('Agg')，不要 plt.show()
- 图中中文正常显示：plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
- 每张图有标题和坐标轴标签
- 关键数字 print 出来（见下方六项）
- 全部中文注释

需要打印的数字：
1) 排除了多少条含「站点外停车」的记录（起点缺失 / 终点缺失分别多少）
2) 参与统计的站点总数，其中「进出总量 ≥100 次」的站点数、被过滤的站点数
3) 净流出最多的 TOP10 站点（站名、inflow、outflow、net_flow）
4) 净流入最多的 TOP10 站点（同上字段）
5) 失衡指数最高的 TOP10 站点（站名、total、net_flow、imbalance_pct）
6) 全市净流量的绝对值之和（可用于估算理论上的每日调度车次需求），
   以及早高峰型站点的最净流出小时、晚高峰型站点的最净流入小时
```

---

## 运行验收标准（自己留着对，不要发给 AI）

| 应该看到 | 参考值 |
|---|---|
| 参与统计的站点总数 | 762（起点/终点站名合并去重） |
| ≥100 次的站点数 | 454 个 |
| 净流出最多的站 | Park Rd & Holmead Pl NW，inflow 727 / outflow 1164 / net −437 |
| 净流入最多的站 | Thomas Jefferson St NW & Water/K St NW，inflow 555 / outflow 326 / net +229 |
| 失衡指数最高 | Wilson Blvd & Ft Myer Dr，28.81% |
| 全市 \|net\| 合计 | 15,068 |

> 注：站点总数若按起点站名去重是 759，按起点∪终点合并去重是 762，两种口径都对，
> 只要脚本里说明清楚即可。

## 跑完后提交 GitHub

Summary 填：`step4: 站点供需失衡分析（TOP20 失衡站点 + 早晚高峰潮汐）`
然后 Commit to main → Push origin（报 SSL 错多点几次）
