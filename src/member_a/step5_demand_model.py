import matplotlib

matplotlib.use('Agg')

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


# 路径以脚本所在目录为准；沿用前四步的图片目录。
BASE_DIR = Path(__file__).resolve().parent.parent  # 项目根目录（src 的上一级）
OUTPUT_DIR = BASE_DIR / 'output'
FIGURE_DIR = BASE_DIR / 'figures'
RANDOM_STATE = 42
TOP_N = 50
OFF_STATION = '站点外停车'
FEATURES = ['hour', 'dow', 'is_weekend', 'inflow', 'outflow',
            'total', 'net_flow', 'hist_mean']
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False


def prepare_data(df):
    # 字符串标记必须显式排除；真正的缺失值报错，不静默删除。
    columns = ['start_station_name', 'end_station_name', 'started_at', 'ended_at']
    missing = set(columns).difference(df.columns)
    if missing:
        raise ValueError(f'清洗数据缺少字段：{sorted(missing)}')
    if df.empty or df[columns].isna().any().any():
        raise ValueError('输入为空或必要字段存在缺失值，请检查清洗数据。')
    for column in columns[:2]:
        if not df[column].map(lambda v: isinstance(v, str) and bool(v.strip())).all():
            raise ValueError(f'{column} 必须为非空字符串。')
    excluded = (df['start_station_name'].eq(OFF_STATION)
                | df['end_station_name'].eq(OFF_STATION))
    valid = df.loc[~excluded, columns].copy()
    print(f'输入记录数：{len(df):,}；排除“{OFF_STATION}”：{excluded.sum():,} 条；'
          f'剩余记录数：{len(valid):,}')
    if valid.empty:
        raise ValueError('排除站点外停车后无有效骑行。')
    for column in columns[2:]:
        valid[column] = pd.to_datetime(valid[column], errors='raise')
        if valid[column].isna().any() or valid[column].dt.tz is not None:
            raise ValueError('时间必须有效且采用原数据的无时区本地时间。')
    if (valid['ended_at'] < valid['started_at']).any():
        raise ValueError('存在结束时间早于开始时间的记录。')
    years = valid['started_at'].dt.year.unique()
    if len(years) != 1 or not valid['started_at'].dt.month.eq(1).all():
        raise ValueError('输入出发时间必须属于同一年一月份。')
    start = pd.Timestamp(year=int(years[0]), month=1, day=1)
    cutoff = start + pd.Timedelta(days=24)
    valid['date'] = valid['started_at'].dt.normalize()
    valid['hour'] = valid['started_at'].dt.hour
    return valid, start, cutoff


def training_stations(df, start, cutoff):
    # 按用户确认的修订口径重算训练期统计，不读取或覆盖全月供需表。
    # 流入按实际到达时间计数，排除训练期出发、测试期才到达的记录。
    incoming = df.loc[df['ended_at'].ge(start) & df['ended_at'].lt(cutoff),
                      'end_station_name'].value_counts().rename('inflow')
    outgoing = df.loc[df['started_at'].lt(cutoff),
                      'start_station_name'].value_counts().rename('outflow')
    table = pd.concat([incoming, outgoing], axis=1).fillna(0).astype('int64')
    table.index.name = 'station_name'
    table['total'] = table['inflow'] + table['outflow']
    table['net_flow'] = table['inflow'] - table['outflow']
    if len(table) < TOP_N:
        raise ValueError(f'训练期真实站点只有 {len(table)} 个，不足 {TOP_N} 个。')
    # 总量相同时按站名排序，保证结果可复现。
    return table.reset_index().sort_values(
        ['total', 'station_name'], ascending=[False, True]).head(TOP_N).reset_index(drop=True)


def build_samples(df, stations, start, cutoff):
    # 完整网格保留没有骑行的小时，不能只使用发生过骑行的组合。
    index = pd.MultiIndex.from_product(
        [stations['station_name'], pd.date_range(start, periods=31, freq='D'), range(24)],
        names=['station_name', 'date', 'hour'])
    counts = (df.groupby(['start_station_name', 'date', 'hour']).size()
              .rename_axis(['station_name', 'date', 'hour']))
    grid = counts.reindex(index, fill_value=0).rename('demand').reset_index()
    grid['dow'] = grid['date'].dt.dayofweek
    grid['is_weekend'] = grid['dow'].ge(5).astype('int64')
    grid = grid.merge(stations, on='station_name', how='left', validate='many_to_one')
    train = grid.loc[grid['date'].lt(cutoff)].copy()
    test = grid.loc[grid['date'].ge(cutoff)].copy()
    # 按题目要求在完整训练集拟合历史均值，并在测试期固定使用。
    # 这些是训练后冻结的模型统计参数，不用于声称训练期逐日回测效果。
    mean = float(train['demand'].mean())
    history = train.groupby(['station_name', 'hour'])['demand'].mean().rename('hist_mean')
    train = train.join(history, on=['station_name', 'hour'])
    test = test.join(history, on=['station_name', 'hour'])
    for part in [train, test]:
        part['hist_mean'] = part['hist_mean'].fillna(mean)
        if not np.isfinite(part[FEATURES].to_numpy(dtype=float)).all():
            raise ValueError('模型特征包含无效值。')
    print(f'样本网格总行数：{len(grid):,}；训练集行数：{len(train):,}；测试集行数：{len(test):,}')
    print(f'训练日期：{start:%Y-%m-%d} 至 {cutoff - pd.Timedelta(days=1):%Y-%m-%d}；'
          f'测试日期：{cutoff:%Y-%m-%d} 至 {start + pd.Timedelta(days=30):%Y-%m-%d}')
    print(f'训练集需求均值：{mean:.6f}；测试集真实需求量均值：{test["demand"].mean():.6f}')
    return train, test


