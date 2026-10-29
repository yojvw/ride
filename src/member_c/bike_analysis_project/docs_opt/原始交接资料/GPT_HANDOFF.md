# 再交接文档：给下一位算法优化者（GPT）

> 你拿到的不是半成品，而是一条**已经跑通、已经有真实数字、也有已知缺陷**的流水线。
> 你的任务是把它做得更好，同时**不要**用随机切分、测试集调参、编造数据把它做“好看”。
> 本文自包含：读完前 5 节即可独立开工，不需要原始对话。

---

## 0. 一页现状

| 项 | 现状 |
|---|---|
| 项目 | 共享单车题目五：数据清洗 → 站点小时面板 → 时空分析 → 借还预测 → 时间验证 → 调度情景回放 |
| 数据 | Capital Bikeshare 风格月表（华盛顿特区），2024-01，238,699 条有效骑行，761 站 |
| 已完成 | 清洗与接口验收、coverage/stations 交付、26 项单元测试、真实数据全流程运行 |
| 当前模型 | 5 个固定候选，验证集按 MAE 选出 `hgb_full`（Poisson 损失的梯度提升树） |
| 当前成绩（测试集 1/25–2/1） | MAE 借出 **1.4685**、归还 **1.4801**；较昨日同小时基线改善 **31.1% / 28.5%** |
| 当前短板 | 高峰系统性低估（17 点偏差 −1.56）、零膨胀未建模、训练期每站仅 264 h、测试集仅 7 天 |
| 你的产出 | 在**不污染测试集**的前提下，把验证集与测试集的误差降下来，并把结论写清楚 |

---

## 1. 五条硬约束（违反任何一条，结果作废）

1. **时间切分固定**：训练 < 2024-01-19 00:00，验证 [01-19, 01-25)，测试 [01-25, 02-01)。禁止随机打乱、禁止 KFold、禁止把测试小时混进训练。
2. **测试集只能用于最终评估**。所有选择（模型、特征、超参、阈值、区间方法）只能用验证集或滚动 CV。同一个测试集反复挑模型 = 测试集失效。
3. **特征只能看 t 之前**。任何滞后必须 ≥1 小时；滚动统计必须先 `shift(1)`；不得把目标小时的会员订单数、当日总量、未来订单作为输入；不得跨站点 shift。
4. **不得编造数据**。没有库存、容量、天气、节假日、成本观测就如实说没有。外部数据（如真实天气）若使用，必须写明来源、覆盖时段，并在报告中单列。
5. **不得改测试断言或校验代码来让结果通过**。`tests/`、`bikeproject/io.py` 的校验是契约的一部分；数据不合格就回去修数据或如实报告。

---

## 2. 文件地图

| 路径 | 作用 | 你可以动吗 |
|---|---|---|
| `data/clean/rides.csv` | 清洗后订单（19 列） | 不可手改；只能改 `scripts/clean_data.py` 后重跑 |
| `data/clean/coverage.csv` | 985 段站点可用区间，全部 `assumed` | 同上 |
| `data/clean/stations.csv` | 761 站坐标 | 同上 |
| `data/clean/cleaning_report.json` | 清洗统计与假设 | 自动生成 |
| `configs/real_template.json` | 真实运行配置 | **可以改**（改 output_dir、max_iter 等；time_basis 不得留占位） |
| `bikeproject/panel.py` | 选站、覆盖感知面板、特征 | 可以改（改完必须重跑测试） |
| `bikeproject/forecast.py` | 候选模型、训练、预测、选择 | 主战场 |
| `bikeproject/evaluation.py` | MAE/RMSE/偏差/峰值/区间 | 可以加指标，不许删旧指标 |
| `bikeproject/io.py` | 配置与输入校验 | **不要放宽** |
| `bikeproject/main.py` | 管线与日志 | 只做加法 |
| `tests/` | 26 项断言 | 只可新增，不可删改 |
| `results/real_run_01/` | 本轮基线产物 | 只读；新实验另开 output_dir |

---

## 3. 数据事实卡

### 3.1 输入与哈希

| 文件 | 行数 | sha256 前 16 位 |
|---|---:|---|
| rides.csv | 238,699 | `02f37c8f6788d0a1` |
| coverage.csv | 985 | `7f2c46f14e866fe1` |
| stations.csv | 761 | `e59fa4f4d182d090` |

原始 CSV sha256 `bb189909da35620f`，副本在 `data/raw/`（未改动）。

### 3.2 rides.csv 契约

