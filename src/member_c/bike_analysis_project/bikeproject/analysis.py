import pandas as pd
import numpy as np


def analyse(rides,panel,stations,cfg,out):
    start,end=pd.Timestamp(cfg['analysis_start']),pd.Timestamp(cfg['analysis_end'])
    d=rides[(rides.started_at>=start)&(rides.started_at<end)].copy()
    d['date']=d.started_at.dt.floor('D')
    d['hour']=d.started_at.dt.hour
    d['weekday']=d.started_at.dt.dayofweek
    d['weekend']=d.weekday>=5
    daily=d.groupby('date').size().rename('rides').reset_index()
    daily.to_csv(out/'daily_orders_observed.csv',index=False)
    hourly=d.groupby(['weekend','hour']).size().rename('rides').reset_index()
    calendar=pd.DataFrame({'time':pd.date_range(start,end,freq='h',inclusive='left')})
    calendar['weekend']=calendar.time.dt.dayofweek>=5
    calendar['hour']=calendar.time.dt.hour
    exposure=calendar.groupby(['weekend','hour']).size().rename('calendar_hour_slots').reset_index()
    hourly=exposure.merge(hourly,how='left',on=['weekend','hour']).fillna({'rides':0})
    hourly['observed_rides_per_calendar_slot']=hourly.rides/hourly.calendar_hour_slots
    hourly.to_csv(out/'hourly_profile.csv',index=False)
    for col in ['member_type','bike_type']:
        d.groupby(col).agg(rides=('ride_id','size'),median_duration_min=('duration_min','median'),
                          mean_duration_min=('duration_min','mean')).reset_index().to_csv(out/f'{col}_summary.csv',index=False)
        d.groupby([col,'hour']).size().rename('rides').reset_index().to_csv(out/f'{col}_hourly.csv',index=False)
    observed=panel[panel.observed].copy()
    station=observed.groupby('station_id').agg(departures=('departures','sum'),arrivals=('arrivals','sum'),
                    observed_hours=('time','size'),absolute_hourly_imbalance=('net_outflow',lambda x:x.abs().sum())).reset_index()
    station['net_outflow']=station.departures-station.arrivals
    station['imbalance_fraction']=station.absolute_hourly_imbalance/(station.departures+station.arrivals).replace(0,np.nan)
    station=station.merge(stations,on='station_id',how='left',validate='one_to_one')
    station.to_csv(out/'station_summary.csv',index=False)
    observed['hour']=observed.time.dt.hour
    pattern=observed.groupby(['station_id','hour']).agg(departures=('departures','mean'),arrivals=('arrivals','mean'),net_outflow=('net_outflow','mean')).reset_index()
    pattern.to_csv(out/'station_hour_pattern.csv',index=False)
    examples=panel.copy()
    examples['date']=examples.time.dt.floor('D')
    examples['cumulative_net_outflow']=examples.groupby(['station_id','date']).net_outflow.cumsum()
    incomplete=examples.groupby(['station_id','date'])['observed'].transform('all')
    examples.loc[~incomplete,'cumulative_net_outflow']=np.nan
    examples.to_csv(out/'station_daily_cumulative_flow.csv',index=False)
    return {'daily':daily,'hourly':hourly,'station':station,'pattern':pattern,'rides':d}
