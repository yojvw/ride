import hashlib
import json
import platform
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import numpy as np
import pandas as pd

REQUIRED = ['ride_id','started_at','ended_at','start_station_id','end_station_id','member_type','bike_type']


def save_json(obj, path):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def read_config(path):
    p = Path(path).resolve()
    cfg = json.loads(p.read_text(encoding='utf-8'))
    for k in ['rides_path','coverage_path','stations_path','output_dir']:
        if cfg.get(k):
            q = Path(cfg[k])
            cfg[k] = str(q if q.is_absolute() else (p.parent / q).resolve())
    if not cfg.get('time_basis') or str(cfg['time_basis']).startswith('REPLACE_'):
        raise ValueError('Set time_basis to the dataset local timezone or documented clock convention.')
    for k in ['analysis_start','train_end','validation_end','analysis_end']:
        cfg[k] = str(pd.Timestamp(cfg[k]))
    times = [pd.Timestamp(cfg[k]) for k in ['analysis_start','train_end','validation_end','analysis_end']]
    if not all(a < b for a,b in zip(times,times[1:])):
        raise ValueError('Require analysis_start < train_end < validation_end < analysis_end.')
    if any(t.tzinfo is not None for t in times):
        raise ValueError('This version requires documented, timezone-naive local-clock timestamps.')
    if any(t != t.floor('h') for t in times):
        raise ValueError('Analysis and split boundaries must align to full hours.')
    if cfg.get('rolling_folds',2)<0 or cfg.get('rolling_validation_days',2)<1:
        raise ValueError('Invalid rolling validation settings.')
    if cfg.get('max_stations',20)<1:
        raise ValueError('max_stations must be positive.')
    for sc in cfg.get('simulation',{}).get('scenarios',[]):
        if sc['capacity']<1 or int(sc['capacity'])!=sc['capacity'] or not 0<=sc['initial_fraction']<=1:
            raise ValueError('Scenario requires positive integer capacity and initial_fraction in [0,1].')
        if sc['hourly_budget']<0 or int(sc['hourly_budget'])!=sc['hourly_budget']:
            raise ValueError('hourly_budget must be a nonnegative integer.')
    return cfg


def load_inputs(cfg):
    p = Path(cfg['rides_path'])
    df = pd.read_csv(p, dtype={'ride_id':'string','start_station_id':'string','end_station_id':'string'})
    missing = sorted(set(REQUIRED)-set(df.columns))
    if missing:
        raise ValueError(f'Missing columns: {missing}')
    for col in ['ride_id','start_station_id','end_station_id']:
        df[col] = df[col].str.strip().replace('',pd.NA)
    if df['ride_id'].isna().any() or df['ride_id'].duplicated().any():
        raise ValueError('ride_id must be nonempty and unique. Return duplicates to cleaning stage.')
    for col in ['started_at','ended_at']:
        df[col] = pd.to_datetime(df[col], errors='coerce')
        if df[col].isna().any():
            raise ValueError(f'Invalid or missing {col}; use a separate rejected-records file.')
        if not pd.api.types.is_datetime64_ns_dtype(df[col].dtype):
            raise ValueError('Use consistent timezone-naive timestamps; document timezone in config.')
    duration = (df.ended_at-df.started_at).dt.total_seconds()/60
    if (duration<=0).any():
        raise ValueError('Nonpositive duration; return these rows to cleaning stage.')
    if 'duration_min' in df:
        supplied = pd.to_numeric(df.duration_min, errors='coerce')
        if supplied.isna().any() or ((supplied-duration).abs()>0.02).any():
            raise ValueError('duration_min disagrees with timestamps by >0.02 minutes.')
    df['duration_min'] = duration
    for col in ['member_type','bike_type']:
        df[col] = df[col].fillna('unknown').astype(str)
    for col in ['start_lat','start_lng','end_lat','end_lng']:
        if col in df:
            v = pd.to_numeric(df[col],errors='coerce')
            lim = 90 if col.endswith('lat') else 180
            if (v.notna() & ~v.between(-lim,lim)).any():
                raise ValueError(f'Invalid coordinates in {col}')
            df[col]=v
    coverage = pd.read_csv(cfg['coverage_path'], dtype={'station_id':'string'})
    required = {'station_id','start','end','status'}
    if not required.issubset(coverage.columns):
        raise ValueError('coverage.csv requires station_id,start,end,status.')
    coverage['station_id']=coverage.station_id.str.strip().replace('',pd.NA)
    for col in ['start','end']:
        coverage[col]=pd.to_datetime(coverage[col],errors='coerce')
    if coverage[['station_id','start','end','status']].isna().any().any():
        raise ValueError('Invalid coverage rows.')
    if not coverage.status.isin(['confirmed','assumed']).all():
        raise ValueError('Coverage status must be confirmed or assumed.')
    if not cfg.get('allow_assumed_coverage',False) and (coverage.status=='assumed').any():
        raise ValueError('Assumed coverage requires explicit allow_assumed_coverage=true.')
    for col in ['start','end']:
        if not coverage[col].eq(coverage[col].dt.floor('h')).all():
            raise ValueError('Coverage intervals must be aligned to full hours.')
    if (coverage.end<=coverage.start).any():
        raise ValueError('Coverage end must be after start.')
    coverage=coverage.sort_values(['station_id','start'])
    for sid,g in coverage.groupby('station_id'):
        if (g.start.iloc[1:].to_numpy()<g.end.iloc[:-1].to_numpy()).any():
            raise ValueError(f'Overlapping coverage for {sid}')
    stations = pd.DataFrame(columns=['station_id','lat','lng'])
    if cfg.get('stations_path'):
        stations=pd.read_csv(cfg['stations_path'],dtype={'station_id':'string'})
        if not {'station_id','lat','lng'}.issubset(stations):
            raise ValueError('stations.csv requires station_id,lat,lng.')
        if stations.station_id.isna().any() or stations.station_id.duplicated().any():
            raise ValueError('stations.csv station_id must be nonempty and unique.')
        for col,lim in [('lat',90),('lng',180)]:
            stations[col]=pd.to_numeric(stations[col],errors='coerce')
            if (stations[col].notna() & ~stations[col].between(-lim,lim)).any():
                raise ValueError(f'Invalid station {col}')
    audit={'rows':len(df),'date_start':df.started_at.min(),'date_end':df.ended_at.max(),
           'missing_start_station':int(df.start_station_id.isna().sum()),
           'missing_end_station':int(df.end_station_id.isna().sum()),
           'coverage_rows':len(coverage),'assumed_coverage_rows':int((coverage.status=='assumed').sum()),
           'time_basis':cfg['time_basis'],'synthetic_demo':cfg.get('synthetic_demo',False)}
    return df,coverage,stations,audit


def reproducibility(cfg):
    hashes={}
    for k in ['rides_path','coverage_path','stations_path']:
        if cfg.get(k):
            hashes[k]=hashlib.sha256(Path(cfg[k]).read_bytes()).hexdigest()
    packages={}
    for p in ['numpy','pandas','scipy','scikit-learn','matplotlib','threadpoolctl']:
        try: packages[p]=version(p)
        except PackageNotFoundError: packages[p]='not installed'
    return {'config':cfg,'sha256':hashes,'python':platform.python_version(),'packages':packages}
