# 5 条核心发现

每条都给出数字、数据范围与对应图表/数据文件。数字来自 data/summary.json。

## F1 工作日双峰、周末单峰，城市级需求集中度很高

工作日 08:00 均值 717 次/日、17:00 874 次/日；周末峰值在 14:00（602 次/日）。全月最高小时为 17:00（23,845 次）。

- 数据范围：全量订单 238,699 条，2024-01-01 至 2024-02-01（按 started_at）
- 来源：data/summary.json → trends.hourly；figures/fig02_hourly_profile.png
- 图表：`figures/fig02_hourly_profile.png`

## F2 站点级潮汐普遍存在，早晚方向系统性反转

355 个事件量 ≥200 的站点中 85.1%（302 个）早晚净流出符号相反；上午与下午净流出的相关系数 -0.876。

- 数据范围：全量订单的站点端点，上午 06–09 时、下午 16–19 时
- 来源：data/summary.json → stations.tide；figures/fig06_tide_scatter.png
- 图表：`figures/fig06_tide_scatter.png`

## F3 “热门站点”不等于“净流出站点”

事件量前 20 与净流量绝对值前 20 只有 2 个重合；最大站 31623（5,955 次）净流量仅 +41，而净流出最高的是 31602（+449），净流入最高的是 31293（-228）。

- 数据范围：761 个有站点端点的站点，2024-01 全月
- 来源：data/summary.json → stations.list；figures/fig05_station_scatter.png
- 图表：`figures/fig05_station_scatter.png`

## F4 已确认模型的预测明显优于基线，但高峰仍被低估

确认模型 hgb_full 测试期 MAE 借出 1.4685 / 归还 1.4801，较“昨日同小时”基线改善 31.1% / 28.5%；但峰值样本欠预测率仍有 85.1% / 82.4%。

- 数据范围：20 个建模站点，测试期 2024-01-25 至 2024-02-01，共 3,360 行/目标
- 来源：data/summary.json → prediction；figures/fig09_prediction_hourly.png
- 图表：`figures/fig09_prediction_hourly.png`

## F5 两轮优化实验只有 1 个候选通过验证门槛，且尚无测试成绩

两轮共 13 个候选，仅 1 个通过预注册门槛：arrivals → reg_leaf15_min30。该候选只有验证集成绩，测试期未评分。

- 数据范围：experiments/opt_v020_001、experiments/opt_v021_001（仅验证集与滚动 CV）
- 来源：data/summary.json → optimization；figures/fig10_candidate_validation.png
- 图表：`figures/fig10_candidate_validation.png`