必需列：`ride_id, started_at, ended_at, start_station_id, end_station_id, member_type, bike_type`；建议列：`duration_min, start/end_lat/lng, quality_flags, source_file, source_row, start/end_station_name`。
时区：**America/New_York 当地墙钟、naive 时间戳**，1 月无夏令时；跨月订单保留（35 条 1/31 借、2/1 还）。

### 3.3 质量数字（必须记住）

| 事实 | 数字 | 对算法的含义 |
|---|---:|---|
| 无起点站的行程 | 15.55% | 这部分“借出”不在任何站点的 departures 里 → 站级借出系统性偏低 |
| 无终点站的行程 | 16.60% | 归还同理 |
| 电动车端点缺站占比 | 30.4% / 32.3% | 缺站几乎只发生在电动车上（自由停放） |
| 经典车端点缺站占比 | 0% / 0.19% | 经典车基本都入桩 |
| 时长 ≥24 h（疑似 25 h 封顶） | 228 条 | 不能当真实长骑行；建议做“剔除 vs 截尾”敏感性 |
| 时长 ≥180 min | 797 条 | 已标记，未删除 |
| 起点坐标离站 >200 m（已置空） | 253 条 | 不要用这些行做空间统计 |
| 无站点端点坐标精度 | 2 位小数（≈1 km） | 不可当精确位置 |
| 被拒绝行 | 135 条（44 负时长 + 91 零时长） | 已在 `rejected_rows.csv` |

### 3.4 coverage / stations 的可信度

- **985 段全部 `assumed`**：没有运营日志，无法标 confirmed。下游必须显式 `allow_assumed_coverage=true` 才加载。
- 区间 = [首个有活动日 00:00, 末个有活动日次日 00:00)，内部“不可信沉默”被挖空（182 站、947 天）。
- 由此：**top-20 站的 744 h 全部是观测**，本轮没有任何样本因覆盖缺口丢失；但换成低流量站就会遇到 NaN。
- `stations.csv` 只有坐标，没有容量/桩数——**容量是未知量**。

### 3.5 现在**没有**的信息

站点容量、实时库存、开关站日志、天气、节假日标签、成本、真实缺车量。
→ 任何涉及这些的结论都必须写成“情景假设”，不能写成观测。

---

## 4. 当前算法（精确到可复现）

### 4.1 面板

1. 候选站 = coverage 中的 761 站；统计**训练窗口**（< 2024-01-15）的端点事件（借出 + 归还），≥50 的 454 站；
2. 取前 20 站（`max_stations=20`）；
3. 时间轴 = 744 个整点；覆盖区间内的小时 `observed=True`，否则目标置 NaN；
4. `departures` 按 `started_at` 落小时，`arrivals` 按 `ended_at` 落小时，站外行程不计数；
5. `net_outflow = departures − arrivals`（描述性，**不是**缺车量）。

### 4.2 特征（25 个数值 + 20 个站点哑变量）

- 日历 7 个：`hour, weekday, weekend, hour_sin, hour_cos, weekday_sin, weekday_cos`
- 每目标 9 个：`lag_1, lag_2, lag_3, lag_24, lag_168, mean_3, mean_24, std_24`（先 shift(1) 再 rolling，按站点分组）
- 借出与归还各一套 → 18 个；加日历 7 个 = 25；
- 站点 one-hot 20 列；
- 样本资格：`[target] + 25 个特征` 全部非空。168 h 暖启动因此固定排除 3,360 行。

### 4.3 模型

`HistGradientBoostingRegressor(loss='poisson', max_iter=80, max_leaf_nodes=15, min_samples_leaf=15, l2_regularization=1.0, early_stopping=False, random_state=42)`
区间：同结构 `loss='quantile'`，q=0.05/0.95，交叉时排序。

### 4.4 候选与选择

`previous_day`（lag_24）、`historical_mean`（训练期 站点×星期×小时 均值）、`hgb_calendar`、`hgb_own_history`、`hgb_full`。
**验证集 MAE 最小者胜出**，测试集只评估。当前两目标都选 `hgb_full`。

### 4.5 环境与命令

```powershell
cd "D:\新建文件夹 (4)\bike_analysis_project"
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe run.py --config configs\real_template.json
```

**环境陷阱**：本机全局 Python 是 pandas 3.0.5，`io.py` 的纳秒 dtype 断言会误报；项目按 `requirements-tested.txt` 在 `.venv` 中固定为 pandas 2.2.3 / numpy 1.26.4 / sklearn 1.6.1。**请用 `.venv\Scripts\python.exe` 运行**，不要为了迁就 pandas 3 去改校验。

