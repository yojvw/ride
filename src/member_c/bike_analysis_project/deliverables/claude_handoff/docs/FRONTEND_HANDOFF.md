# FRONTEND_HANDOFF：给 Claude 的前端数据说明

包版本 1.0.0；生成时间 2026-10-29T10:49:45Z。
本文件描述 data/summary.json 的结构、口径与展示规则。**前端不得自行修改统计口径，也不得硬编码任何成绩。**

## 1. 数据版本与模型版本

| 项 | 值 |
|---|---|
| 数据窗口 | 2024-01-01 00:00:00 至 2024-02-01 00:00:00 |
| rides.csv | 238,699 行，sha256 `02f37c8f6788d0a1…` |
| 覆盖区间 | 985 行，其中 assumed 985 行 |
| 站点 | 761 个 |
| 建模面板 | 20 站 × 744 小时 = 14,880 行 |
| 已确认模型 | `hgb_full`（real_run_01，测试已评估） |
| 候选模型 | 1 个，仅有验证成绩，**没有测试成绩** |

## 2. 三种口径（不能混用）

| 口径 | 行数 | 定义 |
|---|---:|---|
| 全量订单 | 238,699 | 分析窗口内按 started_at 统计的全部有效骑行 |
| 有起点的端点 | 201,574 | start_station_id 非空，可计入站点借出 |
| 有终点的端点（全量） | 199,070 | end_station_id 非空；包含 2 月 1 日到达的 35 条跨月订单 |
| 到达在窗口内的终点端点 | 199,053 | end_station_id 非空且 ended_at < 2024-02-01，可计入站点归还 |
| 起终点都有 | 183,870 | 可同时计入借出与归还 |
| 建模面板（20 站 × 744 h） | 14,880 | 仅覆盖选定 20 站的站点小时面板，与全量订单口径不同 |

`scope.warning` 已写入 JSON；任何图表若混合口径，必须标注清楚。

## 3. 顶层结构

| 键 | 类型 | 内容 |
|---|---|---|
| `meta` | object | 版本、时间口径、数据与模型版本、实验目录 |
| `scope` | object | 三种口径的定义与计数 |
| `overview` | object | 总量、日均、极值日、会员/车型占比 |
| `trends` | object | 每日序列、24 小时序列、星期×小时矩阵 |
| `member_bike` | object | 会员/车型构成、时长、交叉表、分小时占比 |
| `stations` | object | 761 站汇总、潮汐指标、20 站小时画像、代表站点 |
| `prediction` | object | 已确认模型的验证/测试指标、分小时误差、典型曲线 |
| `optimization` | object | 两轮候选实验（仅验证）、测试预算、入选候选 |
| `dispatch` | object | 条件性调度建议与缺口 |
| `findings` | array | 5 条核心发现 |
| `limitations` | array | 8 条限制 |
| `metrics_catalog` | object | 每个指标的单位/范围/口径/分母/来源/状态 |
| `figures` | array | 图表文件名清单 |
| `acceptance` | object | 导出时的验收结果 |

## 4. 关键字段与示例

### 4.1 趋势

```json
{"trends": {"daily": [{"date": "2024-01-01", "rides": 4898}],
            "hourly": [{"hour": 8, "rides_all": 18196, "weekday_mean": 717.4, "weekend_mean": 211.9}],
            "weekday_hour_mean": [[...24 个数...], ...7 行...]}}
```

单位：`rides` 次；`weekday_mean` 是“工作日该钟点的日均次数”，分母 23 个工作日；`weekend_mean` 分母 8 个周末日。

### 4.2 站点

```json
{"station_id": "31623", "station_name": "…", "lat": 38.897, "lng": -77.005,
 "departures": 2998, "arrivals": 2957, "net": 41, "events": 5955,
 "in_panel": true, "am_net": -2.46, "pm_net": 2.25, "reversal": true, "amplitude": 4.71}
```

- `departures/arrivals/net`：全月次数；`net = departures − arrivals`，**不是缺车量**。
- `am_net/pm_net`：06–09 时与 16–19 时的平均每小时净流出。
- `reversal`：早晚净流出符号相反。
- `in_panel`：是否属于 20 个建模站点（只有这 20 站有小时级面板与预测）。
- 潮汐汇总：355 个事件量 ≥200 的站点中 302 个反转（85.1%），上午/下午相关系数 -0.876。

### 4.3 预测