def fit_models(train, test):
    x_train, x_test = train[FEATURES], test[FEATURES]
    y_train, y_test = train['demand'], test['demand']
    forest = RandomForestRegressor(n_estimators=100, random_state=RANDOM_STATE, n_jobs=-1)
    predictions = {'baseline': np.full(len(test), y_train.mean(), dtype=float)}
    for name, model in [('线性回归', LinearRegression()), ('随机森林', forest)]:
        model.fit(x_train, y_train)
        predictions[name] = model.predict(x_test)
    # 三个模型统一使用原始预测值，不对线性回归单独截断或取整。
    metrics = pd.DataFrame([
        {'model': name, 'RMSE': np.sqrt(mean_squared_error(y_test, pred)),
         'MAE': mean_absolute_error(y_test, pred), 'R2': r2_score(y_test, pred)}
        for name, pred in predictions.items()
    ]).sort_values('RMSE', kind='stable').reset_index(drop=True)
    print('\n测试集模型指标（按 RMSE 升序）：')
    print(metrics.to_string(index=False, float_format=lambda v: f'{v:.6f}'))
    scores = metrics.set_index('model')['RMSE']
    baseline, linear, rf = (float(scores[name]) for name in ['baseline', '线性回归', '随机森林'])
    if baseline > 0:
        print(f'随机森林相对基线的 RMSE 提升百分比：{(baseline - rf) / baseline * 100:.2f}%（正值表示改善）')
    else:
        print('基线 RMSE 为 0，相对提升百分比无定义。')
    importance = pd.Series(forest.feature_importances_, index=FEATURES).sort_values(ascending=False)
    print('\n随机森林特征重要性 TOP5：')
    print(importance.head(5).rename('重要性').to_string(float_format=lambda v: f'{v:.6f}'))
    percent = f'，相对变化 {(linear - rf) / linear * 100:+.2f}%' if linear > 0 else '，线性回归误差为零，相对变化无定义'
    verdict = '优于' if rf < linear else ('劣于' if rf > linear else '持平于')
    print(f'结论：按测试集 RMSE，随机森林{verdict}线性回归；'
          f'随机森林 {rf:.6f}，线性回归 {linear:.6f}，误差减少 {linear - rf:+.6f}{percent}。')
    return metrics, predictions['随机森林']


def save_figure(fig, filename):
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    path = FIGURE_DIR / filename
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'已保存：{path}')


def plot_results(test, prediction, metrics):
    points = pd.DataFrame({'actual': test['demand'].to_numpy(), 'predicted': prediction})
    points = points.sample(n=min(5000, len(points)), random_state=RANDOM_STATE)
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.scatter(points['actual'], points['predicted'], s=15, alpha=0.22, color='#2878B5', edgecolors='none')
    upper = max(float(test['demand'].max()), float(np.max(prediction)), 1.0) * 1.05
    ax.plot([0, upper], [0, upper], '--', color='#E87538', label='理想预测：y=x')
    ax.set(xlabel='真实上车需求量（笔/站点·小时）', ylabel='预测上车需求量（笔/站点·小时）',
           title=f'随机森林：测试集预测值与真实值（抽样 {len(points):,} 点）',
           xlim=(0, upper), ylim=(0, upper))
    ax.set_aspect('equal', adjustable='box')
    ax.legend()
    ax.grid(alpha=0.2)
    save_figure(fig, 'fig10_pred_vs_actual.png')
    ordered = metrics.set_index('model').loc[['baseline', '线性回归', '随机森林']]
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    for ax, metric, label in zip(axes, ['RMSE', 'MAE', 'R2'],
                               ['RMSE（越低越好）', 'MAE（越低越好）', 'R²（越高越好）']):
        bars = ax.bar(ordered.index, ordered[metric], color=['#999999', '#2878B5', '#E87538'])
        ax.bar_label(bars, fmt='%.3f', padding=4)
        ax.set(title=label, xlabel='预测模型', ylabel='决定系数 R²' if metric == 'R2' else '误差（笔/站点·小时）')
        ax.axhline(0, color='#555555', linewidth=0.8)
        ax.margins(y=0.20)
        ax.grid(axis='y', alpha=0.2)
        ax.set_axisbelow(True)
    fig.suptitle('站点小时需求预测：测试集三模型对比')
    save_figure(fig, 'fig11_model_compare.png')


def main():
    path = OUTPUT_DIR / 'df_clean.pkl'
    if not path.is_file():
        raise FileNotFoundError(f'未找到清洗数据，请放入：{path}')
    df, start, cutoff = prepare_data(pd.read_pickle(path))
    print('统计口径：仅用 1/1–1/24 选 TOP50 并拟合静态特征和历史均值；'
          '不使用全月供需 CSV，以避免测试期信息泄漏。')
    stations = training_stations(df, start, cutoff)
    train, test = build_samples(df, stations, start, cutoff)
    metrics, prediction = fit_models(train, test)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    metrics_path = OUTPUT_DIR / 'model_metrics.csv'
    metrics.to_csv(metrics_path, index=False, encoding='utf-8-sig')
    print(f'已保存：{metrics_path}')
    # 单独留存训练期站点表，便于复核，不覆盖步骤四的全月结果。
    stations.to_csv(OUTPUT_DIR / 'model_top50_train_stations.csv', index=False, encoding='utf-8-sig')
    plot_results(test, prediction, metrics)


if __name__ == '__main__':
    main()
