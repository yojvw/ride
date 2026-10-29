import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from bike_optimization.features import base_features,adaptive_features,base_columns,common_rows,validate_panel
from bike_optimization.metrics import assert_same_samples,paired_bootstrap,metrics,choose,summarize
from bike_optimization.state import reserve_test,write_lock,read_lock
from bike_optimization.engine import Adapter,tuning_predictions
from bike_optimization.app import tune,finalize
from tools_opt.make_synthetic import make


def panel(n=200):
    parts=[]
    for sid,offset in [('A',0),('B',3)]:
        parts.append(pd.DataFrame({'station_id':sid,'time':pd.date_range('2024-01-01',periods=n,freq='h'),
                                  'departures':np.arange(n)%7+offset,'arrivals':np.arange(n)%5+offset,'observed':True}))
    return pd.concat(parts,ignore_index=True)


def predictions():
    frames=[]
    for name,value in [('hgb_full',3.),('candidate',2.)]:
        frames.append(pd.DataFrame({'station_id':'A','time':pd.date_range('2024-01-01',periods=48,freq='h'),
                     'actual':2.,'prediction':value,'peak_threshold':2.,'split':'validation','target':'departures','model':name}))
    return pd.concat(frames,ignore_index=True)

class FeatureTests(unittest.TestCase):
    def test_original_feature_count_is_23(self):self.assertEqual(len(base_columns()),23)
    def test_mean168_available_at_hour168(self):
        f,extra=adaptive_features(base_features(panel()))
        a=f[f.station_id=='A'].reset_index(drop=True)
        self.assertTrue(pd.isna(a.loc[167,'departures_mean_168']))
        self.assertFalse(pd.isna(a.loc[168,'departures_mean_168']))
    def test_no_extra_warmup(self):
        b=base_features(panel());f,_=adaptive_features(b)
        self.assertEqual(len(common_rows(b,'departures',base_columns())),len(common_rows(f,'departures',base_columns())))
    def test_no_cross_station_ewm(self):
        f,_=adaptive_features(base_features(panel()))
        self.assertTrue(f.groupby('station_id').head(1).departures_ewm_24.isna().all())
    def test_current_target_does_not_change_features(self):
        p=panel();a,extra=adaptive_features(base_features(p))
        idx=p.index[(p.station_id=='A')&(p.time==pd.Timestamp('2024-01-08 03:00'))][0]
        p.loc[idx,'departures']=999;b,_=adaptive_features(base_features(p))
        pd.testing.assert_series_equal(a.loc[idx,extra],b.loc[idx,extra])
    def test_future_values_do_not_change_past(self):
        p=panel();a,extra=adaptive_features(base_features(p))
        cutoff=pd.Timestamp('2024-01-08 03:00');p.loc[p.time>=cutoff,'departures']=999
        b,_=adaptive_features(base_features(p))
        pd.testing.assert_frame_equal(a.loc[a.time<cutoff,extra],b.loc[b.time<cutoff,extra])
    def test_uncovered_targets_not_filled(self):
        p=panel();p.loc[5,'observed']=False;p.loc[5,['departures','arrivals']]=np.nan
        f,_=adaptive_features(base_features(p));self.assertTrue(pd.isna(f.loc[5,'departures']))
    def test_gap_not_reindexed_silently(self):
        with self.assertRaisesRegex(ValueError,'complete hourly'):validate_panel(panel().drop(index=3))
    def test_duplicate_keys_rejected(self):
        p=panel()
        with self.assertRaisesRegex(ValueError,'duplicate'):validate_panel(pd.concat([p,p.iloc[:1]]))
    def test_zero_fraction_respects_missing(self):
        p=panel();p.loc[:23,'departures']=0
        f,_=adaptive_features(base_features(p));self.assertEqual(f.loc[24,'departures_zero_fraction_24'],1)

class MetricTests(unittest.TestCase):
    def test_mask_mismatch_rejected(self):
        p=predictions().drop(index=0)
        with self.assertRaises(AssertionError):assert_same_samples(p)
    def test_duplicate_samples_rejected(self):
        p=predictions()
        with self.assertRaises(AssertionError):assert_same_samples(pd.concat([p,p.iloc[:1]]))
    def test_actual_mismatch_rejected(self):
        p=predictions();p.loc[48,'actual']=3
        with self.assertRaises(AssertionError):assert_same_samples(p)
    def test_bootstrap_constant_difference(self):
        p=predictions();r=paired_bootstrap(p[p.model=='candidate'],p[p.model=='hgb_full'],200)
        self.assertEqual(r['mae_difference'],-1);self.assertEqual(r['ci_high'],-1)
    def test_bootstrap_reproducible(self):
        p=predictions();a=p[p.model=='candidate'];b=p[p.model=='hgb_full']
        self.assertEqual(paired_bootstrap(a,b,50),paired_bootstrap(a,b,50))
    def test_poisson_metric_handles_zero_predictions(self):
        p=predictions().iloc[:2].copy();p['prediction']=0
        self.assertTrue(np.isfinite(metrics(p)['poisson_deviance_eps_1e_minus9']))
    def test_selection_chooses_improvement(self):
        p=predictions();chosen,*_=choose(p,summarize(p),{'bootstrap_repetitions':100})
        self.assertEqual(chosen['departures'],'candidate')
    def test_selection_falls_back(self):
        p=predictions();p.loc[p.model=='candidate','prediction']=4
        chosen,*_=choose(p,summarize(p),{'bootstrap_repetitions':100})
        self.assertEqual(chosen['departures'],'hgb_full')

class StateTests(unittest.TestCase):
    def test_lock_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);write_lock({'x':1},p);(p/'LOCK.json').write_text('{"x":2}')
            with self.assertRaisesRegex(ValueError,'changed'):read_lock(p)
    def test_budget_exhaustion(self):
        with tempfile.TemporaryDirectory() as t:
            reserve_test(t,'a',1,3,'data');reserve_test(t,'b',1,3,'data')
            with self.assertRaisesRegex(ValueError,'exhausted'):reserve_test(t,'c',1,3,'data')
    def test_repeat_test_reservation_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            reserve_test(t,'a',1,3,'data')
            with self.assertRaisesRegex(ValueError,'already'):reserve_test(t,'a',1,3,'data')
    def test_dataset_budget_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            reserve_test(t,'a',1,3,'data1')
            with self.assertRaisesRegex(ValueError,'another dataset'):reserve_test(t,'b',1,3,'data2')
    def test_finalize_requires_acknowledgement(self):
        with self.assertRaisesRegex(ValueError,'acknowledge'):finalize('not_exists','.',False)

class IntegrationTests(unittest.TestCase):
    def test_tune_locks_without_test_scoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);cfg=make(p)
            cfg['demo_host_config']['max_iter']=5;cfg['longer_max_iter']=8
            cfg['demo_host_config']['rolling_folds']=0;cfg['final_prediction_intervals']=False
            (p/'protocol.json').write_text(json.dumps(cfg))
            result=tune(p/'protocol.json',p)
            out=Path(result['result_directory']);pr=pd.read_csv(out/'validation_cv_predictions.csv')
            self.assertNotIn('test',pr.split.unique());self.assertFalse((p/'experiments/optimization_test_budget.json').exists())
            final=finalize(out,p,True)
            self.assertEqual(final['test_budget_used'],2)
            self.assertTrue((out/'final_test/metrics.csv').exists())
            with self.assertRaises(FileExistsError):finalize(out,p,True)

if __name__=='__main__':unittest.main()