```json
{"split": "test", "target": "departures", "model": "hgb_full", "n": 3360,
 "mae": 1.4685, "rmse": 2.2184, "bias": -0.2886, "peak_mae": 2.8788,
 "peak_underprediction_rate": 0.8514, "interval_coverage": 0.9134,
 "interval_width": 5.634, "improvement_vs_previous_day": 0.3113}
```

- `split` ∈ {cv_1, cv_2, validation, test}；**测试与验证必须分开展示**。
- 只有 `hgb_full`（以及测试期的全部候选模型）有区间字段；其余为 null。
- `curves[].points[]` 字段：`time, actual, prediction, lower, upper`，按站点+目标严格对齐。

### 4.4 优化实验

```json
{"run_id": "opt_v021_001", "target": "arrivals", "model": "reg_leaf15_min30",
 "validation_mae": 1.1776, "relative_gain_vs_baseline": 0.0143,
 "paired_ci_low": -0.0286, "paired_ci_high": -0.0066, "test_mae": null,
 "status": "validation_only"}
```

**`test_mae` 恒为 null**：候选没有测试成绩，前端不得用任何数字填充。

### 4.5 调度建议

```json
{"station_id": "31602", "daily_net": 449, "am_net_per_hour": 2.1, "pm_net_per_hour": -1.4,
 "pattern": "早高峰净流出、晚高峰净流入",
 "suggested_action": "早间（约 06:30 前）优先补车；晚间（约 16:00–19:00）优先疏解",
 "missing_info": "站点容量、实时库存、调度车容量与成本、道路可达性均未提供"}
```

## 5. 四个页面

| 页面 | 主要数据 | 推荐图表 |
|---|---|---|
| 1 总览 | `meta`、`overview`、`trends.daily`、`findings` | 指标卡（总量/日均/会员占比/车型占比）、每日折线、发现列表 |
| 2 出行与站点 | `trends.hourly`、`weekday_hour_mean`、`member_bike`、`stations.list/profiles` | 小时曲线（工作日/周末）、星期×小时热力图、站点散点（事件量 vs 净流量）、潮汐四象限、代表站点累计曲线 |
| 3 预测评估 | `prediction.metrics/by_hour/curves`、`optimization` | 模型 MAE 条形图、分小时误差、预测曲线（含区间）、候选验证对比（标注“仅验证”） |
| 4 调度建议 | `dispatch.items`、`stations.tide_summary`、`limitations` | 站点优先级表、早晚方向箭头/象限图、缺口清单 |

## 6. 筛选条件与筛选后的口径

| 页面 | 可用筛选 | 说明 |
|---|---|---|
| 总览 | 日期范围 | 只能从 `trends.daily` 重新计算均值；不得把单日数字当全月 |
| 出行 | 工作日/周末、小时 | `hourly` 已给两种分母；前端不得把两种均值混算 |
| 站点 | 全部/仅建模 20 站/仅反转站/事件量阈值 | `stations.list` 是月汇总，筛选后仍是月汇总，不做时间加权 |
| 预测 | 划分（validation/test）、目标、模型 | 只能显示 JSON 中已有的组合；**禁止把验证成绩标成测试** |
| 优化 | 轮次、目标 | 只显示 `validation` 指标与 `test_mae: null` |

## 7. 缺失与未评估的展示规则

- 任何 `null` 显示为“暂无数据”或“—”，不得用 0 代替。
- 候选模型卡片必须写“仅有验证成绩，测试未评估”；不得出现测试分数、排名或“预计提升”。
- 调度页必须显示“未运行模拟”的提示：JSON `dispatch.simulation` 为 null。
- 站点页脚注必须写：净流量不是缺车量；容量/库存未知。
- 坐标标注为“站点中心估计值”，不得展示为精确门牌位置。

## 8. 更新方法

1. 修改 `handoff_config.json` 中的实验目录（或数据路径），不要按文件修改时间自动选择。
2. 在包根目录运行 `python scripts/export_all.py`（使用项目 `.venv`）。
3. 脚本会重新校验输入哈希、生成 JSON/图表/Notebook/HTML，并输出 `docs/ACCEPTANCE.md`。
4. 失败时脚本非零退出且不覆盖既有产物；不要手工编辑 JSON。

## 9. 前端禁止事项

- 不得修改 `scope` 定义或把不同口径的数字放在同一张图里不加说明。
- 不得把 `optimization.candidates[].test_mae` 填成任何数值。
- 不得从前端代码重新计算 MAE/RMSE（口径会漂移）；只显示 JSON 中的值。
- 不得编造库存、容量、天气、成本或“缺车率”。
