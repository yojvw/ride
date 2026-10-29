#!/usr/bin/env python3
"""One-click export: JSON, figures, notebook, HTML, docs, acceptance, manifest."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

import pandas as pd

from handoff import core, docs, figures, notebook, report


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_kernelspec(python_executable: str) -> Path:
    kernel_dir = PKG / ".jupyter" / "kernels" / "bike-handoff"
    kernel_dir.mkdir(parents=True, exist_ok=True)
    spec = {
        "argv": [python_executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": "Bike Handoff (venv)",
        "language": "python",
        "env": {"MPLCONFIGDIR": str(PKG / ".mplcache")},
    }
    (kernel_dir / "kernel.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return kernel_dir


def execute_notebook(python_executable: str) -> None:
    env = dict(os.environ)
    env["JUPYTER_PATH"] = str(PKG / ".jupyter")
    env["MPLCONFIGDIR"] = str(PKG / ".mplcache")
    run_cmd = [
        python_executable, "-m", "nbconvert", "--to", "notebook", "--execute", "--inplace",
        "--ExecutePreprocessor.timeout=900", "--ExecutePreprocessor.kernel_name=bike-handoff",
        "bike_analysis.ipynb",
    ]
    result = subprocess.run(run_cmd, cwd=PKG, env=env, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise RuntimeError(f"Notebook execution failed:\n{result.stdout}\n{result.stderr}")
    export_cmd = [python_executable, "-m", "nbconvert", "--to", "html",
                  "bike_analysis.ipynb", "--output", "bike_analysis.html"]
    result = subprocess.run(export_cmd, cwd=PKG, env=env, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise RuntimeError(f"HTML export failed:\n{result.stdout}\n{result.stderr}")


def load_notebook(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def acceptance(summary, cfg, data, metrics, tables, nb_path, html_path, figure_paths):
    rows = []

    def check(name, ok, detail=""):
        rows.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    try:
        json.loads(json.dumps(summary, allow_nan=False))
        check("JSON 合法且不含 NaN/Infinity", True, "json.dumps(allow_nan=False) 通过")
    except ValueError as exc:
        check("JSON 合法且不含 NaN/Infinity", False, str(exc))

    total = sum(item["rides"] for item in summary["trends"]["daily"])
    check("每日序列求和 = 总订单", total == summary["overview"]["total_rides"],
          f"{total} vs {summary['overview']['total_rides']}")

    dep_sum = sum(item["departures"] for item in summary["stations"]["list"])
    arr_sum = sum(item["arrivals"] for item in summary["stations"]["list"])
    scope = {item["scope"]: item["rows"] for item in summary["scope"]["definitions"]}
    check("站点借出合计 = 有起点端点", dep_sum == scope["有起点的端点"], f"{int(dep_sum)} vs {scope['有起点的端点']}")
    check("站点归还合计 = 窗口内终点端点", arr_sum == scope["到达在窗口内的终点端点"],
          f"{int(arr_sum)} vs {scope['到达在窗口内的终点端点']}")

    check("面板行数一致", len(data.panel) == data.versions["panel_rows"], f"{len(data.panel)} 行")

    test_rows = metrics[(metrics.split == "test") & (metrics.target == "departures") & (metrics.model == "hgb_full")]
    check("测试样本数 = 3,360", int(test_rows.n.iloc[0]) == 3360, f"{int(test_rows.n.iloc[0])}")

    candidates = summary["optimization"]["candidates"]
    check("候选实验没有测试成绩", all(item["test_mae"] is None for item in candidates),
          f"{len(candidates)} 条候选记录全部为 null")

    selected = summary["optimization"]["selected_candidates"]
    check("入选候选状态为 validation_only", all(item["status"] == "validation_only_not_finalized" for item in selected),
          f"{[item['model'] for item in selected]}")

    check("预测指标包含确认模型的测试成绩",
          any(item["model"] == "hgb_full" and item["split"] == "test" for item in summary["prediction"]["metrics"]), "")

    curves = summary["prediction"]["curves"]
    aligned = True
    for curve in curves:
        frame = data.predictions[(data.predictions.split == curve["split"]) & (data.predictions.model == curve["model"]) &
                                 (data.predictions.station_id == curve["station_id"]) & (data.predictions.target == curve["target"])]
        frame = frame.sort_values("time").head(len(curve["points"]))
        if len(frame) != len(curve["points"]):
            aligned = False
            break
        for point, row in zip(curve["points"], frame.itertuples()):
            if point["time"] != row.time.strftime("%Y-%m-%d %H:%M") or abs(point["actual"] - float(row.actual)) > 1e-9:
                aligned = False
                break
    check("预测曲线按站点/时间/目标对齐", aligned, f"{len(curves)} 条曲线")

    nb = load_notebook(nb_path)
    code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
    check("Notebook 全部代码单元已执行", all(c.get("execution_count") is not None for c in code_cells),
          f"{len(code_cells)} 个代码单元")
    comments = [i for i, c in enumerate(code_cells) if "#" in "".join(c["source"])]
    check("代码单元无注释", not comments, f"违规单元: {comments}")

    html = html_path.read_text(encoding="utf-8", errors="ignore")
    check("HTML 已生成且无 Traceback", html_path.exists() and "Traceback (most recent call last)" not in html,
          f"{len(html):,} 字符")
    check("HTML 内嵌图片", html.count("image/png") >= 10, f"image/png 出现 {html.count('image/png')} 次")

    missing_figs = [name for name, path in figure_paths.items() if not Path(path).exists()]
    check("11 张图表全部存在", not missing_figs and len(figure_paths) == 11, f"{len(figure_paths)} 张")

    findings_ok = all((PKG / "figures" / item["figure"]).exists() for item in summary["findings"])
    check("发现引用的图表存在", findings_ok, f"{len(summary['findings'])} 条发现")

    required = ["docs/FRONTEND_HANDOFF.md", "docs/FINDINGS.md", "docs/LIMITATIONS.md",
                "docs/REPORT_OUTLINE.md", "docs/SLIDES_5MIN.md", "docs/FIGURES.md",
                "README.md", "运行说明.md"]
    missing = [item for item in required if not (PKG / item).exists()]
    check("交付文档齐全", not missing, f"缺失: {missing}" if missing else "")
    return rows


def manifest(root: Path) -> list:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(root).as_posix()
        if (rel.startswith((".jupyter/", ".mplcache/")) or "__pycache__" in rel or rel.endswith(".pyc")
                or rel == "docs/FILE_MANIFEST.md"):
            continue
        rows.append({"path": rel, "bytes": path.stat().st_size, "sha256": sha256(path)})
    return rows


def main() -> int:
    cfg = core.load_config(PKG / "handoff_config.json")
    core.verify_inputs(cfg)
    data = core.load_data(cfg)
    tide = core.tide_table(data)
    metrics = core.prediction_metrics(data)
    tables = core.candidate_tables(cfg)
    rounds = core.round_summary(cfg, tables)
    reps = core.representative_stations(data, tide)
    dispatch = core.dispatch_table(data, tide, 8)
    hourly = core.hourly_tables(data)
    findings = core.build_findings(data, tide, metrics, rounds, tables)

    figure_paths = figures.render_all(data, tide, metrics, tables, reps, cfg, PKG / "figures")
    summary = report.build_summary(cfg, data, tide, metrics, hourly, tables, rounds, reps,
                                   dispatch, findings, figure_paths, {"status": "pending"})
    summary["dispatch"]["simulation"] = None
    summary["dispatch"]["simulation_note"] = "本包未运行调度模拟；没有初始库存、容量与预算，因此不提供模拟收益。"

    (PKG / "data").mkdir(exist_ok=True)
    (PKG / "data" / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")

    docs.write_frontend_handoff(PKG / "docs" / "FRONTEND_HANDOFF.md", summary)
    docs.write_findings(PKG / "docs" / "FINDINGS.md", summary)
    docs.write_limitations(PKG / "docs" / "LIMITATIONS.md", summary)
    docs.write_report_outline(PKG / "docs" / "REPORT_OUTLINE.md", summary)
    docs.write_slides(PKG / "docs" / "SLIDES_5MIN.md", summary)
    docs.write_figures(PKG / "docs" / "FIGURES.md", summary)
    docs.write_readme(PKG / "README.md", summary)
    docs.write_run_instructions(PKG / "运行说明.md", summary)

    notebook.build(PKG / "bike_analysis.ipynb")
    write_kernelspec(sys.executable)
    execute_notebook(sys.executable)

    checks_rows = acceptance(summary, cfg, data, metrics, tables,
                             PKG / "bike_analysis.ipynb", PKG / "bike_analysis.html", figure_paths)
    summary["acceptance"] = {"status": "PASS" if all(r["status"] == "PASS" for r in checks_rows) else "FAIL",
                             "checks": checks_rows}
    (PKG / "data" / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")

    lines = ["# 验收记录", "",
             f"总体状态：**{summary['acceptance']['status']}**", "",
             "| 检查项 | 结果 | 说明 |", "|---|---|---|"]
    for row in checks_rows:
        lines.append(f"| {row['check']} | {row['status']} | {row['detail']} |")
    lines += ["", f"数据：`{cfg['data']['rides']}`（sha256 `{data.versions['rides_sha256'][:16]}…`）",
              f"已确认模型：`{cfg['confirmed_model']['model']}`（{cfg['confirmed_model']['run_id']}）",
              "候选实验：仅验证成绩，未评分测试集。"]
    (PKG / "docs" / "ACCEPTANCE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    rows = manifest(PKG)
    manifest_lines = ["# 文件清单", "", "| 文件 | 字节 | sha256 |", "|---|---:|---|"]
    for row in rows:
        manifest_lines.append(f"| `{row['path']}` | {row['bytes']:,} | `{row['sha256'][:16]}…` |")
    (PKG / "docs" / "FILE_MANIFEST.md").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    failed = [row for row in checks_rows if row["status"] != "PASS"]
    print(json.dumps({"status": summary["acceptance"]["status"], "failed": failed,
                      "figures": len(figure_paths), "json_bytes": (PKG / "data" / "summary.json").stat().st_size,
                      "html_bytes": (PKG / "bike_analysis.html").stat().st_size}, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
