# Claude 前端与课程成果交接包

版本 1.0.0；生成时间 2026-10-29T10:49:45Z；数据 2024-01-01 00:00:00 至 2024-02-01 00:00:00。

本包把已完成的分析、冻结的预测结果与两轮优化实验整理成：前端 JSON、字段说明、图表、课程材料、可执行 Notebook（含 HTML）与一键导出脚本。

## 采用版本

- 数据：`data/clean/rides.csv`，238,699 行，sha256 `02f37c8f6788d0a1…`
- 已确认模型：`hgb_full`（real_run_01，测试已评估）
- 候选实验：`opt_v020_001`（全部拒绝）、`opt_v021_001`（归还 1 个候选入选，仅有验证成绩）
- 测试预算：1/3 已用；本包未运行 finalize。

## 目录

```text
bike_analysis.ipynb        已执行 Notebook（含输出）
bike_analysis.html         由该 Notebook 导出的离线 HTML
data/summary.json          前端数据
figures/                   11 张图（PNG）
docs/FRONTEND_HANDOFF.md   前端字段与展示规则
docs/FINDINGS.md           5 条核心发现
docs/LIMITATIONS.md        局限
docs/REPORT_OUTLINE.md     课程报告提纲
docs/SLIDES_5MIN.md        5 分钟汇报提纲
docs/FIGURES.md            图表清单（单位/状态/来源）
docs/ACCEPTANCE.md         验收记录
docs/FILE_MANIFEST.md      文件清单（含 sha256）
scripts/export_all.py      一键重新导出
handoff/                   共享计算模块（Notebook 与导出脚本共用）
handoff_config.json        路径与版本配置
```

## 运行

本包**依赖原工程与数据**（data/clean、results/real_run_01、experiments/*），不能脱离工程独立运行。
把本目录放在 `bike_analysis_project/deliverables/claude_handoff/` 下即可直接使用；若移动位置，请修改 `handoff_config.json` 的 `project_root`。

```powershell
cd deliverables\claude_handoff
..\..\.venv\Scripts\python.exe scripts\export_all.py
```

## 口径提醒

- 全量订单、站点端点、建模面板三种口径不能混用。
- 候选模型只有验证成绩；`test_mae` 在 JSON 中恒为 null。
- 净流量不是缺车量；没有库存与容量数据。
