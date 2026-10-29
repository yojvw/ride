import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd


def make(destination):
    out=Path(destination);out.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(42);rows=[]
    for sid in ['001','002','003','004']:
        for time in pd.date_range('2024-01-01','2024-02-01',freq='h',inclusive='left'):
            peak=np.exp(-((time.hour-8)/2)**2)+1.2*np.exp(-((time.hour-17)/2)**2)
            mean=.2+2.4*peak+(.4 if 9<time.hour<22 else 0)
            mean*=1+.01*(time.day-1)
            rows.append({'station_id':sid,'time':time,'departures':rng.poisson(mean),
                         'arrivals':rng.poisson(mean*.95),'observed':True})
    pd.DataFrame(rows).to_csv(out/'panel.csv',index=False)
    cfg={'run_id':'synthetic_v020','synthetic_demo':True,'demo_panel':str((out/'panel.csv').resolve()),
         'ledger_dir':str((out/'experiments').resolve()),'longer_max_iter':20,'bootstrap_repetitions':200,
         'require_negative_ci':True,'require_peak_not_worse':True,'minimum_relative_gain':0,
         'cv_relative_tolerance':.02,'final_prediction_intervals':True,
         'test_evaluations_already_used':1,'maximum_total_test_evaluations':3,
         'demo_host_config':{'analysis_start':'2024-01-01','train_end':'2024-01-19','validation_end':'2024-01-25',
                             'analysis_end':'2024-02-01','rolling_folds':2,'rolling_validation_days':2,
                             'max_iter':12,'min_training_rows':50,'seed':42}}
    (out/'protocol.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
    return cfg

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--destination',required=True);a=p.parse_args()
    make(a.destination)
