import matplotlib

matplotlib.use('Agg')

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


# 路径以脚本所在目录为基准，与前两步保持一致。
BASE_DIR = Path(__file__).resolve().parent.parent  # 项目根目录（src 的上一级）
DATA_PATH = BASE_DIR / 'output' / 'df_clean.pkl'
FIGURE_DIR = BASE_DIR / 'figures'
OFF_STATION = '站点外停车'
MIN_TOTAL = 100
WARM = '#E87538'
COOL = '#2878B5'
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False


def prepare_data(df):
    # 只接受明确清洗过的字段，异常值报错，不静默删除。
    required = ['start_station_name', 'end_station_name', 'started_at', 'ended_at']
    missing = set(required).difference(df.columns)
    if missing:
        raise ValueError(f'缺少字段：{sorted(missing)}')
    if df.empty:
        raise ValueError('输入数据为空。')
    if df[required].isna().any().any():
        raise ValueError('所需字段存在缺失值，请检查清洗结果；未删除任何记录。')
    for column in required[:2]:
        if not df[column].map(lambda x: isinstance(x, str) and bool(x.strip())).all():
            raise ValueError(f'{column} 必须为非空字符串。')
    start_off = df['start_station_name'].eq(OFF_STATION)
    end_off = df['end_station_name'].eq(OFF_STATION)
    excluded = start_off | end_off
    print(f'输入骑行数：{len(df):,}')
    print(f'起点“{OFF_STATION}”：{int(start_off.sum()):,} 条；'
          f'终点“{OFF_STATION}”：{int(end_off.sum()):,} 条')
    print(f'两端均为站点外停车：{int((start_off & end_off).sum()):,} 条；'
          f'去重后整条排除：{int(excluded.sum()):,} 条')
    valid = df.loc[~excluded, required].copy()
    print(f'保留起终点均为真实站点的骑行：{len(valid):,} 条')
    if valid.empty:
        raise ValueError('排除站点外停车后无有效骑行。')
    for column in ['started_at', 'ended_at']:
        valid[column] = pd.to_datetime(valid[column], errors='raise')
        if valid[column].isna().any():
            raise ValueError(f'{column} 存在无效时间。')
    if (valid['ended_at'] < valid['started_at']).any():
        raise ValueError('存在结束时间早于开始时间的骑行。')
    print('时间口径：对输入全月骑行计数；借车归属出发小时，还车归属到达小时，包含跨日到达。')
    return valid


def station_summary(df):
    # 使用起终点站名的并集，保留只有流入或只有流出的站点。
    inflow = df['end_station_name'].value_counts().rename('inflow')
    outflow = df['start_station_name'].value_counts().rename('outflow')
    table = pd.concat([inflow, outflow], axis=1).fillna(0).astype('int64')
    table.index.name = 'station_name'
    table['total'] = table['inflow'] + table['outflow']
    table['net_flow'] = table['inflow'] - table['outflow']
    table['imbalance_pct'] = table['net_flow'].abs() / table['total'] * 100
    # 并列时按站名排序，使每次运行的结果一致；本步骤不使用随机抽样。
    return (table.reset_index().assign(_abs=table['net_flow'].abs().to_numpy())
            .sort_values(['_abs', 'station_name'], ascending=[False, True])
            .drop(columns='_abs').reset_index(drop=True))


def hourly_netflow(df, stations):
    # 按实际到达时间计流入，不能直接使用基于出发时间生成的 hour 字段。
    incoming = df.loc[df['end_station_name'].isin(stations)]
    outgoing = df.loc[df['start_station_name'].isin(stations)]
    arrivals = incoming.groupby(incoming['ended_at'].dt.hour).size().reindex(range(24), fill_value=0)
    departures = outgoing.groupby(outgoing['started_at'].dt.hour).size().reindex(range(24), fill_value=0)
    return arrivals - departures


def save_figure(fig, filename):
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    path = FIGURE_DIR / filename
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'已保存：{path}')


def plot_rank(eligible):
    top = eligible.head(20).iloc[::-1]
    fig, ax = plt.subplots(figsize=(13, 9))
    colors = [WARM if value > 0 else COOL for value in top['net_flow']]
    bars = ax.barh(top['station_name'], top['net_flow'], color=colors)
    ax.bar_label(bars, labels=[f'{value:+d}' for value in top['net_flow']], padding=4, fontsize=9)
    ax.axvline(0, color='#555555', linewidth=1)
    ax.margins(x=0.18)
    ax.set_title(f'华盛顿特区站点净流量绝对值 TOP{len(top)}（进出总量≥100次）\n暖色：净流入、车辆堆积；冷色：净流出、车辆减少')
    ax.set_xlabel('全月净流量（流入−流出，次）')
    ax.set_ylabel('站点名称')
    ax.grid(axis='x', alpha=0.2)
    ax.set_axisbelow(True)
    if top.empty:
        ax.text(0.5, 0.5, '无满足进出总量门槛的站点', transform=ax.transAxes, ha='center')
    save_figure(fig, 'fig08_top_imbalance.png')


