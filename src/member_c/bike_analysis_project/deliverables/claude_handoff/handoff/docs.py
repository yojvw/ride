"""Markdown documentation generated together with the JSON summary."""

from __future__ import annotations

from pathlib import Path


def _pct(x, digits=1):
    return f"{x * 100:.{digits}f}%"


def write_frontend_handoff(path: Path, s: dict) -> None:
    meta, scope = s["meta"], s["scope"]
    tide = s["stations"]["tide_summary"]
    sel = s["optimization"]["selected_candidates"]
    lines = [
        "# FRONTEND_HANDOFF：给 Claude 的前端数据说明",
        "",
        f"包版本 {meta['version']}；生成时间 {meta['generated_at_utc']}。",
        "本文件描述 data/summary.json 的结构、口径与展示规则。**前端不得自行修改统计口径，也不得硬编码任何成绩。**",
        "",
        "## 1. 数据版本与模型版本",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 数据窗口 | {meta['data_version']['window'][0]} 至 {meta['data_version']['window'][1]} |",
        f"| rides.csv | {meta['data_version']['rides_rows']:,} 行，sha256 `{meta['data_version']['rides_sha256'][:16]}…` |",
        f"| 覆盖区间 | {meta['data_version']['coverage_rows']} 行，其中 assumed {meta['data_version']['coverage_assumed_rows']} 行 |",
        f"| 站点 | {meta['data_version']['stations']} 个 |",
        f"| 建模面板 | {meta['data_version']['panel_stations']} 站 × 744 小时 = {meta['data_version']['panel_rows']:,} 行 |",
        f"| 已确认模型 | `{meta['model_version']['confirmed']['model']}`（{meta['model_version']['confirmed']['run_id']}，测试已评估） |",
        f"| 候选模型 | {len(sel)} 个，仅有验证成绩，**没有测试成绩** |",
        "",
        "## 2. 三种口径（不能混用）",
        "",
        "| 口径 | 行数 | 定义 |",
        "|---|---:|---|",
    ]
    for item in scope["definitions"]:
        lines.append(f"| {item['scope']} | {item['rows']:,} | {item['definition']} |")
    lines += [
        "",
        "`scope.warning` 已写入 JSON；任何图表若混合口径，必须标注清楚。",
        "",
        "## 3. 顶层结构",
        "",
        "| 键 | 类型 | 内容 |",
        "|---|---|---|",
        "| `meta` | object | 版本、时间口径、数据与模型版本、实验目录 |",
        "| `scope` | object | 三种口径的定义与计数 |",
        "| `overview` | object | 总量、日均、极值日、会员/车型占比 |",
        "| `trends` | object | 每日序列、24 小时序列、星期×小时矩阵 |",
        "| `member_bike` | object | 会员/车型构成、时长、交叉表、分小时占比 |",
        "| `stations` | object | 761 站汇总、潮汐指标、20 站小时画像、代表站点 |",
        "| `prediction` | object | 已确认模型的验证/测试指标、分小时误差、典型曲线 |",
        "| `optimization` | object | 两轮候选实验（仅验证）、测试预算、入选候选 |",
        "| `dispatch` | object | 条件性调度建议与缺口 |",
        "| `findings` | array | 5 条核心发现 |",
        "| `limitations` | array | 8 条限制 |",
        "| `metrics_catalog` | object | 每个指标的单位/范围/口径/分母/来源/状态 |",
        "| `figures` | array | 图表文件名清单 |",
        "| `acceptance` | object | 导出时的验收结果 |",
        "",
        "## 4. 关键字段与示例",
        "",
        "### 4.1 趋势",
        "",
        "```json",
        '{"trends": {"daily": [{"date": "2024-01-01", "rides": 4898}],',
        '            "hourly": [{"hour": 8, "rides_all": 18196, "weekday_mean": 717.4, "weekend_mean": 211.9}],',
        '            "weekday_hour_mean": [[...24 个数...], ...7 行...]}}',
        "```",
        "",
        "单位：`rides` 次；`weekday_mean` 是“工作日该钟点的日均次数”，分母 23 个工作日；`weekend_mean` 分母 8 个周末日。",
        "",
        "### 4.2 站点",
        "",
        "```json",
        '{"station_id": "31623", "station_name": "…", "lat": 38.897, "lng": -77.005,',
        ' "departures": 2998, "arrivals": 2957, "net": 41, "events": 5955,',
        ' "in_panel": true, "am_net": -2.46, "pm_net": 2.25, "reversal": true, "amplitude": 4.71}',
        "```",
        "",
        "- `departures/arrivals/net`：全月次数；`net = departures − arrivals`，**不是缺车量**。",
        "- `am_net/pm_net`：06–09 时与 16–19 时的平均每小时净流出。",
        "- `reversal`：早晚净流出符号相反。",
        "- `in_panel`：是否属于 20 个建模站点（只有这 20 站有小时级面板与预测）。",
        f"- 潮汐汇总：{tide['active_stations']} 个事件量 ≥200 的站点中 {tide['reversal_count']} 个反转（{_pct(tide['reversal_share'])}），上午/下午相关系数 {tide['corr_am_pm']:.3f}。",
        "",
        "### 4.3 预测",
        "",
        "```json",
        '{"split": "test", "target": "departures", "model": "hgb_full", "n": 3360,',
        ' "mae": 1.4685, "rmse": 2.2184, "bias": -0.2886, "peak_mae": 2.8788,',
        ' "peak_underprediction_rate": 0.8514, "interval_coverage": 0.9134,',
        ' "interval_width": 5.634, "improvement_vs_previous_day": 0.3113}',
        "```",
        "",
        "- `split` ∈ {cv_1, cv_2, validation, test}；**测试与验证必须分开展示**。",
        "- 只有 `hgb_full`（以及测试期的全部候选模型）有区间字段；其余为 null。",
        "- `curves[].points[]` 字段：`time, actual, prediction, lower, upper`，按站点+目标严格对齐。",
        "",
        "### 4.4 优化实验",
        "",
        "```json",
        '{"run_id": "opt_v021_001", "target": "arrivals", "model": "reg_leaf15_min30",',
        ' "validation_mae": 1.1776, "relative_gain_vs_baseline": 0.0143,',
        ' "paired_ci_low": -0.0286, "paired_ci_high": -0.0066, "test_mae": null,',
        ' "status": "validation_only"}',
        "```",
        "",
        "**`test_mae` 恒为 null**：候选没有测试成绩，前端不得用任何数字填充。",
        "",
        "### 4.5 调度建议",
        "",
        "```json",
        '{"station_id": "31602", "daily_net": 449, "am_net_per_hour": 2.1, "pm_net_per_hour": -1.4,',
        ' "pattern": "早高峰净流出、晚高峰净流入",',
        ' "suggested_action": "早间（约 06:30 前）优先补车；晚间（约 16:00–19:00）优先疏解",',
        ' "missing_info": "站点容量、实时库存、调度车容量与成本、道路可达性均未提供"}',
        "```",
        "",
        "## 5. 四个页面",
        "",
        "| 页面 | 主要数据 | 推荐图表 |",
        "|---|---|---|",
        "| 1 总览 | `meta`、`overview`、`trends.daily`、`findings` | 指标卡（总量/日均/会员占比/车型占比）、每日折线、发现列表 |",
        "| 2 出行与站点 | `trends.hourly`、`weekday_hour_mean`、`member_bike`、`stations.list/profiles` | 小时曲线（工作日/周末）、星期×小时热力图、站点散点（事件量 vs 净流量）、潮汐四象限、代表站点累计曲线 |",
        "| 3 预测评估 | `prediction.metrics/by_hour/curves`、`optimization` | 模型 MAE 条形图、分小时误差、预测曲线（含区间）、候选验证对比（标注“仅验证”） |",
        "| 4 调度建议 | `dispatch.items`、`stations.tide_summary`、`limitations` | 站点优先级表、早晚方向箭头/象限图、缺口清单 |",
        "",
        "## 6. 筛选条件与筛选后的口径",
        "",
        "| 页面 | 可用筛选 | 说明 |",
        "|---|---|---|",
        "| 总览 | 日期范围 | 只能从 `trends.daily` 重新计算均值；不得把单日数字当全月 |",
        "| 出行 | 工作日/周末、小时 | `hourly` 已给两种分母；前端不得把两种均值混算 |",
        "| 站点 | 全部/仅建模 20 站/仅反转站/事件量阈值 | `stations.list` 是月汇总，筛选后仍是月汇总，不做时间加权 |",
        "| 预测 | 划分（validation/test）、目标、模型 | 只能显示 JSON 中已有的组合；**禁止把验证成绩标成测试** |",
        "| 优化 | 轮次、目标 | 只显示 `validation` 指标与 `test_mae: null` |",
        "",
        "## 7. 缺失与未评估的展示规则",
        "",
        "- 任何 `null` 显示为“暂无数据”或“—”，不得用 0 代替。",
        "- 候选模型卡片必须写“仅有验证成绩，测试未评估”；不得出现测试分数、排名或“预计提升”。",
        "- 调度页必须显示“未运行模拟”的提示：JSON `dispatch.simulation` 为 null。",
        "- 站点页脚注必须写：净流量不是缺车量；容量/库存未知。",
        "- 坐标标注为“站点中心估计值”，不得展示为精确门牌位置。",
        "",
        "## 8. 更新方法",
        "",
        "1. 修改 `handoff_config.json` 中的实验目录（或数据路径），不要按文件修改时间自动选择。",
        "2. 在包根目录运行 `python scripts/export_all.py`（使用项目 `.venv`）。",
        "3. 脚本会重新校验输入哈希、生成 JSON/图表/Notebook/HTML，并输出 `docs/ACCEPTANCE.md`。",
        "4. 失败时脚本非零退出且不覆盖既有产物；不要手工编辑 JSON。",
        "",
        "## 9. 前端禁止事项",
        "",
        "- 不得修改 `scope` 定义或把不同口径的数字放在同一张图里不加说明。",
        "- 不得把 `optimization.candidates[].test_mae` 填成任何数值。",
        "- 不得从前端代码重新计算 MAE/RMSE（口径会漂移）；只显示 JSON 中的值。",
        "- 不得编造库存、容量、天气、成本或“缺车率”。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_findings(path: Path, s: dict) -> None:
    lines = ["# 5 条核心发现", "",
             "每条都给出数字、数据范围与对应图表/数据文件。数字来自 data/summary.json。", ""]
    for item in s["findings"]:
        lines += [f"## {item['id']} {item['title']}", "",
                  item["value"], "",
                  f"- 数据范围：{item['scope']}",
                  f"- 来源：{item['source']}",
                  f"- 图表：`figures/{item['figure']}`", ""]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_limitations(path: Path, s: dict) -> None:
    lines = ["# 局限说明", "",
             "以下限制会直接影响结论的可推广性，报告中必须同时引用。", ""]
    for item in s["limitations"]:
        lines += [f"## {item['id']} {item['title']}", "", item["text"], ""]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report_outline(path: Path, s: dict) -> None:
    lines = [
        "# 课程报告提纲（对应题目五模板）",
        "",
        "| 章节 | 内容 | 图表/数据 |",
        "|---|---|---|",
        "| 1 研究问题与数据 | 城市、时间窗、三种口径、数据版本哈希 | `data/summary.json → meta/scope` |",
        "| 2 数据接口与清洗审计 | 238,699 条保留、135 条拒绝、缺失率、25 小时封顶 | `rides.csv`、`cleaning_report.json` |",
        "| 3 出行规律 | 工作日双峰 / 周末单峰、会员与车型差异 | `fig02`、`fig03`、`fig04` |",
        f"| 4 站点潮汐与失衡 | {s['stations']['tide_summary']['reversal_share']:.1%} 站点早晚反转、热门≠净流出、代表站点 | `fig05`、`fig06`、`fig07` |",
        "| 5 建模与验证 | 5 个固定候选、验证选模、测试只评一次 | `fig08`、`fig09`、`fig11` |",
        "| 6 优化实验 | 两轮 13 个新候选、仅 1 个过验证门槛、无测试成绩 | `fig10`、`optimization` |",
        "| 7 调度建议 | 条件性补车/疏解优先级、所需补充信息 | `dispatch` |",
        "| 8 局限与下一步 | 覆盖假设、站外端点、单月、短验证期、测试已查看 | `limitations` |",
        "",
        "写作要求：",
        "",
        "- 第 5 章只引用已确认模型（`hgb_full`）的测试成绩；第 6 章只引用验证成绩。",
        "- 所有“可能原因”用“与……一致”表述，不写成已证明因果。",
        "- 调度章节不出现缺车量、收益、成本等未观测指标。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_slides(path: Path, s: dict) -> None:
    lines = [
        "# 5 分钟汇报提纲（总时长 5:00）",
        "",
        "| 时间 | 内容 | 图表/数据 |",
        "|---|---|---|",
        "| 0:00–0:40 | 问题与数据：238,699 次骑行、761 站、2024-01；三种口径 | `overview`、`scope` |",
        "| 0:40–1:30 | 出行规律：工作日 08:00/17:00 双峰，周末 14–16 时单峰 | `fig02`、`fig03` |",
        f"| 1:30–2:20 | 站点潮汐：{s['stations']['tide_summary']['reversal_share']:.1%} 站点早晚反转；热门≠净流出 | `fig05`、`fig06` |",
        "| 2:20–3:20 | 预测：确认模型测试 MAE 1.4685/1.4801，较基线 +31.1%/+28.5%；高峰仍低估 | `fig08`、`fig09` |",
        "| 3:20–4:10 | 优化实验：13 个新候选仅 1 个过验证门槛，且没有测试成绩 | `fig10` |",
        "| 4:10–5:00 | 调度建议与局限：条件性补车/疏解；容量库存未知 | `dispatch`、`limitations` |",
        "",
        "讲稿要点：",
        "",
        "- 强调“净流量不是缺车量”，避免把站点净流出说成真实短缺。",
        "- 强调候选模型的成绩只来自验证集，测试期未评分。",
        "- 最后 20 秒说明覆盖假设与单月数据限制。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_figures(path: Path, s: dict) -> None:
    lines = ["# 图表清单", "",
             "| 文件 | 标题 | 单位 | 状态 | 来源 |", "|---|---|---|---|---|"]
    for item in s["figures"]:
        lines.append(f"| `{item['file']}` | {item.get('title', '')} | {item.get('unit', '')} | "
                     f"{item.get('status', '')} | {item.get('source', '')} |")
    lines += ["", "状态说明：observed = 观测；prediction = 冻结预测；validation_experiment = 仅验证集实验。",
              "所有图表由 `scripts/export_all.py` 用同一版数据生成，Notebook 中显示的是同一批 PNG。"]
    path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")


def write_readme(path: Path, s: dict) -> None:
    meta = s["meta"]
    lines = [
        "# Claude 前端与课程成果交接包",
        "",
        f"版本 {meta['version']}；生成时间 {meta['generated_at_utc']}；数据 {meta['data_version']['window'][0]} 至 {meta['data_version']['window'][1]}。",
        "",
        "本包把已完成的分析、冻结的预测结果与两轮优化实验整理成：前端 JSON、字段说明、图表、课程材料、"
        "可执行 Notebook（含 HTML）与一键导出脚本。",
        "",
        "## 采用版本",
        "",
        f"- 数据：`data/clean/rides.csv`，{meta['data_version']['rides_rows']:,} 行，sha256 `{meta['data_version']['rides_sha256'][:16]}…`",
        f"- 已确认模型：`{meta['model_version']['confirmed']['model']}`（{meta['model_version']['confirmed']['run_id']}，测试已评估）",
        "- 候选实验：`opt_v020_001`（全部拒绝）、`opt_v021_001`（归还 1 个候选入选，仅有验证成绩）",
        "- 测试预算：1/3 已用；本包未运行 finalize。",
        "",
        "## 目录",
        "",
        "```text",
        "bike_analysis.ipynb        已执行 Notebook（含输出）",
        "bike_analysis.html         由该 Notebook 导出的离线 HTML",
        "data/summary.json          前端数据",
        "figures/                   11 张图（PNG）",
        "docs/FRONTEND_HANDOFF.md   前端字段与展示规则",
        "docs/FINDINGS.md           5 条核心发现",
        "docs/LIMITATIONS.md        局限",
        "docs/REPORT_OUTLINE.md     课程报告提纲",
        "docs/SLIDES_5MIN.md        5 分钟汇报提纲",
        "docs/FIGURES.md            图表清单（单位/状态/来源）",
        "docs/ACCEPTANCE.md         验收记录",
        "docs/FILE_MANIFEST.md      文件清单（含 sha256）",
        "scripts/export_all.py      一键重新导出",
        "handoff/                   共享计算模块（Notebook 与导出脚本共用）",
        "handoff_config.json        路径与版本配置",
        "```",
        "",
        "## 运行",
        "",
        "本包**依赖原工程与数据**（data/clean、results/real_run_01、experiments/*），不能脱离工程独立运行。",
        "把本目录放在 `bike_analysis_project/deliverables/claude_handoff/` 下即可直接使用；"
        "若移动位置，请修改 `handoff_config.json` 的 `project_root`。",
        "",
        "```powershell",
        "cd deliverables\\claude_handoff",
        "..\\..\\.venv\\Scripts\\python.exe scripts\\export_all.py",
        "```",
        "",
        "## 口径提醒",
        "",
        "- 全量订单、站点端点、建模面板三种口径不能混用。",
        "- 候选模型只有验证成绩；`test_mae` 在 JSON 中恒为 null。",
        "- 净流量不是缺车量；没有库存与容量数据。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_run_instructions(path: Path, s: dict) -> None:
    lines = [
        "# 运行说明",
        "",
        "## 环境",
        "",
        "- Python 3.12；项目 `.venv` 内已固定：numpy 1.26.4 / pandas 2.2.3 / scipy 1.13.1 / scikit-learn 1.6.1 / matplotlib 3.10.3。",
        "- Notebook 执行额外需要：nbformat / nbconvert / nbclient / ipykernel（仅用于生成与导出，不参与建模）。",
        "- 中文字体：Microsoft YaHei 或 SimHei（Windows 自带）。",
        "",
        "## 依赖的原工程文件",
        "",
        "```text",
        "data/clean/rides.csv",
        "data/clean/coverage.csv",
        "data/clean/stations.csv",
        "data/clean/cleaning_report.json",
        "results/real_run_01/tables/hourly_panel.csv",
        "results/real_run_01/tables/predictions.csv",
        "experiments/opt_v020_001/{validation_cv_metrics.csv,validation_paired_bootstrap.csv,selection_decisions.csv}",
        "experiments/opt_v021_001/{metrics.csv,paired_bootstrap.csv,selection_decisions.csv}",
        "```",
        "",
        "## 一键导出",
        "",
        "```powershell",
        "cd deliverables\\claude_handoff",
        "..\\..\\.venv\\Scripts\\python.exe scripts\\export_all.py",
        "```",
        "",
        "脚本会：校验输入哈希 → 生成 11 张图 → 写 data/summary.json → 生成并执行 bike_analysis.ipynb → 导出 bike_analysis.html → 运行验收 → 写 ACCEPTANCE.md 与 FILE_MANIFEST.md。",
        "",
        "## 失败处理",
        "",
        "- 输入缺失或哈希不符：脚本抛错并非零退出，不覆盖既有产物。",
        "- Notebook 执行失败：脚本保留 stderr，不生成 HTML。",
        "- 验收失败：不写“通过”，并在 ACCEPTANCE.md 中列出具体项。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