---

## 5. 基线成绩（不许悄悄丢掉这张表）

### 5.1 测试集（3,360 行/目标，7 天）

| 目标 | 模型 | MAE | RMSE | 偏差 | 峰值 MAE | 区间覆盖 |
|---|---|---:|---:|---:|---:|---:|
| 借出 | **hgb_full** | **1.4685** | 2.2184 | −0.289 | 2.879 | 91.3% |
| 借出 | hgb_own_history | 1.5463 | 2.3394 | −0.313 | 3.067 | — |
| 借出 | previous_day | 2.1321 | 3.2186 | −0.013 | 3.710 | — |
| 归还 | **hgb_full** | **1.4801** | 2.2738 | −0.215 | 3.079 | 91.6% |
| 归还 | hgb_own_history | 1.4890 | 2.3062 | −0.278 | 3.151 | — |
| 归还 | previous_day | 2.0690 | 3.2311 | +0.011 | 3.850 | — |

### 5.2 验证集（选模型的唯一依据）

| 目标 | hgb_full | own_history | calendar | historical_mean | previous_day |
|---|---:|---:|---:|---:|---:|
| 借出 | **1.1648** | 1.2645 | 1.5658 | 1.7500 | 1.4715 |
| 归还 | **1.1947** | 1.2196 | 1.5436 | 1.6793 | 1.4361 |

### 5.3 噪声地板（按天块 bootstrap，2000 次，7 个日块）

| 比较 | 差值 | 95% 区间 | 结论 |
|---|---:|---|---|
| 借出 full − own_history | −0.0778 | [−0.107, −0.045] | 稳定优于 own_history |
| 归还 full − own_history | −0.0088 | [−0.022, +0.004] | **在噪声内**，别宣称更好 |
| 借出 full − previous_day | −0.6636 | [−0.920, −0.439] | 明显更好 |
| 归还 full − previous_day | −0.5889 | [−0.838, −0.367] | 明显更好 |

单看 MAE 的 95% 区间：借出 [1.30, 1.64]，归还 [1.30, 1.68]。
**判据：验证集上 MAE 改善 < 2% 基本是噪声；任何“提升”都要给出按天块 bootstrap 的配对区间。**

复现上面这张表：

```powershell
.venv\Scripts\python.exe scripts\block_bootstrap.py --predictions results\real_run_01\tables\predictions.csv --split test
.venv\Scripts\python.exe scripts\block_bootstrap.py --predictions <新实验>\tables\predictions.csv --split validation
```

---

## 6. 诊断：钱在哪里（都有证据）

1. **高峰低估是最大的一块**（借出）：小时 17 偏差 **−1.56**、小时 16 −0.97、小时 8 −0.88；峰值样本欠预测率 **85%**。16–18 点合计贡献 −2.64，占逐小时偏差总和 −6.93 的 **38%**（17 点单小时就占 23%）；24 个钟头平均后即总偏差 −0.289。
2. **零膨胀没建模**：29.9%（借出）/31.7%（归还）的实际值为 0，模型**从不预测 0**。夜间小时 MAE 0.19 看着低，但那是零样本堆出来的；真正的损失在“0 被预测成 1”。
3. **水平漂移**：测试周均值 3.04 vs 训练 2.08（+46%），模型跟着 168 h 前的水平走，跟不上。
4. **站点异质性**：MAE 1.14–2.30；最大站 31623 贡献了最多绝对误差。
5. **样本太少**：训练期每站只有 264 行（432 h 扣 168 h 暖启动），站点×星期×小时每格平均 1.6 个样本 → 树模型学不到细粒度周期。
6. **口径缺口**：15.6%/16.6% 的端点没有站点，站级借还只是“有站点记录的部分”，任何站级需求结论都有这个偏差。

---

## 7. 优化路线图（按 ROI 排序）

### P0 实验基建（先做，1 天以内）

1. **试验台账** `experiments/ledger.csv`：每次运行追加一行（见第 8 节模板）。
2. **同掩码断言**：所有模型必须在同一 `(split,target)` 样本上评估（验证 2,880、测试 3,360）；不一致就报错。
3. **测试预算**：整个优化周期测试集最多评估 **3 次**，其余全部看验证集 + CV。
4. **复现基线**：先重跑一次 `real_template.json`，确认 MAE 与 5.1 一致（同哈希、同版本）。

验收：台账有 1 行基线；重跑误差 <1e-9。

### P1 特征（预期收益最大，风险低）

