# 共享单车分析项目 v0.1.0

本项目对应题目五：数据接口验收 → 站点小时面板 → 时空分析 → 借还预测 → 时间验证 → 调度与情景回放。

目前交付的是已用虚构数据跑通的研究代码，不是实际课程数据的最终实验结果。不保证复杂模型优于基线，也不保证调度改善。请如实报告结果。

## 1. 先做什么

1. 把docs/DEEPSEEK_HANDOFF.md交给负责清洗的DeepSeek。
2. 本机安装Python与依赖，运行单元测试。
3. 跑虚构演示，理解输出结构。
4. 接入清洗数据，修改真实配置，先关闭模拟跑分析与预测。
5. 确认覆盖和库存假设后再开启调度回放。

## 2. 安装

建议Python 3.10或更新版本。代码交付时实际运行环境及包版本在docs/VERIFICATION.md。requirements.txt给出下界，不代表所有历史版本都测试过；requirements-tested.txt记录本次验证版本。

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS/Linux：

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 3. 跑测试和演示

在包含run.py的项目根目录执行：

```bash
python -m unittest discover -s tests -v
python scripts/make_demo.py --destination demo
python run.py --config demo/config.json
```

包内已附demo的虚构数据；已验证结果单独位于examples/verified_demo_results，不占用首次运行输出目录。若再次使用同一输出目录运行：

```bash
python run.py --config demo/config.json --overwrite
```

--overwrite仅允许覆盖带项目标记的实验输出目录，仍会删除该目录原来的结果。更推荐复制配置并修改output_dir，保留每次实验。

所有演示图标有SYNTHETIC DEMO。虚构数据不能作为真实作业结果提交。

## 4. 真实数据接入

先阅读docs/DEEPSEEK_HANDOFF.md，然后准备data/clean/。

修改configs/real_template.json：

- rides_path、coverage_path、stations_path是相对配置文件位置的路径，不是相对终端位置。
- output_dir必须与输入目录分离。不要写为项目根目录。
- time_basis填写数据真实当地时区与时间约定；占位值会报错。
- analysis_start、train_end、validation_end、analysis_end均左闭右开。
- 检查数据是否确实覆盖默认日期；默认只是一个初始实验方案。
- allow_assumed_coverage默认false；覆盖仅为假设时必须人工确认后显式设true。
- max_stations默认20，仅对建模面板筛选；总体时间/会员/车型分析仍使用分析窗口内可用订单。
- simulation.enabled默认false；确认模拟局限后再启用。
- stations_path可设null以跳过空间图；模拟需要坐标。

```bash
python run.py --config configs/real_template.json
```

只有一个月数据，默认168小时滞后会排除前一周。每次运行会记录实际可建模样本数量。若真实数据不支持默认时间划分，请调整配置并在报告说明，不可继续用错误区间。

## 5. 代码与职责

| 文件 | 职责 |
|---|---|
| bikeproject/io.py | 配置、输入校验、哈希和环境记录 |
| bikeproject/panel.py | 初期训练数据选站、覆盖感知面板、滞后与滚动特征 |
| bikeproject/analysis.py | 时间、用户/车型、站点与净流量统计 |
| bikeproject/forecast.py | 基线、Poisson梯度提升树、消融、分位数区间、时间验证 |
| bikeproject/evaluation.py | MAE/RMSE、站点/小时误差、高需求误差、覆盖率 |
| bikeproject/dispatch.py | 贪心调度与整数优化，求解失败显式回退 |
| bikeproject/simulation.py | 事件回放、库存/在途/外部流/溢出池守恒 |
| bikeproject/plots.py | 统一生成静态图，不依赖在线地图 |
| bikeproject/main.py | 运行管线、日志与结果摘要 |
| tests/ | 逻辑与完整流程测试 |

## 6. 怎么理解模型

对每个站点，在某一小时开始时预测这一小时借出/归还量。训练时学习历史记录；测试时允许使用已经过去的测试小时的真实请求历史。这是每小时更新的单步预测，不是凌晨一次性预测全天。

两个简单基线：昨天同小时、训练期同站点/星期/小时均值。后三种HGB：只有日历、日历+本目标历史、日历+借还双方历史。所有模型使用相同的完整特征样本集合，避免消融因样本不同而失去可比性。

主模型使用非负计数目标的Poisson损失。站点用独热编码。历史特征仅向后看1/2/3/24/168小时和此前3/24小时统计；区间通过5%与95%分位数模型给出，交叉时排序，不能保证90%实际覆盖。

模型候选预先固定。验证集MAE选择模型，最终测试集只评估；结果摘要使用验证选出的模型。全部候选的测试分数也保存，禁止据此回头挑参然后仍称测试独立。模拟中的hgb_full是事先固定的实验策略，不是假装一定获胜的最终模型。

## 7. 输出去哪看

