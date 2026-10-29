import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd


def make_demo(destination):
    dest=Path(destination).resolve();dest.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(42)
    ids=['A','B','C','D']
    start,end=pd.Timestamp('2024-01-01'),pd.Timestamp('2024-02-01')
    stations=pd.DataFrame({'station_id':ids,'lat':[40.70,40.71,40.72,40.71],
                           'lng':[-73.99,-73.98,-73.97,-73.96]})
    rows=[]
    for t in pd.date_range(start,end,freq='h',inclusive='left'):
        for i,sid in enumerate(ids):
            peak=np.exp(-((t.hour-(8 if i%2==0 else 17))/2)**2)
            rate=.35+3.5*peak+(.8 if 10<=t.hour<=20 else 0)
            if t.dayofweek>=5: rate=.4+1.8*np.exp(-((t.hour-14)/4)**2)
            for k in range(rng.poisson(rate)):
                destid=rng.choice([s for s in ids if s!=sid])
                begun=t+pd.Timedelta(minutes=int(rng.integers(0,60)))
                duration=int(rng.integers(5,35))
                rows.append({'ride_id':f'SYNTH_{len(rows):06d}','started_at':begun,
                             'ended_at':begun+pd.Timedelta(minutes=duration),
                             'start_station_id':sid,'end_station_id':destid,
                             'member_type':rng.choice(['member','casual'],p=[.7,.3]),
                             'bike_type':rng.choice(['classic','electric']),
                             'duration_min':duration,'quality_flags':'synthetic_demo'})
    pd.DataFrame(rows).to_csv(dest/'rides.csv',index=False)
    stations.to_csv(dest/'stations.csv',index=False)
    pd.DataFrame({'station_id':ids,'start':[start]*4,'end':[end]*4,'status':['confirmed']*4}).to_csv(dest/'coverage.csv',index=False)
    cfg={'rides_path':'rides.csv','coverage_path':'coverage.csv','stations_path':'stations.csv','output_dir':'results',
         'time_basis':'SYNTHETIC local clock; no real city or timezone claims',
         'analysis_start':str(start),'train_end':'2024-01-19','validation_end':'2024-01-29','analysis_end':str(end),
         'allow_assumed_coverage':False,'synthetic_demo':True,'max_stations':4,'min_train_events':10,
         'rolling_folds':2,'rolling_validation_days':2,'max_iter':35,'min_training_rows':50,
         'prediction_intervals':True,'seed':42,
         'simulation':{'enabled':True,'buffer':2,'distance_weight':.03,
                       'scenarios':[{'name':'synthetic_low_stock','capacity':16,'initial_fraction':.25,'hourly_budget':4},
                                    {'name':'synthetic_medium_stock','capacity':16,'initial_fraction':.5,'hourly_budget':4}]}}
    (dest/'config.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
    return len(rows)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--destination',default='demo');a=p.parse_args()
    print({'synthetic_rows':make_demo(a.destination)})
