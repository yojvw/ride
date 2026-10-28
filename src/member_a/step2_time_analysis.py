import matplotlib

matplotlib.use('Agg')

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


# 路径以脚本所在目录为基准，避免启动位置影响数据读取。
BASE_DIR = Path(__file__).resolve().parent.parent  # 项目根目录（src 的上一级）
DATA_PATH = BASE_DIR / 'output' / 'df_clean.pkl'
FIGURE_DIR = BASE_DIR / 'figures'
WEEKDAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
USER_NAMES = {'member': '会员', 'casual': '临时用户'}

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False


def save_figure(fig, filename):
    # 统一保存分辨率，并及时关闭图形以释放内存。
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / filename, dpi=150, bbox_inches='tight')
    plt.close(fig)


def main():
    if not DATA_PATH.is_file():
        raise FileNotFoundError(f'未找到清洗后数据，请先完成步骤一：{DATA_PATH}')

    df = pd.read_pickle(DATA_PATH)
    required = {'date', 'hour', 'dow', 'is_weekend', 'member_casual'}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f'缺少时间分析所需字段：{sorted(missing)}')
    if df.empty:
        raise ValueError('清洗后数据为空，无法进行时间分析。')
    if df[list(required)].isna().any().any():
        raise ValueError('时间分析所需字段存在缺失值，请检查步骤一的输出。')
    if not df['hour'].isin(range(24)).all() or not df['dow'].isin(range(7)).all():
        raise ValueError('hour 应为 0~23，dow 应为 0~6。')
    if not df['member_casual'].isin(USER_NAMES).all():
        raise ValueError('member_casual 包含 member、casual 以外的类别。')
    if not df['is_weekend'].isin([False, True]).all():
        raise ValueError('is_weekend 应为布尔值或 0、1。')

    # 只转换副本中的日期，不修改步骤一保存的数据。
    df = df.copy()
    df['date'] = pd.to_datetime(df['date'], errors='raise').dt.normalize()
    if df['date'].isna().any() or not df['date'].between('2024-01-01', '2024-01-31').all():
        raise ValueError('date 必须是 2024 年 1 月内的有效日期。')
    if not (df['dow'] == df['date'].dt.dayofweek).all():
        raise ValueError('dow 与 date 对应的星期不一致。')
    if not (df['is_weekend'] == (df['dow'] >= 5)).all():
        raise ValueError('is_weekend 与 dow 不一致。')

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    colors = ['#2563EB', '#F97316']

    # 补齐全部小时、星期和日期，未出现的组合记为零，不删除记录。
    hourly = (
        df.groupby(['hour', 'member_casual']).size().unstack(fill_value=0)
        .reindex(index=range(24), columns=['member', 'casual'], fill_value=0)
    )
    hourly_total = hourly.sum(axis=1)
    weekday = df.groupby('dow').size().reindex(range(7), fill_value=0)
    dates = pd.date_range('2024-01-01', '2024-01-31', freq='D')
    daily = df.groupby('date').size().reindex(dates, fill_value=0)
    heatmap = (
        df.groupby(['hour', 'dow']).size().unstack(fill_value=0)
        .reindex(index=range(24), columns=range(7), fill_value=0)
    )

    # 并列极值全部打印；图中日极值也标注所有并列日期。
    peak_hours = hourly_total[hourly_total == hourly_total.max()].index.tolist()
    low_hours = hourly_total[hourly_total == hourly_total.min()].index.tolist()
    print(f'本次读取骑行记录：{len(df):,} 条')
    print(f'峰值小时：{peak_hours} 时；每个峰值小时骑行量：{hourly_total.max():,} 次')
    print(f'最低小时：{low_hours} 时；每个最低小时骑行量：{hourly_total.min():,} 次')

    # 占比以各用户类别自身的总骑行量为分母，报告原始总量占比。
    split = (
        df.groupby(['member_casual', 'is_weekend']).size().unstack(fill_value=0)
        .reindex(index=['member', 'casual'], columns=[False, True], fill_value=0)
    )
    work_total, weekend_total = split.sum(axis=0).tolist()
    print(f'工作日总量：{work_total:,} 次；周末总量：{weekend_total:,} 次')
    shares = split.div(split.sum(axis=1).replace(0, float('nan')), axis=0) * 100
    print('以下占比的分母为各类用户全月骑行量，未按工作日或周末天数归一化：')
    for user, label in USER_NAMES.items():
        print(f'{label}：工作日 {shares.loc[user, False]:.2f}%；周末 {shares.loc[user, True]:.2f}%')
    for weekend, label in [(False, '工作日'), (True, '周末')]:
        difference = shares.loc['casual', weekend] - shares.loc['member', weekend]
        print(f'{label}占比差异（casual − member）：{difference:+.2f} 个百分点')

    # 早晚高峰按预先指定的时间窗口识别，不预设数据必然呈双峰。
    fig, ax = plt.subplots(figsize=(11, 6))
    for user, color in zip(USER_NAMES, colors):
        ax.plot(hourly.index, hourly[user], marker='o', markersize=4,
                label=f'{user}（{USER_NAMES[user]}）', color=color)
    for start, end, label, offset in [(6, 10, '早高峰', 0.96), (16, 20, '晚高峰', 0.83)]:
        peak = hourly_total.loc[start:end].idxmax()
        ax.axvline(peak, color='#64748B', linestyle='--', alpha=0.65)
        ax.text(peak + 0.2, offset, f'{label} {peak}:00\n合计 {hourly_total.loc[peak]:,} 次',
                transform=ax.get_xaxis_transform(), va='top', fontsize=10,
                bbox=dict(facecolor='white', alpha=0.85, edgecolor='none'))
        print(f'{label}（{start}~{end} 时内；并列时取最早）：{peak} 时，{hourly_total.loc[peak]:,} 次')
    ax.set(title='2024年1月各小时骑行量（早高峰窗口6–10时，晚高峰窗口16–20时）',
           xlabel='小时', ylabel='全月累计骑行量（次）')
    ax.set_xticks(range(24))
    ax.set_ylim(bottom=0)
    ax.grid(axis='y', alpha=0.25)
    ax.legend(loc='upper left')
    save_figure(fig, 'fig01_hourly.png')

    # 星期图为全月累计量，各星期在一月出现的次数可能不同。
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(WEEKDAY_NAMES, weekday.values,
                  color=['#2563EB'] * 5 + ['#F97316'] * 2)
    ax.bar_label(bars, fmt='%.0f', padding=3)
    ax.set(title='2024年1月各星期累计骑行量', xlabel='星期', ylabel='全月累计骑行量（次）')
    ax.margins(y=0.12)
    save_figure(fig, 'fig02_weekday.png')

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(daily.index.day, daily.values, color=colors[0], marker='o', markersize=4)
    for value, label, color, vertical in [
        (daily.max(), '最高', '#DC2626', -38),
        (daily.min(), '最低', '#15803D', 24),
    ]:
        for day in daily[daily == value].index:
            ax.scatter(day.day, value, color=color, s=55, zorder=3)
            ax.annotate(f'{label}：1月{day.day}日\n{value:,} 次', (day.day, value),
                        xytext=(0, vertical), textcoords='offset points', ha='center',
                        fontsize=9, color=color,
                        bbox=dict(facecolor='white', alpha=0.8, edgecolor='none'))
        day_text = '、'.join(f'1月{day.day}日' for day in daily[daily == value].index)
        print(f'日骑行量{label}：{day_text}，{value:,} 次')
    ax.set(title='2024年1月每日骑行量', xlabel='日期（1月）', ylabel='每日骑行量（次）')
    ax.set_xticks(range(1, 32))
    ax.margins(x=0.04, y=0.22)
    ax.grid(axis='y', alpha=0.25)
    save_figure(fig, 'fig03_daily.png')

    fig, ax = plt.subplots(figsize=(10, 9))
    sns.heatmap(heatmap, cmap='YlOrRd', xticklabels=WEEKDAY_NAMES,
                yticklabels=list(range(24)), cbar_kws={'label': '全月累计骑行量（次）'}, ax=ax)
    ax.set(title='2024年1月小时×星期骑行量热力图', xlabel='星期', ylabel='小时')
    ax.tick_params(axis='y', rotation=0)
    save_figure(fig, 'fig04_heatmap.png')
    print(f'四张图已保存至：{FIGURE_DIR}')


if __name__ == '__main__':
    main()
