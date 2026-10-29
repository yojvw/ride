import numpy as np
import pandas as pd
from .dispatch import plan_moves


def replay(rides,forecast,coords,cfg,strategy,scenario):
    start,end=pd.Timestamp(cfg['validation_end']),pd.Timestamp(cfg['analysis_end'])
    ids=sorted(coords)
    capacity={s:int(scenario['capacity']) for s in ids}
    inventory={s:int(np.floor(capacity[s]*scenario['initial_fraction'])) for s in ids}
    initial=sum(inventory.values())
    if any(v<0 or v>capacity[s] for s,v in inventory.items()): raise ValueError('Bad inventory scenario')
    active=set();in_transit=0;overflow=0;external_in=0;external_out=0
    demand=served=full_returns=moved=0;cost=0.0
    events=[]
    for r in rides.itertuples():
        origin=None if pd.isna(r.start_station_id) else str(r.start_station_id)
        destination=None if pd.isna(r.end_station_id) else str(r.end_station_id)
        if start<=r.started_at<end and origin in inventory:
            events.append((r.started_at,2,'departure',r.ride_id,origin,destination))
        if start<=r.ended_at<end and destination in inventory:
            internal=(origin in inventory and r.started_at>=start)
            events.append((r.ended_at,0,'internal_arrival' if internal else 'external_arrival',r.ride_id,origin,destination))
    for hour in pd.date_range(start,end,freq='h',inclusive='left'):
        events.append((hour,1,'dispatch','',None,None))
    events.sort(key=lambda x:(x[0],x[1],str(x[3])))
    lookup={}
    for r in forecast.itertuples():
        lookup[(r.time,r.station_id,r.target)]=float(r.prediction)
    snapshots=[];moves_log=[];solver_log=[]
    def check():
        if any(v<0 or v>capacity[s] for s,v in inventory.items()):
            raise AssertionError('Inventory bound violation')
        if sum(inventory.values())+in_transit+overflow != initial+external_in-external_out:
            raise AssertionError('Fleet balance violation')
    for time,priority,kind,rid,origin,dest in events:
        if kind=='departure':
            demand+=1
            if inventory[origin]>0:
                inventory[origin]-=1;served+=1
                if dest in inventory:
                    active.add(rid);in_transit+=1
                else:
                    external_out+=1
        elif kind=='internal_arrival':
            if rid not in active:
                continue
            active.remove(rid);in_transit-=1
            if inventory[dest]<capacity[dest]: inventory[dest]+=1
            else: overflow+=1;full_returns+=1
        elif kind=='external_arrival':
            external_in+=1
            if inventory[dest]<capacity[dest]: inventory[dest]+=1
            else: overflow+=1;full_returns+=1
        else:
            if strategy!='no_dispatch':
                dep={s:lookup.get((time,s,'departures'),np.nan) for s in ids}
                arr={s:lookup.get((time,s,'arrivals'),np.nan) for s in ids}
                if not all(np.isfinite(v) for v in list(dep.values())+list(arr.values())):
                    solver_log.append({'time':time,'status':'skipped_missing_forecast','solver':strategy})
                else:
                    method='milp' if strategy=='model_milp' else 'greedy'
                    moves,status=plan_moves(inventory,capacity,dep,arr,coords,scenario['hourly_budget'],method,
                                            cfg['simulation'].get('buffer',2),cfg['simulation'].get('distance_weight',.03))
                    solver_log.append({'time':time,**status})
                    for a,b,n,d in moves:
                        inventory[a]-=n;inventory[b]+=n;moved+=n;cost+=n*d
                        moves_log.append({'time':time,'from_station':a,'to_station':b,'bikes':n,'distance_km':d,'bike_km_proxy':n*d})
            for sid in ids:
                snapshots.append({'time':time,'station_id':sid,'inventory':inventory[sid],'capacity':capacity[sid]})
        check()
    summary={'scenario':scenario['name'],'strategy':strategy,'observed_requests':demand,'served_requests':served,
             'unserved_requests':demand-served,'service_rate':served/demand if demand else np.nan,
             'full_return_events':full_returns,'moved_bikes':moved,'bike_km_proxy':cost,
             'external_in':external_in,'external_out':external_out,'final_in_transit':in_transit,
             'overflow_holding':overflow,'initial_fleet':initial,'final_station_inventory':sum(inventory.values()),
             'claim_scope':'scenario_replay_of_observed_requests_NOT_actual_unmet_demand'}
    return summary,pd.DataFrame(snapshots),pd.DataFrame(moves_log),pd.DataFrame(solver_log)


def run_simulations(rides,predictions,stations,panel,cfg,out):
    if not cfg.get('simulation',{}).get('enabled',False):
        return pd.DataFrame()
    test=predictions[predictions.split=='test']
    test_panel=panel[panel.time>=pd.Timestamp(cfg['validation_end'])]
    valid=test_panel.groupby('station_id')['observed'].all()
    ids=valid[valid].index.intersection(stations.dropna(subset=['lat','lng']).station_id)
    if len(ids)<2: raise ValueError('Simulation needs >=2 stations with coordinates and complete test coverage.')
    xyz=stations.set_index('station_id').loc[ids]
    coords={sid:(float(r.lat),float(r.lng)) for sid,r in xyz.iterrows()}
    pd.DataFrame({'station_id':list(coords)}).to_csv(out/'simulation_stations.csv',index=False)
    summaries=[];all_snap=[];all_moves=[];all_status=[]
    scenarios=cfg['simulation'].get('scenarios',[])
    for sc in scenarios:
        for strategy in ['no_dispatch','historical_greedy','model_greedy','model_milp']:
            model='historical_mean' if strategy=='historical_greedy' else 'hgb_full'
            forecast=test[test.model==model]
            result,snap,moves,status=replay(rides,forecast,coords,cfg,strategy,sc)
            summaries.append(result)
            for frame,collection in [(snap,all_snap),(moves,all_moves),(status,all_status)]:
                if not frame.empty:
                    frame['scenario']=sc['name'];frame['strategy']=strategy;collection.append(frame)
    for name,parts in [('simulation_inventory',all_snap),('simulation_moves',all_moves),('simulation_solver_log',all_status)]:
        if parts: pd.concat(parts,ignore_index=True).to_csv(out/f'{name}.csv',index=False)
    return pd.DataFrame(summaries)
