import unittest
import tempfile
import json
from pathlib import Path
import numpy as np
import pandas as pd
from bikeproject.io import load_inputs,read_config
from bikeproject.forecast import historical_mean
from bikeproject.evaluation import tables
from bikeproject.main import run

class BoundaryTests(unittest.TestCase):
    def fixture(self,p):
        row={'ride_id':'1','started_at':'2024-01-01 08:50','ended_at':'2024-01-01 09:10',
             'start_station_id':'001','end_station_id':'002','member_type':'member','bike_type':'classic','duration_min':20}
        pd.DataFrame([row]).to_csv(p/'rides.csv',index=False)
        pd.DataFrame({'station_id':['001','002'],'start':['2024-01-01']*2,'end':['2024-02-01']*2,
                      'status':['confirmed']*2}).to_csv(p/'coverage.csv',index=False)
        cfg={'rides_path':str(p/'rides.csv'),'coverage_path':str(p/'coverage.csv'),'time_basis':'test local clock',
             'analysis_start':'2024-01-01','train_end':'2024-01-19','validation_end':'2024-01-25','analysis_end':'2024-02-01',
             'output_dir':str(p/'out')}
        return cfg

    def test_station_leading_zeros_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=self.fixture(Path(tmp));d,*_=load_inputs(cfg)
            self.assertEqual(d.start_station_id.iloc[0],'001')

    def test_assumed_coverage_rejected_without_optin(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);cfg=self.fixture(p)
            c=pd.read_csv(p/'coverage.csv',dtype={'station_id':str});c['status']='assumed';c.to_csv(p/'coverage.csv',index=False)
            with self.assertRaisesRegex(ValueError,'Assumed coverage'): load_inputs(cfg)

    def test_duration_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);cfg=self.fixture(p)
            d=pd.read_csv(p/'rides.csv');d['duration_min']=999;d.to_csv(p/'rides.csv',index=False)
            with self.assertRaisesRegex(ValueError,'disagrees'): load_inputs(cfg)

    def test_overlapping_coverage_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);cfg=self.fixture(p)
            c=pd.read_csv(p/'coverage.csv');pd.concat([c,c]).to_csv(p/'coverage.csv',index=False)
            with self.assertRaisesRegex(ValueError,'Overlapping'): load_inputs(cfg)

    def test_bad_time_order_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);cfg=self.fixture(p);cfg['train_end']='2024-02-05'
            (p/'config.json').write_text(json.dumps(cfg))
            with self.assertRaisesRegex(ValueError,'Require'): read_config(p/'config.json')

    def test_non_hour_aligned_config_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);cfg=self.fixture(p);cfg['analysis_start']='2024-01-01 00:30'
            (p/'config.json').write_text(json.dumps(cfg))
            with self.assertRaisesRegex(ValueError,'full hours'): read_config(p/'config.json')

    def test_placeholder_timezone_config_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);cfg=self.fixture(p);cfg['time_basis']='REPLACE_WITH_TIMEZONE'
            (p/'config.json').write_text(json.dumps(cfg))
            with self.assertRaisesRegex(ValueError,'time_basis'): read_config(p/'config.json')

    def test_overwrite_unmarked_folder_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);cfg=self.fixture(p);(p/'out').mkdir();(p/'out/important.txt').write_text('keep')
            (p/'config.json').write_text(json.dumps(cfg))
            with self.assertRaisesRegex(ValueError,'Refusing overwrite'): run(p/'config.json',True)
            self.assertEqual((p/'out/important.txt').read_text(),'keep')

    def test_baseline_uses_train_only(self):
        tr=pd.DataFrame({'station_id':['A','A'],'weekday':[0,0],'hour':[8,8],'departures':[2,4]})
        te=pd.DataFrame({'station_id':['A'],'weekday':[0],'hour':[8],'departures':[999]})
        self.assertEqual(historical_mean(tr,te,'departures')[0],3)

    def test_metrics_known_example(self):
        p=pd.DataFrame({'station_id':['A','A'],'time':pd.date_range('2024-01-01',periods=2,freq='h'),
                        'actual':[1,3],'prediction':[2,1],'peak_threshold':[2,2],
                        'split':['test']*2,'target':['departures']*2,'model':['previous_day']*2})
        summary,*_=tables(p)
        self.assertAlmostEqual(summary.mae.iloc[0],1.5)
        self.assertAlmostEqual(summary.rmse.iloc[0],np.sqrt(2.5))

if __name__=='__main__': unittest.main()