| 输出 | 用途 |
|---|---|
| RUN_SUMMARY.md | 本次运行摘要及局限 |
| input_audit.json | 输入检查和缺失站点统计 |
| manifest.json | 参数、包版本、输入SHA256 |
| model_eligibility.json | 暖启动/覆盖缺口造成的样本排除 |
| validation_selected_models.json | 仅依验证集选择的模型 |
| tables/hourly_panel.csv | 站点小时借还与覆盖标记 |
| tables/station_selection.csv | 选站依据、选择截止日期 |
| tables/features.csv | 可审计的全部历史特征 |
| tables/predictions.csv | 每样本真实值、预测、模型、划分、区间 |
| tables/metrics.csv | 总体、宏平均站点MAE、高峰与区间指标 |
| tables/station_metrics.csv | 分站点误差 |
| tables/hour_metrics.csv | 分小时误差 |
| tables/worst_errors.csv | 最差预测样本，用于失败案例 |
| tables/station_daily_cumulative_flow.csv | 累计净流量；缺覆盖日不作完整累计解释 |
| tables/simulation_summary.csv | 四策略、多情景结果；仅启用模拟时 |
| tables/simulation_moves.csv | 每次调车清单和自行车公里代理 |
| tables/simulation_inventory.csv | 每小时调度后的库存快照，不是精确空站时长 |
| tables/simulation_solver_log.csv | MILP求解状态、跳过与回退 |
| figures/ | 7张基础图，有坐标和模拟时最多8张 |

没有坐标时空间图跳过，未开模拟时模拟图跳过，因此不是每次都8张。

每日总量图只展示已观测日期；缺日不能自动解释为零需求。全局小时平均的分母是配置日历小时数，若总数据覆盖不完整，应在报告标注偏差或调整数据窗口。站点面板则严格按coverage控制缺失/零值。

## 8. 调度模型和模拟边界

四策略：不调度；历史均值+贪心；固定HGB全特征+同一贪心；固定HGB全特征+整数优化。

库存目标是min(容量, max(缓冲, ceil(预测借出-预测归还+缓冲)))。这是可解释的启发式目标，不是已知最优库存。整数规划只在富余站和缺口站之间安排整数辆搬运，满足小时总辆数预算、源站富余和目的缺口；目标权衡补足辆数与直线距离乘辆数。求解器说optimal仅表示该简化模型求解成功，不表示真实运营最优。

设定假设：

- 容量和初始库存比例是情景参数，不是观测值。
- 每小时调车瞬时完成，不模拟卡车装卸、道路、路线和途中时间。
- 所有车型合并为可替换资源，不模拟充电与车型偏好。
- 真实订单作为固定请求流；没有未下单需求，不能识别全部潜在需求。
- 特征依真实已观测订单历史形成，模拟中把它作为固定请求信号，不重新把反事实成功订单伪装成真实观测。
- 某次借车失败，该内部订单的归还被取消。
- 满站归还车辆进入独立holding池，后续不自动重新投放。这会改变后续服务能力，应做敏感性讨论。
- 子集外部到达/离开单独入账；不声称所选站点形成真实封闭系统。
- 仿真开始前出发、开始后到达的车作为期初外部/在途流入处理。
- 同时刻顺序：归还 → 调度 → 借出。
- 完整测试覆盖且有坐标的站点才进入模拟；simulation_stations.csv记录集合。

每事件校验：站内库存+内部在途+holding = 初始站内库存+累计外部流入−累计外部流出。

## 9. 尚未做的内容

- 未对真实课程CSV跑实验，未验证真实站点/编码/覆盖情况。
- 未提供完整的跨城市、跨季节泛化证据。
- 未实现真实道路路线、多卡车路径优化、天气外部数据、实时部署API。
- 未计算真实缺车率、真实运营利润或真实调度收益。
- 模型默认参数未声称最优；不自动开展大规模调参。
- 没有精确空站累计时长指标，只有事件结果和小时快照。
- 不生成可冒充人工撰写最终课程报告的结论；数字需自行审阅。

## 10. 论文/报告中如何表述

可写：“在给定初始库存、容量和搬运预算下，对留出时段的已观测订单进行情景回放，比较策略表现。”

不能写：“真实缺车率下降了X%”“运营成本真实减少X元”，除非另外取得支持这些结论的观测数据和成本依据。

图表都配合一句具体问题、一项结果和一个限制。按课程要求在报告附录注明仓库链接，真实团队分工应与Git提交记录对应。

## 11. 技术参考

- [scikit-learn：时间滞后特征与骑行需求预测](https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html)
- [SciPy：混合整数规划milp](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html)
- [pandas：merge连接校验](https://pandas.pydata.org/docs/reference/api/pandas.merge.html)

这些是实现参考，不代表本项目真实数据结果已被外部验证。