| 想法 | 做法 | 预期 | 风险 |
|---|---|---|---|
| 周期均值 | 加 `mean_168`（过去一周同站点均值，shift(1)） | 抗水平漂移 | 暖启动从 168 → 336 h，样本更少 |
| 指数加权 | `ewm(halflife=24/72).mean().shift(1)` | 跟随近期水平 | 参数需验证集选 |
| 周内交互 | `weekday×hour` 的类别编码或目标编码（只用训练期统计） | 抓工作日/周末差异 | 目标编码必须时间安全 |
| 节假日 | 真实美国联邦假日（1/1 元旦、1/15 MLK）+ 可能的 DC 事件，**只用日历即可预先知道的信息** | 解释 1/15 低谷 | 1 月只有 2 个假日，效果有限 |
| 天气（可选） | 从公开源取 DC 逐小时温度/降水，写明来源与覆盖期 | 解释 1/16、1/19 的暴雪低谷 | 数据获取与对齐成本；不得伪造 |
| 滞后差分 | `lag_24 − mean_24`、`mean_3 / mean_24` 比值 | 给树模型“相对强度”信号 | 需防止除零 |

**红线**：所有滚动统计必须 `groupby(station_id).shift(1).rolling(...)`；不得用测试期统计构造“过去已知”信息。

### P2 模型（中等收益，注意过拟合）

1. **容量与早停**：`max_iter 80 → 300–500`，用训练期末尾 2 天做时间序早停（不要用 sklearn 内部随机 `validation_fraction`）；`max_leaf_nodes 15 → 31`，`min_samples_leaf 15 → 20`。
2. **损失函数**：试 `loss='tweedie', variance_power=1.1–1.5`（对零膨胀更友好）；或 **hurdle**：先分类“是否为 0”，再对正值用 Poisson。
3. **分站 vs 汇总**：训练期 20 站合计 5,280 行（每站 264 行），单站独立建模必然过拟合；可试“汇总 + 站点哑变量”（现状）与“按站点量分层的 3–5 个模型”。
4. **集成**：`0.7×hgb_full + 0.3×historical_mean`（权重在验证集上定，不许看测试）。
5. **区间**：分位数模型覆盖 91.3%/91.6% 已接近名义 90%，改用 **conformal（按站点/按小时分组校准）** 可让覆盖更稳。
6. **不要**做的：深度 LSTM/Transformer（训练期每站仅 264 行，必然过拟合）；把 `net_outflow` 当库存。

验收：验证集 MAE 相对 1.1648/1.1947 至少降 5%，且峰值欠预测率不上升；如果只降 1–2%，视为噪声。

### P3 评估（让结论更可信）

1. 增加指标：Poisson deviance、pinball loss、分需求分位（0、1–2、3–5、6+）的 MAE、按站点宏平均（已有）。
2. 所有“提升”附**按天块 bootstrap 配对区间**（见 §5.3 与 `scripts/block_bootstrap.py`）。
3. 报告“最差 100 样本”的共性（现成 `worst_errors.csv`）。
4. 所有配对比较统一用 `scripts/block_bootstrap.py`（按天重采样、同一批日块、配对差值），不要手算。

### P4 数据侧（影响上限）

1. **off-dock 行程**：15.6% 的借出没有站点。可做**敏感性分析**（例如把无站点起点按最近站点 300 m 内归属），但只能作为“敏感性”，不能写进主口径。
2. **25 h 封顶**：做“剔除 228 条 vs 保留”的对照，确认结论不依赖它。
3. **覆盖**：若能从平台/运营拿到开关站日志，把 assumed 升级为 confirmed，才能放心补零。
4. **容量**：调度模拟需要真实桩数，目前只能情景假设。

---

## 8. 实验协议（防自欺，必须照做）

### 8.1 台账模板

```csv
run_id,timestamp,change,config_hash,val_mae_dep,val_mae_arr,test_mae_dep,test_mae_arr,test_evals_used,verdict,notes
base_001,2026-10-29T17:05,initial real run,<sha>,1.1648,1.1947,1.4685,1.4801,1,baseline,real_run_01
```

### 8.2 规则

1. 每次改动只动一个变量；改完先跑验证集，不跑测试集。
2. 只有“验证集稳定更好 + 方向可解释”才消耗一次测试预算。
3. 测试结果出来后，**不允许**回头按测试结果改超参再报同一个测试集。
4. 任何结论必须写：样本量（验证 2,880 / 测试 3,360）、指标、配对区间、以及“是否在噪声内”。
5. 图表标题必须带“1 小时滚动预测，不是日前计划”。

