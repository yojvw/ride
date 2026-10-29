# 图表清单

| 文件 | 标题 | 单位 | 状态 | 来源 |
|---|---|---|---|---|
| `figures/fig01_daily_trips.png` | 每日观测骑行量 | 次/日 | observed | data/clean/rides.csv |
| `figures/fig02_hourly_profile.png` | 工作日/周末日均小时曲线 | 次/（日·小时） | observed | data/clean/rides.csv |
| `figures/fig03_weekday_hour_heatmap.png` | 星期×小时平均骑行量 | 次/（日·小时） | observed | data/clean/rides.csv |
| `figures/fig04_member_bike.png` | 会员/车型构成与时长 | 次；分钟 | observed | data/clean/rides.csv |
| `figures/fig05_station_scatter.png` | 站点事件量与净流量 | 次；次（净） | observed | data/clean/rides.csv |
| `figures/fig06_tide_scatter.png` | 早晚净流出四象限（潮汐） | 次/小时 | observed | data/clean/rides.csv |
| `figures/fig07_representative_cumulative.png` | 代表站点日内累计净流量 | 次（累计） | observed | data/clean/rides.csv；单日 2024-01-10 |
| `figures/fig08_prediction_models.png` | 确认模型在测试集的 MAE 对比 | 辆/站·小时 | prediction | results/real_run_01/tables/predictions.csv；模型 hgb_full 等 5 个 |
| `figures/fig09_prediction_hourly.png` | 分小时误差（测试集） | 辆/站·小时 | prediction | results/real_run_01/tables/predictions.csv；模型 hgb_full |
| `figures/fig10_candidate_validation.png` | 两轮候选的验证集相对增益 | %（相对基线 MAE） | validation_experiment | experiments/opt_v020_001；experiments/opt_v021_001；仅验证集 |
| `figures/fig11_prediction_example.png` | 预测示例（31623 借出，测试前 72 小时） | 次/小时 | prediction | results/real_run_01/tables/predictions.csv |

状态说明：observed = 观测；prediction = 冻结预测；validation_experiment = 仅验证集实验。
所有图表由 `scripts/export_all.py` 用同一版数据生成，Notebook 中显示的是同一批 PNG。