def plot_hourly(df, negative, positive):
    fig, ax = plt.subplots(figsize=(12, 6))
    for group, label, color, extreme in [
        (negative, '早高峰型候选（全月净流出）', COOL, 'min'),
        (positive, '晚高峰型候选（全月净流入）', WARM, 'max'),
    ]:
        flow = hourly_netflow(df, group['station_name'])
        ax.plot(flow.index, flow.values, marker='o', markersize=4, color=color,
                label=f'{label} TOP{len(group)}')
        if group.empty:
            print(f'{label}：无符合条件的站点，无法判定极值小时。')
            continue
        value = flow.min() if extreme == 'min' else flow.max()
        hours = '、'.join(f'{hour:02d}:00' for hour in flow.index[flow.eq(value)])
        print(f'{label}：最净{"流出" if extreme == "min" else "流入"}小时 '
              f'{hours}；该小时全月累计净流量 {int(value):+d} 次')
    ax.axhline(0, color='#555555', linestyle='--', linewidth=1)
    ax.set_xticks(range(24))
    ax.set_xlabel('小时（采用数据原有时间口径）')
    ax.set_ylabel('组内站点全月该小时累计净流量（次）')
    ax.set_title('华盛顿特区两类站点逐小时净流量：早晚高峰潮汐检验\n按全月净流量选组，各组最多20站，进出总量≥100次')
    ax.legend()
    ax.grid(alpha=0.2)
    save_figure(fig, 'fig09_hour_netflow.png')


def main():
    if not DATA_PATH.is_file():
        raise FileNotFoundError(f'未找到清洗后数据，请将数据放入：{DATA_PATH}')
    df = prepare_data(pd.read_pickle(DATA_PATH))
    table = station_summary(df)
    eligible = table.loc[table['total'].ge(MIN_TOTAL)]
    print(f'参与统计的真实站点总数：{len(table):,}；进出总量≥100次：{len(eligible):,}；'
          f'排名过滤：{len(table) - len(eligible):,} 个站点（仍保留在结果表中）')
    # 正负分组严格要求对应符号，不以零值或相反方向站点补足名额。
    negative = eligible.loc[eligible['net_flow'].lt(0)].sort_values(
        ['net_flow', 'station_name'], ascending=[True, True]).head(20)
    positive = eligible.loc[eligible['net_flow'].gt(0)].sort_values(
        ['net_flow', 'station_name'], ascending=[False, True]).head(20)
    columns = ['station_name', 'inflow', 'outflow', 'net_flow']
    for title, group in [('净流出最多', negative), ('净流入最多', positive)]:
        print(f'\n{title} TOP10（进出总量≥100次，不足10站则全部列出）：')
        print(group.head(10)[columns].to_string(index=False))
    imbalance = eligible.sort_values(['imbalance_pct', 'total', 'station_name'],
                                    ascending=[False, False, True]).head(10)
    print('\n失衡指数最高 TOP10（进出总量≥100次）：')
    print(imbalance[['station_name', 'total', 'net_flow', 'imbalance_pct']].to_string(
        index=False, formatters={'imbalance_pct': lambda x: f'{x:.2f}%'}))
    absolute_sum = int(table['net_flow'].abs().sum())
    print(f'\n全市全部统计站点全月净流量的绝对值之和：{absolute_sum:,} 次（未应用100次门槛）')
    print(f'全市净流量代数和：{int(table.net_flow.sum()):,} 次；'
          f'理想条件下抵消全月期末失衡的搬移量下界：{absolute_sum // 2:,} 辆次。')
    print('说明：一次搬移同时缓解一个盈余站和一个短缺站，因此取绝对值之和的一半；'
          '全月净值会抵消日内及跨日波动，不能直接作为每日调度需求或调度车辆趟数。')
    print('小时图仅展示选定站点组，并非全市所有站点合计；早/晚高峰型为候选标签，'
          '是否存在潮汐须结合曲线和实际极值小时判断。')
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    csv_path = DATA_PATH.parent / 'top_imbalance_stations.csv'
    table.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f'已保存：{csv_path}')
    plot_rank(eligible)
    plot_hourly(df, negative, positive)


if __name__ == '__main__':
    main()