### 8.3 如何加一个新候选（代码）

分两步：先在 `fit_model()` 里加一个损失分支（它目前只接受 Poisson 或分位数），再在 `predict_split()` 里把新模型注册进 `preds`：

```python
# forecast.py :: predict_split()
preds['hgb_tweedie'] = fit_model(train, target, 'full', cfg, loss='tweedie').predict(test)
```

然后 `run_forecast()` 会自动把它纳入 validation 比较；**选择逻辑仍然只看验证集 MAE**，你不需要（也不应该）改选择逻辑。加特征则改 `panel.make_features()` 与 `feature_columns()`，并同步 `tests/` 里的特征集断言（如现有测试覆盖）。

---

## 9. 已知陷阱（踩过）

1. **测试集不是同分布**：测试周比训练周忙 46%，测试 MAE 一定高于验证 MAE；不要拿两个数直接比。
2. **CV 折太短**：48 h/折，归还任务在 CV-2 只赢基线 0.9%，别用 CV 单独下结论。
3. **零值主导**：30% 的 0 让 MAE 看起来“还行”，一定要看峰值 MAE 与偏差。
4. **偏差符号**：负偏差 = 低估。当前全期为负，说明整体偏保守。
5. **暖启动成本**：加 `lag_336` 会让样本从 11,520 掉到 8,160（每站 576 → 408 h，再少 168 h），收益必须抵得过样本损失。
6. **`net_outflow`**：只是借出减归还的记录差，不是库存变化，也不是缺车量。
7. **覆盖 assumed**：任何“零需求”结论都要先问“这个小时真的被观测了吗”。
8. **`--overwrite`** 只对带 `.bikeproject-output` 标记的目录生效；新实验请改 `output_dir`。
9. **matplotlib 缓存**：若报 `C:\Users\...\.matplotlib` 无权限，设 `$env:MPLCONFIGDIR` 到可写目录。

---

## 10. 接手第一步（30 分钟 checklist）

1. 读 `docs/DEEPSEEK_HANDOFF.md`、`docs/OUTPUT_REPORT.md`、`data/clean/data_dictionary.md`、`data/clean/cleaning_report.json`。
2. 跑 26 项测试，确认全过。
3. 重跑 `real_template.json` 到新目录，确认 MAE 与 5.1 一致（环境/hash 对上）。
4. 打开 `tables/metrics.csv`、`hour_metrics.csv`、`worst_errors.csv`，复述三个最大的误差来源。
5. 建 `experiments/ledger.csv`，写入基线行。
6. 从 P1 里挑**一个**特征，按第 8 节协议做第一次实验。

---

## 附录 A：20 个建模站点（训练期端点事件）

| 站点 | 事件 | 站点 | 事件 |
|---|---:|---|---:|
| 31623 | 2,673 | 31266 | 1,428 |
| 31229 | 2,308 | 31281 | 1,408 |
| 31201 | 1,868 | 31615 | 1,390 |
| 31101 | 1,818 | 31124 | 1,380 |
| 31613 | 1,698 | 31104 | 1,235 |
| 31600 | 1,685 | 31125 | 1,191 |
| 31627 | 1,657 | 31214 | 1,179 |
| 31603 | 1,574 | 31203 | 1,135 |
| 31200 | 1,517 | 31228 | 1,106 |
| 31202 | 1,432 | 31505 | 1,099 |

第 21 名 31108（1,088）被排除，边界很窄。

## 附录 B：real_template.json 关键字段

```json
{
  "rides_path": "../data/clean/rides.csv",
  "coverage_path": "../data/clean/coverage.csv",
  "stations_path": "../data/clean/stations.csv",
  "time_basis": "America/New_York local wall clock ...",
  "analysis_start": "2024-01-01", "train_end": "2024-01-19",
  "validation_end": "2024-01-25", "analysis_end": "2024-02-01",
  "allow_assumed_coverage": true,
  "max_stations": 20, "min_train_events": 50,
  "rolling_folds": 2, "rolling_validation_days": 2,
  "max_iter": 80, "min_training_rows": 100,
  "prediction_intervals": true, "seed": 42,
  "simulation": { "enabled": false, "...": "情景参数，不是观测值" }
}
```

## 附录 C：一句话交接

> 数据是干净的但有已知口径缺口；模型是有效的但高峰低估；测试集只有 7 天且已经被评估过一次。
> 想证明你更好，请用验证集 + 配对 bootstrap，并把每一次尝试记进台账。
