# v0.2.1 对照实验：特征精简 / 正则化 / 在线误差修正

run_id：opt_v021_001　候选：8 个（不交叉组合）

测试集未评分；所有候选只在此前的滚动 CV 与验证窗上比较，样本掩码与原 `hgb_full` 完全一致。

## 1. 基线复现

- 状态：validation_baseline_reproduced
- 验证期逐样本最大差：1.7763568394002505e-15（n=5760）

## 2. 验证集结果（每目标 2,880 行）

| 目标 | 模型 | MAE | 相对基线 | RMSE | 偏差 | 峰值 MAE | 峰值欠预测率 |
|---|---|---:|---:|---:|---:|---:|---:|
| departures | online_ema_050 | 1.1441 | +1.77% | 1.7583 | -0.097 | 3.3473 | 0.9522 |
| departures | online_ema_025 | 1.1504 | +1.23% | 1.7653 | -0.082 | 3.3755 | 0.9556 |
| departures | reg_leaf15_min30 | 1.1557 | +0.77% | 1.7614 | -0.066 | 3.3532 | 0.9522 |
| departures | reg_leaf8_min30 | 1.1603 | +0.38% | 1.7739 | -0.061 | 3.4665 | 0.9625 |
| departures | hgb_full **(保留)** | 1.1648 | +0.00% | 1.7786 | -0.060 | 3.4073 | 0.9590 |
| departures | reg_leaf8_min15 | 1.1684 | -0.32% | 1.7741 | -0.051 | 3.4547 | 0.9693 |
| departures | feat_same_hour_7d | 1.1697 | -0.43% | 1.8221 | -0.192 | 3.7021 | 0.9625 |
| departures | feat_mean168 | 1.1748 | -0.86% | 1.8025 | -0.088 | 3.5107 | 0.9761 |
| departures | feat_ewm72 | 1.1758 | -0.95% | 1.7990 | -0.086 | 3.4622 | 0.9522 |
| arrivals | reg_leaf8_min15 | 1.1740 | +1.73% | 1.8464 | -0.107 | 3.7249 | 0.9386 |
| arrivals | reg_leaf15_min30 | 1.1776 | +1.43% | 1.8440 | -0.082 | 3.6497 | 0.9061 |
| arrivals | reg_leaf8_min30 | 1.1818 | +1.08% | 1.8609 | -0.093 | 3.7544 | 0.9350 |
| arrivals | online_ema_050 | 1.1875 | +0.60% | 1.8668 | -0.076 | 3.6364 | 0.9134 |
| arrivals | online_ema_025 | 1.1881 | +0.55% | 1.8709 | -0.075 | 3.6718 | 0.9170 |
| arrivals | feat_mean168 | 1.1894 | +0.44% | 1.8654 | -0.080 | 3.6653 | 0.9134 |
| arrivals | hgb_full **(保留)** | 1.1947 | +0.00% | 1.8796 | -0.071 | 3.7074 | 0.9206 |
| arrivals | feat_ewm72 | 1.1983 | -0.31% | 1.8840 | -0.084 | 3.7487 | 0.9206 |
| arrivals | feat_same_hour_7d | 1.2046 | -0.83% | 1.8908 | -0.192 | 3.9022 | 0.9458 |

## 3. 滚动 CV（两折加权 MAE）

| 目标 | 模型 | CV 加权 MAE | 相对基线 |
|---|---|---:|---:|
| departures | reg_leaf8_min30 | 1.0128 | +2.17% |
| departures | online_ema_025 | 1.0257 | +0.93% |
| departures | reg_leaf8_min15 | 1.0260 | +0.89% |
| departures | online_ema_050 | 1.0266 | +0.84% |
| departures | hgb_full | 1.0353 | +0.00% |
| departures | reg_leaf15_min30 | 1.0371 | -0.17% |
| departures | feat_same_hour_7d | 1.0567 | -2.06% |
| departures | feat_mean168 | 1.0638 | -2.76% |
| departures | feat_ewm72 | 1.0666 | -3.02% |
| arrivals | online_ema_050 | 1.0458 | +1.83% |
| arrivals | online_ema_025 | 1.0498 | +1.45% |
| arrivals | hgb_full | 1.0653 | +0.00% |
| arrivals | reg_leaf8_min30 | 1.0726 | -0.69% |
| arrivals | reg_leaf15_min30 | 1.0753 | -0.94% |
| arrivals | reg_leaf8_min15 | 1.0873 | -2.07% |
| arrivals | feat_ewm72 | 1.1098 | -4.17% |
| arrivals | feat_same_hour_7d | 1.1271 | -5.80% |
| arrivals | feat_mean168 | 1.1315 | -6.21% |

