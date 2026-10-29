import numpy as np
import pandas as pd

TARGETS=('departures','arrivals')

def base_columns():
    cols=['hour','weekday','weekend','hour_sin','hour_cos','weekday_sin','weekday_cos']
    for t in TARGETS:
        cols += [f'{t}_lag_{n}' for n in [1,2,3,24,168]]
        cols += [f'{t}_mean_3',f'{t}_mean_24',f'{t}_std_24']
    return cols


def validate_panel(panel):
    required={'station_id','time','departures','arrivals','observed'}
    if not required.issubset(panel): raise ValueError(f'Missing panel columns: {required-set(panel)}')
    if panel[['station_id','time']].isna().any().any() or panel.duplicated(['station_id','time']).any():
        raise ValueError('Invalid or duplicate panel keys')
    for _,g in panel.sort_values(['station_id','time']).groupby('station_id'):
        if not g.time.diff().dropna().eq(pd.Timedelta(hours=1)).all():
            raise ValueError('Each station must have a complete hourly index; represent uncovered hours by NaN.')
    for t in TARGETS:
        if (panel[t].dropna()<0).any(): raise ValueError('Negative counts')
        if (panel.loc[~panel.observed,t].notna()).any(): raise ValueError('Uncovered target must remain NaN')


def base_features(panel):
    validate_panel(panel)
    f=panel.sort_values(['station_id','time']).reset_index(drop=True).copy()
    f['hour']=f.time.dt.hour;f['weekday']=f.time.dt.dayofweek
    f['weekend']=(f.weekday>=5).astype(int)
    for name,period in [('hour',24),('weekday',7)]:
        f[name+'_sin']=np.sin(2*np.pi*f[name]/period)
        f[name+'_cos']=np.cos(2*np.pi*f[name]/period)
    for t in TARGETS:
        g=f.groupby('station_id',sort=False)[t]
        for n in [1,2,3,24,168]:f[f'{t}_lag_{n}']=g.shift(n)
        for w in [3,24]:f[f'{t}_mean_{w}']=g.transform(lambda s:s.shift(1).rolling(w,min_periods=w).mean())
        f[f'{t}_std_24']=g.transform(lambda s:s.shift(1).rolling(24,min_periods=24).std())
    return f


def adaptive_features(base):
    f=base.sort_values(['station_id','time']).reset_index(drop=True).copy()
    extra=['weekday_hour']
    f['weekday_hour']=f.weekday*24+f.hour
    for t in TARGETS:
        g=f.groupby('station_id',sort=False)[t]
        for half in [24,72]:
            col=f'{t}_ewm_{half}'
            f[col]=g.transform(lambda s:s.shift(1).ewm(halflife=half,adjust=False,min_periods=1,ignore_na=False).mean())
            extra.append(col)
        col=f'{t}_mean_168'
        f[col]=g.transform(lambda s:s.shift(1).rolling(168,min_periods=168).mean())
        extra.append(col)
        # Same-clock-hour history is restricted to strictly earlier days.
        col=f'{t}_same_hour_mean_7d'
        f[col]=f.groupby(['station_id','hour'],sort=False)[t].transform(lambda s:s.shift(1).rolling(7,min_periods=1).mean())
        extra.append(col)
        derived={f'{t}_recent_ratio':(f[f'{t}_mean_3']+1)/(f[f'{t}_mean_24']+1),
                 f'{t}_day_level_difference':f[f'{t}_lag_24']-f[f'{t}_mean_24'],
                 f'{t}_recent_trend':f[f'{t}_ewm_24']-f[f'{t}_ewm_72'],
                 f'{t}_lag1_minus_lag24':f[f'{t}_lag_1']-f[f'{t}_lag_24']}
        for col,val in derived.items(): f[col]=val;extra.append(col)
        col=f'{t}_zero_fraction_24'
        f[col]=g.transform(lambda s:s.eq(0).astype(float).where(s.notna()).shift(1).rolling(24,min_periods=24).mean())
        extra.append(col)
    # Newly added statistics may be unavailable; HGB handles NaN. They do not change the reference mask.
    f[extra]=f[extra].replace([np.inf,-np.inf],np.nan)
    return f,extra


def common_rows(frame,target,original_columns):
    return frame.dropna(subset=[target]+list(original_columns)).copy()
