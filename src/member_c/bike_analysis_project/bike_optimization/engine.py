import hashlib
import importlib
import json
from importlib.metadata import version
from pathlib import Path
import numpy as np
import pandas as pd
from .features import base_features,base_columns,adaptive_features,common_rows,validate_panel,TARGETS
from .models import registry,fit_predict_candidates,fit


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save_json(obj,path):Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding='utf-8')

def config_read(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def resolve(root,p):
    path=Path(p)
    return path if path.is_absolute() else Path(root)/path


def fingerprint(root,protocol,hostcfg,demo=False):
    inputs={}
    paths={'demo_panel':resolve(root,protocol['demo_panel'])} if demo else {
        k:Path(hostcfg[k]) for k in ['rides_path','coverage_path','stations_path'] if hostcfg.get(k)}
    for k,p in paths.items():inputs[k]=digest(p)
    expected=protocol.get('expected_input_sha256',{})
    for k,v in expected.items():
        if inputs.get(k)!=v:raise ValueError(f'Input digest mismatch: {k}; do not modify the baseline dataset silently.')
    source={}
    for p in Path(__file__).parent.glob('*.py'):source['optimization/'+p.name]=digest(p)
    if not demo:
        for name in ['io','panel','forecast']:
            mod=importlib.import_module('bikeproject.'+name)
            source['host/'+name]=digest(mod.__file__)
    packages={name:version(name) for name in ['numpy','pandas','scipy','scikit-learn','threadpoolctl']}
    return {'inputs':inputs,'source':source,'packages':packages,'host_config':hostcfg}


class Adapter:
    def __init__(self,root,protocol):
        self.root=Path(root).resolve();self.protocol=protocol
        self.demo=protocol.get('synthetic_demo',False)
        if self.demo:
            self.hostcfg=dict(protocol['demo_host_config'])
            self.original_columns=base_columns()
            self.panel=pd.read_csv(resolve(root,protocol['demo_panel']),dtype={'station_id':str},parse_dates=['time'])
            if self.panel.observed.dtype!=bool:raise ValueError('Demo observed must parse as bool')
            self.original_features=base_features
        else:
            io=importlib.import_module('bikeproject.io')
            panelmod=importlib.import_module('bikeproject.panel')
            self.forecastmod=importlib.import_module('bikeproject.forecast')
            self.hostcfg=io.read_config(resolve(root,protocol['project_config']))
            rides,coverage,stations,audit=io.load_inputs(self.hostcfg)
            self.panel,_=panelmod.build_panel(rides,coverage,self.hostcfg)
            self.original_columns=panelmod.feature_columns('departures','full')
            if set(self.original_columns)!=set(panelmod.feature_columns('arrivals','full')):
                raise ValueError('Unexpected asymmetric original feature schema; review before integration.')
            self.original_features=panelmod.make_features
        validate_panel(self.panel)
        h=self.hostcfg
        for key,wanted in protocol.get('fixed_splits',{}).items():
            if pd.Timestamp(h[key])!=pd.Timestamp(wanted):raise ValueError(f'Fixed split changed: {key}')
        self.meta=fingerprint(root,protocol,h,self.demo)
        self.modelcfg={**protocol,'baseline_max_iter':h.get('max_iter',80),'seed':h.get('seed',42)}
        self.specs=registry(self.modelcfg)

    def frame(self,include_test=False):
        panel=self.panel.copy()
        if not include_test:panel=panel[panel.time<pd.Timestamp(self.hostcfg['validation_end'])]
        base=self.original_features(panel).sort_values(['station_id','time']).reset_index(drop=True)
        # Do not let an integration silently change original causal features.
        reference=base_features(panel)
        cols=base_columns()
        if set(cols)!=set(self.original_columns):
            raise ValueError('Original feature schema differs from v0.1.0. Audit real source before using this adapter.')
        pd.testing.assert_frame_equal(base[['station_id','time']+cols],reference[['station_id','time']+cols],
                                      check_dtype=False,check_exact=False,rtol=1e-12,atol=1e-12)
        return adaptive_features(base)

    def baseline_fit(self,train,target):
        if self.demo:return fit(train,target,self.specs[0],self.original_columns,[],self.modelcfg)
        return self.forecastmod.fit_model(train,target,'full',self.hostcfg)


def fold_predictions(adapter,features,extra,split,start,end,names=None,intervals=False):
    out=[]
    for target in TARGETS:
        eligible=common_rows(features,target,adapter.original_columns)
        tr=eligible[eligible.time<start]
        te=eligible[(eligible.time>=start)&(eligible.time<end)]
        if len(tr)<adapter.hostcfg.get('min_training_rows',100) or te.empty:
            raise ValueError(f'Too few samples for {split}/{target}: train={len(tr)} test={len(te)}')
        expected=adapter.protocol.get('expected_rows',{}).get(split)
        if expected is not None and len(te)!=expected:
            raise AssertionError(f'{split}/{target} row count {len(te)} != frozen {expected}')
        use_names=names[target] if isinstance(names,dict) else names
        preds=fit_predict_candidates(tr,te,target,adapter.specs,adapter.original_columns,extra,adapter.modelcfg,
                                     adapter.baseline_fit,use_names)
        peak=tr.groupby('station_id')[target].quantile(.9)
        for name,values in preds.items():
            p=te[['station_id','time',target]].rename(columns={target:'actual'}).copy()
            p['prediction']=values;p['model']=name;p['target']=target;p['split']=split
            p['peak_threshold']=p.station_id.map(peak)
            if intervals:
                spec=next(s for s in adapter.specs if s['name']==name)
                if spec.get('kind')=='blend':spec=next(s for s in adapter.specs if s['name']=='adaptive_poisson')
                lo=fit(tr,target,spec,adapter.original_columns,extra,adapter.modelcfg,.05).predict(te)
                hi=fit(tr,target,spec,adapter.original_columns,extra,adapter.modelcfg,.95).predict(te)
                p['lower']=np.minimum(lo,hi);p['upper']=np.maximum(lo,hi)
                p['interval_method']='auxiliary_quantile_models_no_coverage_guarantee'
            out.append(p)
    return pd.concat(out,ignore_index=True)


def tuning_predictions(adapter):
    f,extra=adapter.frame(False)
    a=pd.Timestamp(adapter.hostcfg['train_end']);b=pd.Timestamp(adapter.hostcfg['validation_end'])
    if not (f.time<b).all():raise AssertionError('Test rows entered tuning')
    pieces=[]
    folds=adapter.hostcfg.get('rolling_folds',2);days=adapter.hostcfg.get('rolling_validation_days',2)
    for i in range(folds):
        end=a-pd.Timedelta(days=days*(folds-1-i));start=end-pd.Timedelta(days=days)
        pieces.append(fold_predictions(adapter,f,extra,f'cv_{i+1}',start,end))
    pieces.append(fold_predictions(adapter,f,extra,'validation',a,b))
    pred=pd.concat(pieces,ignore_index=True)
    if (pred.time>=b).any():raise AssertionError('Test labels leaked into tuning output')
    return pred,extra


def compare_reference(adapter,pred):
    if adapter.demo:return {'status':'synthetic_only_no_real_baseline_reproduction'}
    path=resolve(adapter.root,adapter.protocol['reference_predictions'])
    reference=pd.read_csv(path,dtype={'station_id':str},parse_dates=['time'])
    keys=['target','station_id','time']
    mask=lambda d:(d.split=='validation')&(d.model=='hgb_full')
    a=pred.loc[mask(pred)].sort_values(keys).reset_index(drop=True)
    b=reference.loc[mask(reference)].sort_values(keys).reset_index(drop=True)
    if a.duplicated(keys).any() or b.duplicated(keys).any():raise AssertionError('Reference duplicates')
    pd.testing.assert_frame_equal(a[keys+['actual']],b[keys+['actual']],check_dtype=False,check_exact=True)
    delta=np.abs(a.prediction.to_numpy()-b.prediction.to_numpy())
    tolerance=adapter.protocol.get('baseline_reproduction_tolerance',1e-9)
    if np.max(delta)>tolerance:
        raise AssertionError(f'Baseline validation predictions not reproduced: max delta={delta.max()}. Check frozen environment and host code.')
    return {'status':'validation_baseline_reproduced','max_absolute_prediction_delta':float(delta.max()),
            'n':len(a),'reference_sha256':digest(path),'test_recomputed':False}
