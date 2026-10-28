import matplotlib

matplotlib.use('Agg')

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# 路径以脚本所在目录为基准，支持从其他目录启动。
BASE_DIR = Path(__file__).resolve().parent.parent  # 项目根目录（src 的上一级）
DATA_PATH = BASE_DIR / 'output' / 'df_clean.pkl'
FIGURE_DIR = BASE_DIR / 'figures'
OFF_STATION = '站点外停车'
USER_NAMES = {'member': '会员', 'casual': '临时用户'}
COLORS = {'member': '#2563EB', 'casual': '#F97316'}
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False


def save_figure(fig, filename):
    # 保存后关闭图形，避免连续绘图占用过多内存。
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / filename, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'已保存：{FIGURE_DIR / filename}')


def haversine_km(df):
    # 将角度转为弧度，按球面距离公式进行向量化计算。
    lat1, lon1, lat2, lon2 = np.radians(
        df[['start_lat', 'start_lng', 'end_lat', 'end_lng']].to_numpy(dtype=float)
    ).T
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    # 限制浮点误差，避免反正弦函数接收到定义域外的数值。
    return 2 * 6371 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def main():
    if not DATA_PATH.is_file():
        raise FileNotFoundError(f'未找到清洗后数据，请将数据放入：{DATA_PATH}')
    df = pd.read_pickle(DATA_PATH)
    required = ['start_station_name', 'member_casual',
                'start_lat', 'start_lng', 'end_lat', 'end_lng']
    missing = set(required).difference(df.columns)
    if missing:
        raise ValueError(f'缺少空间分析所需字段：{sorted(missing)}')
    if df.empty:
        raise ValueError('数据为空，无法进行空间分析。')
    # 遇到异常直接报告，不静默删除记录或改变统计分母。
    if df[required].isna().any().any():
        raise ValueError('空间分析字段存在缺失值，请检查清洗结果；未删除任何记录。')
    if not df['member_casual'].isin(USER_NAMES).all():
        raise ValueError('用户类型必须为 member 或 casual。')
    df = df.copy()
    for column, limit in [('start_lat', 90), ('end_lat', 90),
                          ('start_lng', 180), ('end_lng', 180)]:
        df[column] = pd.to_numeric(df[column], errors='raise')
        if not np.isfinite(df[column].to_numpy(dtype=float)).all() or not df[column].between(-limit, limit).all():
            raise ValueError(f'{column} 含无效经纬度，请检查清洗结果。')
    names = df['start_station_name']
    if not names.map(lambda value: isinstance(value, str) and bool(value.strip())).all():
        raise ValueError('起点站名须为非空字符串，缺失站点应统一标记为“站点外停车”。')

    # 仅在站点维度排除明确标记的站点外停车，其他分析保留全部骑行。
    off_station = names.eq(OFF_STATION)
    station_df = df.loc[~off_station]
    counts = station_df['start_station_name'].value_counts()
    print(f'总骑行记录数：{len(df):,}')
    print(f'站点统计排除“{OFF_STATION}”：{int(off_station.sum()):,} 条')
    print(f'剩余有效有站点记录数：{len(station_df):,}')
    print(f'真实起点站点总数（按站名去重）：{len(counts):,}')
    print('\nTOP10 热门起点站：')
    for rank, (name, count) in enumerate(counts.head(10).items(), start=1):
        print(f'{rank:2d}. {name}：{count:,} 次')
    for n in (10, 20):
        if len(station_df):
            print(f'TOP{n} 占全部有站点记录比例：{counts.head(n).sum() / len(station_df):.2%}')
        else:
            print(f'TOP{n} 占比：无有站点记录，无法计算')

    print('\n起点位置统计（包含站点外停车）：')
    print(f'经度范围：{df.start_lng.min():.6f} ~ {df.start_lng.max():.6f}')
    print(f'纬度范围：{df.start_lat.min():.6f} ~ {df.start_lat.max():.6f}')
    print(f'中心点（经度、纬度均值）：({df.start_lng.mean():.6f}, {df.start_lat.mean():.6f})')

    df['distance_km'] = haversine_km(df)
    distance = df['distance_km']
    median, mean = distance.median(), distance.mean()
    truncated = int((distance > 10).sum())
    print('\n骑行直线距离统计（全部记录，未截断）：')
    print(f'中位数：{median:.3f} km；均值：{mean:.3f} km；最大值：{distance.max():.3f} km')
    print(f'起终点重合（<50 米，视为原地还车）：{int((distance < 0.05).sum()):,} 条，占比 {(distance < 0.05).mean():.2%}')
    print(f'距离 >10 km、绘图时并入最右区间：{truncated:,} 条')
    group_means = df.groupby('member_casual')['distance_km'].mean().reindex(USER_NAMES)
    for user, label in USER_NAMES.items():
        value = group_means[user]
        print(f'{label}平均直线距离：{value:.3f} km' if pd.notna(value) else f'{label}：无记录')
    if group_means.notna().all():
        if np.isclose(group_means['member'], group_means['casual'], rtol=0, atol=1e-9):
            print('两类用户的平均直线距离相同。')
        else:
            print(f'{USER_NAMES[group_means.idxmax()]}平均骑得更远。')
    else:
        print('缺少某类用户记录，无法比较平均距离。')

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    # 大数据量固定抽取五万条；位置范围与中心点仍使用全量数据统计。
    sampled = df.sample(n=50000, random_state=42) if len(df) > 50000 else df
    print(f'散点图使用 {len(sampled):,} / {len(df):,} 条记录。')
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.scatter(sampled['start_lng'], sampled['start_lat'], s=3, alpha=0.15,
               color=COLORS['member'], linewidths=0)
    ax.set(title=f'华盛顿特区共享单车起点分布（绘制 {len(sampled):,} 条）',
           xlabel='起点经度（°）', ylabel='起点纬度（°）')
    ax.set_aspect('equal')
    ax.grid(alpha=0.2)
    save_figure(fig, 'fig05_start_scatter.png')

    # 按总次数排序，再分用户类型堆叠，最高频站点位于图的最上方。
    top = counts.head(20)
    fig, ax = plt.subplots(figsize=(13, 10))
    if len(top):
        grouped = (station_df.groupby(['start_station_name', 'member_casual'])
                   .size().unstack(fill_value=0)
                   .reindex(index=top.index, columns=list(USER_NAMES), fill_value=0))
        y = np.arange(len(top))
        left = np.zeros(len(top))
        for user, label in USER_NAMES.items():
            values = grouped[user].to_numpy()
            ax.barh(y, values, left=left, color=COLORS[user], label=label)
            left += values
        for position, total in enumerate(top.to_numpy()):
            ax.annotate(f'{total:,}', (total, position), xytext=(5, 0),
                        textcoords='offset points', va='center', fontsize=9)
        ax.set_yticks(y, top.index, fontsize=9)
        ax.invert_yaxis()
        ax.set_xlim(0, top.max() * 1.18)
        ax.legend()
    else:
        ax.text(0.5, 0.5, '无有效起点站记录', transform=ax.transAxes, ha='center')
    ax.set(title=f'TOP20 热门起点站（已排除站点外停车 {int(off_station.sum()):,} 条）',
           xlabel='骑行次数', ylabel='起点站名称')
    save_figure(fig, 'fig06_top_stations.png')

    # 仅绘图数据截断至十公里，原始距离用于全部统计和参考线。
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.hist(np.minimum(distance.to_numpy(), 10), bins=np.linspace(0, 10, 51),
            color='#60A5FA', edgecolor='white', linewidth=0.5)
    for value, label, color, style in [(median, '中位数', '#DC2626', '--'),
                                       (mean, '均值', '#059669', '-.')]:
        ax.axvline(value, color=color, linestyle=style, linewidth=2,
                   label=f'{label}：{value:.3f} km')
        if value > 10:
            print(f'提示：{label}超过 10 km，参考线在绘图区外，图例保留真实值。')
    ax.set(xlim=(0, 10), title='共享单车骑行直线距离分布',
           xlabel='起终点直线距离（km，>10 km 并入最右区间）', ylabel='骑行次数')
    ax.legend(loc='upper right')
    ax.text(0.98, 0.76, f'截断并入最右区间：{truncated:,} 条\n均值和中位数按未截断数据计算',
            transform=ax.transAxes, ha='right', va='top', fontsize=10)
    save_figure(fig, 'fig07_distance.png')


if __name__ == '__main__':
    main()
