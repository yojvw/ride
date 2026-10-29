import unittest
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from bikeproject.panel import build_panel,make_features
from bikeproject.dispatch import plan_moves
from bikeproject.simulation import replay
from bikeproject.io import load_inputs

class PanelTests(unittest.TestCase):
    def fixture(self):
        cfg={'analysis_start':'2024-01-01','train_end':'2024-01-02','analysis_end':'2024-01-03',
             'max_stations':5,'min_train_events':0,'rolling_folds':0}
        rides=pd.DataFrame({'started_at':pd.to_datetime(['2024-01-01 08:50']),
                            'ended_at':pd.to_datetime(['2024-01-01 09:10']),
                            'start_station_id':['A'],'end_station_id':['B']})
        cov=pd.DataFrame({'station_id':['A','B'],'start':pd.to_datetime(['2024-01-01']*2),
                          'end':pd.to_datetime(['2024-01-03']*2),'status':['confirmed']*2})
        return rides,cov,cfg

    def test_cross_hour_arrival(self):
        r,c,cfg=self.fixture();p,_=build_panel(r,c,cfg)
        a=p[(p.station_id=='A')&(p.time==pd.Timestamp('2024-01-01 08:00'))].iloc[0]
        b=p[(p.station_id=='B')&(p.time==pd.Timestamp('2024-01-01 09:00'))].iloc[0]
        self.assertEqual(a.departures,1);self.assertEqual(b.arrivals,1)

    def test_covered_no_events_is_zero(self):
        r,c,cfg=self.fixture();p,_=build_panel(r,c,cfg)
        self.assertEqual(p[(p.station_id=='A')&(p.time==pd.Timestamp('2024-01-01'))].departures.iloc[0],0)

    def test_uncovered_is_nan(self):
        r,c,cfg=self.fixture();c.loc[c.station_id=='A','start']=pd.Timestamp('2024-01-01 01:00')
        p,_=build_panel(r,c,cfg)
        self.assertTrue(pd.isna(p[(p.station_id=='A')&(p.time==pd.Timestamp('2024-01-01'))].departures.iloc[0]))

    def test_lag_cannot_cross_station(self):
        r,c,cfg=self.fixture();p,_=build_panel(r,c,cfg);f=make_features(p)
        self.assertTrue(f.groupby('station_id').head(1).departures_lag_1.isna().all())

    def test_current_label_not_in_rolling_feature(self):
        r,c,cfg=self.fixture();p,_=build_panel(r,c,cfg);a=make_features(p)
        mark=(p.station_id=='A')&(p.time==pd.Timestamp('2024-01-01 08:00'))
        p.loc[mark,'departures']=999;b=make_features(p)
        idx=a.index[(a.station_id=='A')&(a.time==pd.Timestamp('2024-01-01 08:00'))][0]
        self.assertEqual(a.loc[idx,'departures_mean_3'],b.loc[idx,'departures_mean_3'])

    def test_future_station_not_selected(self):
        r,c,cfg=self.fixture()
        extra=pd.DataFrame({'started_at':pd.to_datetime(['2024-01-02 10:00']),
             'ended_at':pd.to_datetime(['2024-01-02 10:20']),'start_station_id':['C'],'end_station_id':['C']})
        c=pd.concat([c,pd.DataFrame({'station_id':['C'],'start':pd.to_datetime(['2024-01-01']),
                                   'end':pd.to_datetime(['2024-01-03']),'status':['confirmed']})])
        p,_=build_panel(pd.concat([r,extra]),c,cfg)
        self.assertNotIn('C',p.station_id.unique())

class DispatchTests(unittest.TestCase):
    def check_method(self,method):
        inv={'A':10,'B':0};cap={'A':12,'B':12};coords={'A':(0,0),'B':(0,.001)}
        moves,status=plan_moves(inv,cap,{'A':0,'B':8},{'A':0,'B':0},coords,3,method,buffer=2)
        self.assertLessEqual(sum(m[2] for m in moves),3)
        for a,b,n,d in moves: inv[a]-=n;inv[b]+=n;self.assertEqual(n,int(n))
        self.assertEqual(sum(inv.values()),10)
        self.assertTrue(all(0<=inv[s]<=cap[s] for s in inv))
        self.assertGreater(inv['B'],0)
        return status

    def test_greedy_conserves_inventory(self): self.check_method('greedy')
    def test_milp_conserves_inventory(self): self.assertEqual(self.check_method('milp')['status'],'optimal')
    def test_zero_budget(self):
        moves,_=plan_moves({'A':4,'B':0},{'A':10,'B':10},{'A':0,'B':4},{},
                           {'A':(0,0),'B':(0,.1)},0)
        self.assertEqual(moves,[])

class ReplayTests(unittest.TestCase):
    def setup_replay(self,rows,fraction=0,capacity=2):
        r=pd.DataFrame(rows,columns=['ride_id','started_at','ended_at','start_station_id','end_station_id'])
        for c in ['started_at','ended_at']: r[c]=pd.to_datetime(r[c])
        cfg={'validation_end':'2024-01-01','analysis_end':'2024-01-02','simulation':{}}
        sc={'name':'test','capacity':capacity,'initial_fraction':fraction,'hourly_budget':0}
        return replay(r,pd.DataFrame(),{'A':(0,0),'B':(0,.01)},cfg,'no_dispatch',sc)[0]

    def test_failed_departure_does_not_create_arrival(self):
        s=self.setup_replay([('x','2024-01-01 08:00','2024-01-01 08:20','A','B')])
        self.assertEqual(s['served_requests'],0);self.assertEqual(s['final_station_inventory'],0)

    def test_successful_trip_conserves_bikes(self):
        s=self.setup_replay([('x','2024-01-01 08:00','2024-01-01 08:20','A','B')],.5)
        self.assertEqual(s['served_requests'],1);self.assertEqual(s['final_station_inventory'],2)

    def test_external_inflow_accounted(self):
        s=self.setup_replay([('x','2024-01-01 08:00','2024-01-01 08:20','X','A')])
        self.assertEqual(s['external_in'],1);self.assertEqual(s['final_station_inventory'],1)

    def test_external_outflow_accounted(self):
        s=self.setup_replay([('x','2024-01-01 08:00','2024-01-01 08:20','A','X')],.5)
        self.assertEqual(s['external_out'],1);self.assertEqual(s['final_station_inventory'],1)

    def test_full_return_enters_holding_pool(self):
        s=self.setup_replay([('x','2024-01-01 08:00','2024-01-01 08:20','X','A')],1)
        self.assertEqual(s['overflow_holding'],1);self.assertEqual(s['full_return_events'],1)

class InputTests(unittest.TestCase):
    def test_duplicate_ids_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            row={'ride_id':'x','started_at':'2024-01-01 08:00','ended_at':'2024-01-01 08:20',
                 'start_station_id':'A','end_station_id':'B','member_type':'member','bike_type':'classic'}
            pd.DataFrame([row,row]).to_csv(p/'rides.csv',index=False)
            with self.assertRaisesRegex(ValueError,'unique'):
                load_inputs({'rides_path':str(p/'rides.csv')})

if __name__=='__main__': unittest.main()
