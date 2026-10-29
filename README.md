# 共享单车出行时空分析与调度优化

《Python 数据分析编程》课程小组项目 —— 题目五

## 项目简介

基于 2024 年 1 月某城市共享单车骑行记录（238834 条），分析出行的时空分布、
潮汐规律与站点供需失衡现象，建立骑行需求预测模型，提出车辆调度/投放优化建议。

## 数据说明

- 文件：`data/题5_共享单车骑行_202401.csv`（约 46MB，不入库，仅本地保留）
- 规模：238834 行 × 13 列，时间范围 2024-01-01 ~ 2024-01-31
- 来源：课程学习通平台下发

| 字段 | 含义 | 取值 |
|---|---|---|
| ride_id | 骑行编号 | 字符串 |
| rideable_type | 车辆类型 | electric_bike / classic_bike |
| started_at / ended_at | 起/止时间 | 时间字符串 |
| start/end_station_name, id | 起/终点站名、站号 | 部分缺失（结构性缺失） |
| start_lat, start_lng / end_lat, end_lng | 起/终点经纬度 | 数值 |
| member_casual | 用户类型 | member / casual |

## 五条公共约定（全组统一，不得擅自更改）

1. **清洗阈值**：骑行时长 `< 1 分钟`、`> 1440 分钟` 剔除；`end_lat/end_lng` 缺失剔除。
2. **缺失站点处理**：**禁止 `dropna()`**，统一填充为 `"站点外停车"`（电单车可停站点外，属结构性缺失）。
3. **衍生列命名**：`date / hour / dow / is_weekend / duration_min`。
4. **建模口径**：`random_state=42`；按时间切分 —— 1/1–1/24 训练，1/25–1/31 测试。
5. **评估指标**：统一 RMSE / MAE / R²；图表命名 `figXX_说明.png`。

## 标准答案（清洗校验基准）

清洗后行数应为 **233749**（剔除 5085 条），清洗后时长中位数 **8.92 分钟**。

## 运行方式

在项目根目录执行（脚本会自行定位 `output/` 与 `figures/`）：

```
py src/step0_eda_check.py          # 数据体检
py src/step1_clean.py              # 清洗，产出 output/df_clean.pkl
py src/step2_time_analysis.py      # 时间维度，fig01~fig04
py src/step3_space_analysis.py     # 空间维度，fig05~fig07
py src/step4_supply_demand.py      # 供需失衡，fig08~fig09 + 站点表
py src/step5_demand_model.py       # 需求建模，fig10~fig11 + 指标表
```

依赖：Python 3.14.6、pandas 3.0.6、numpy 2.5.1、matplotlib 3.11.2、seaborn 0.13.2、scikit-learn 1.9.1

## 目录结构

```
├── data/        原始数据（csv 不上传，仅本地保留）
├── src/         分析脚本（见下方两层说明）
├── figures/     输出图表 fig01~fig11
├── output/      中间结果（清洗后 pkl、指标表、站点供需表）
└── report/      项目报告
```

### 成员对照

| 目录 | 成员 | GitHub |
|---|---|---|
| `src/member_a/` | 杨佳伟（组长） | yojvw |
| `src/member_b/` | 张熙正 | panb6746-coder |
| `src/member_c/` | 尹泽宇 | yinzeyu26-commits |

### src/ 的两层结构说明

本项目采用「三人各自独立完成 → 汇总定稿」的协作方式，`src/` 因此分两层：

| 位置 | 含义 | 说明 |
|---|---|---|
| `src/step0~step5*.py` | **最终汇总定稿** | 报告与汇报所引用的正式版本，图表与指标均由这一层产出 |
| `src/member_a/` | 成员 A 的个人过程稿 | 独立完成的一整套脚本，保留用于核对与追溯 |
| `src/member_b/` | 成员 B 的个人过程稿 | 同上 |
| `src/member_c/` | 成员 C 的个人过程稿 | 同上 |

> 目前 `src/member_a/` 的内容与汇总定稿一致，因为成员 A 是第一位完成全流程的成员；
> 成员 B、C 的过程稿陆续提交后，汇总定稿将在三人结果交叉验证的基础上形成。
> 这一设计使「谁在什么时候提交了什么」在提交历史中可以逐条追溯，与报告第 8 章的
> 分工说明一一对应。

## 协作约定

1. 每位成员**只修改自己名下目录**（`src/member_x/`），不改动他人文件与根目录 `README.md`。
2. 提交前先执行 `拉取源(Fetch)` → 如落后则 `拉取(Pull)`，再 `提交(Commit)` → `推送(Push)`。
3. 每位成员首次克隆后须设置本机身份，否则提交记录的作者不正确：
   ```
   cd /d D:\bike
   git config user.name "姓名"
   git config user.email "GitHub 注册邮箱"
   ```
