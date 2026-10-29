# 验收记录

总体状态：**PASS**

| 检查项 | 结果 | 说明 |
|---|---|---|
| JSON 合法且不含 NaN/Infinity | PASS | json.dumps(allow_nan=False) 通过 |
| 每日序列求和 = 总订单 | PASS | 238699 vs 238699 |
| 站点借出合计 = 有起点端点 | PASS | 201574 vs 201574 |
| 站点归还合计 = 窗口内终点端点 | PASS | 199053 vs 199053 |
| 面板行数一致 | PASS | 14880 行 |
| 测试样本数 = 3,360 | PASS | 3360 |
| 候选实验没有测试成绩 | PASS | 30 条候选记录全部为 null |
| 入选候选状态为 validation_only | PASS | ['reg_leaf15_min30'] |
| 预测指标包含确认模型的测试成绩 | PASS |  |
| 预测曲线按站点/时间/目标对齐 | PASS | 6 条曲线 |
| Notebook 全部代码单元已执行 | PASS | 17 个代码单元 |
| 代码单元无注释 | PASS | 违规单元: [] |
| HTML 已生成且无 Traceback | PASS | 1,554,843 字符 |
| HTML 内嵌图片 | PASS | image/png 出现 12 次 |
| 11 张图表全部存在 | PASS | 11 张 |
| 发现引用的图表存在 | PASS | 5 条发现 |
| 交付文档齐全 | PASS |  |

数据：`data/clean/rides.csv`（sha256 `02f37c8f6788d0a1…`）
已确认模型：`hgb_full`（real_run_01）
候选实验：仅验证成绩，未评分测试集。
