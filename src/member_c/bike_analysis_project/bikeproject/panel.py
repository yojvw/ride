import numpy as np
import pandas as pd


def build_panel(rides,coverage,cfg):
    start,end=pd.Timestamp(cfg['analysis_start']),pd.Timestamp(cfg['analysis_end'])
    train_end=pd.Timestamp(cfg['train_end'])
    selection_end=train_end-pd.Timedelta(days=cfg.get('rolling_folds',2)*cfg.get('rolling_validation_days',2))
    ids=coverage.station_id.unique()
    events=[]
    for col,tc in [('start_station_id','started_at'),('end_station_id','ended_at')]:
        m=rides[tc].between(start,selection_end,inclusive='left') & rides[col].isin(ids)
        events.append(rides.loc[m,col].value_counts())
    popularity=events[0].add(events[1],fill_value=0).sort_values(ascending=False)
    popularity=popularity[popularity>=cfg.get('min_train_events',10)]
    selected=popularity.head(cfg.get('max_stations',20)).index.tolist()
    if not selected:
        raise ValueError('No eligible stations with sufficient training-period events.')
    hours=pd.date_range(start,end,freq='h',inclusive='left')
    idx=pd.MultiIndex.from_product([selected,hours],names=['station_id','time'])
    panel=pd.DataFrame(index=idx).reset_index()
    panel['observed']=False
    for row in coverage[coverage.station_id.isin(selected)].itertuples():
        m=(panel.station_id==row.station_id)&(panel.time>=row.start)&(panel.time+pd.Timedelta(hours=1)<=row.end)
        panel.loc[m,'observed']=True
    for col,tc,target in [('start_station_id','started_at','departures'),('end_station_id','ended_at','arrivals')]:
        valid=rides[col].notna()
        counts=rides.loc[valid].groupby([col,rides.loc[valid,tc].dt.floor('h')]).size()
        counts.index.names=['station_id','time']
        panel=panel.merge(counts.rename(target).reset_index(),on=['station_id','time'],how='left',validate='one_to_one')
        panel[target]=panel[target].fillna(0).where(panel.observed,np.nan)
    panel['net_outflow']=panel.departures-panel.arrivals
    selection=popularity.rename('training_endpoint_events').reset_index()
    selection.columns=['station_id','training_endpoint_events']
    selection['selected']=selection.station_id.isin(selected)
    selection['selection_end_exclusive']=selection_end
    return panel.sort_values(['station_id','time']).reset_index(drop=True),selection


def make_features(panel):
    out=panel.copy().sort_values(['station_id','time']).reset_index(drop=True)
    out['hour']=out.time.dt.hour
    out['weekday']=out.time.dt.dayofweek
    out['weekend']=(out.weekday>=5).astype(int)
    out['hour_sin']=np.sin(2*np.pi*out.hour/24)
    out['hour_cos']=np.cos(2*np.pi*out.hour/24)
    out['weekday_sin']=np.sin(2*np.pi*out.weekday/7)
    out['weekday_cos']=np.cos(2*np.pi*out.weekday/7)
    for target in ['departures','arrivals']:
        g=out.groupby('station_id',sort=False)[target]
        for lag in [1,2,3,24,168]:
            out[f'{target}_lag_{lag}']=g.shift(lag)
        for window in [3,24]:
            out[f'{target}_mean_{window}']=g.transform(lambda s:s.shift(1).rolling(window,min_periods=window).mean())
        out[f'{target}_std_24']=g.transform(lambda s:s.shift(1).rolling(24,min_periods=24).std())
    return out


def feature_columns(target,stage='full'):
    cols=['hour','weekday','weekend','hour_sin','hour_cos','weekday_sin','weekday_cos']
    if stage=='calendar': return cols
    targets=[target] if stage=='own_history' else ['departures','arrivals']
    for t in targets:
        cols += [f'{t}_lag_{k}' for k in [1,2,3,24,168]]
        cols += [f'{t}_mean_3',f'{t}_mean_24',f'{t}_std_24']
    return cols