## 4. 配对日块 bootstrap（候选 − 基线，负数=更好，6 个日块）

| 目标 | 模型 | 差值 | 95% 区间 | 上界<0 |
|---|---|---:|---|---|
| arrivals | reg_leaf8_min15 | -0.0206 | [-0.0506, -0.0003] | 是 |
| arrivals | reg_leaf15_min30 | -0.0170 | [-0.0286, -0.0066] | 是 |
| arrivals | reg_leaf8_min30 | -0.0129 | [-0.0474, +0.0157] | 否 |
| arrivals | online_ema_050 | -0.0071 | [-0.0293, +0.0248] | 否 |
| arrivals | online_ema_025 | -0.0065 | [-0.0187, +0.0102] | 否 |
| arrivals | feat_mean168 | -0.0052 | [-0.0210, +0.0128] | 否 |
| arrivals | hgb_full | +0.0000 | [+0.0000, +0.0000] | 否 |
| arrivals | feat_ewm72 | +0.0037 | [-0.0085, +0.0158] | 否 |
| arrivals | feat_same_hour_7d | +0.0099 | [-0.0108, +0.0320] | 否 |
| departures | online_ema_050 | -0.0206 | [-0.0553, +0.0176] | 否 |
| departures | online_ema_025 | -0.0144 | [-0.0336, +0.0059] | 否 |
| departures | reg_leaf15_min30 | -0.0090 | [-0.0191, +0.0014] | 否 |
| departures | reg_leaf8_min30 | -0.0045 | [-0.0245, +0.0098] | 否 |
| departures | hgb_full | +0.0000 | [+0.0000, +0.0000] | 否 |
| departures | reg_leaf8_min15 | +0.0037 | [-0.0187, +0.0229] | 否 |
| departures | feat_same_hour_7d | +0.0050 | [-0.0162, +0.0292] | 否 |
| departures | feat_mean168 | +0.0100 | [-0.0046, +0.0278] | 否 |
| departures | feat_ewm72 | +0.0111 | [-0.0062, +0.0334] | 否 |

## 5. 选择结论

- 借出：hgb_full　归还：reg_leaf15_min30

## 6. 门槛判定（每候选）

| 目标 | 模型 | 相对增益 | CV 不退化 | 峰值不恶化 | 区间上界<0 | 入选 |
|---|---|---:|---|---|---|---|
| arrivals | feat_ewm72 | -0.31% | 否 | 否 | 否 | 否 |
| arrivals | feat_mean168 | +0.44% | 否 | 是 | 否 | 否 |
| arrivals | feat_same_hour_7d | -0.83% | 否 | 否 | 否 | 否 |
| arrivals | hgb_full | +0.00% | 是 | 是 | 否 | 否 |
| arrivals | online_ema_025 | +0.55% | 是 | 是 | 否 | 否 |
| arrivals | online_ema_050 | +0.60% | 是 | 是 | 否 | 否 |
| arrivals | reg_leaf15_min30 | +1.43% | 是 | 是 | 是 | 是 |
| arrivals | reg_leaf8_min15 | +1.73% | 否 | 否 | 是 | 否 |
| arrivals | reg_leaf8_min30 | +1.08% | 是 | 否 | 否 | 否 |
| departures | feat_ewm72 | -0.95% | 否 | 否 | 否 | 否 |
| departures | feat_mean168 | -0.86% | 否 | 否 | 否 | 否 |
| departures | feat_same_hour_7d | -0.43% | 否 | 否 | 否 | 否 |
| departures | hgb_full | +0.00% | 是 | 是 | 否 | 否 |
| departures | online_ema_025 | +1.23% | 是 | 是 | 否 | 否 |
| departures | online_ema_050 | +1.77% | 是 | 是 | 否 | 否 |
| departures | reg_leaf15_min30 | +0.77% | 是 | 是 | 否 | 否 |
| departures | reg_leaf8_min15 | -0.32% | 是 | 否 | 否 | 否 |
| departures | reg_leaf8_min30 | +0.38% | 是 | 否 | 否 | 否 |

## 7. 口径说明

- 特征类候选只改“新增哪一对统计量”，其余与原模型一致；特征全部由 shift(1) 之后的过去值计算。
- 正则化类候选只改 (max_leaf_nodes, min_samples_leaf)，其余超参与原模型相同。
- 在线修正候选：每折独立、按站点与目标维护 EWM(实际−原预测)，半衰期 24 h，先预测后更新，修正值下限 0；
  其信息集与 1 小时滚动预测一致（第 t 小时只用到 t−1 及更早的实际值）。
- 同一验证集已被反复使用，选择后区间未做多重比较校正；只能作为保守筛选依据。
- 测试期（1/25–2/1）从头到尾没有被评分，测试预算未消耗。
